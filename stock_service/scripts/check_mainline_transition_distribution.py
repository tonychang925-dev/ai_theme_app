#!/usr/bin/env python3
"""
主线迁移分布门禁脚本

用途：
- 检查指定交易日 mainline_state_transition 的迁移分布是否异常单边
- 监控 downgrade/fade 是否异常抬升
- 可作为盘后门禁步骤，必要时阻断对外快照
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from statistics import mean, pstdev
import sys
from typing import Any, Dict, List, Optional

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


@dataclass
class TransitionDistribution:
    trade_date: date
    total: int
    ratios: Dict[str, float]
    source_table: str = "mainline_state_transition"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查主线迁移分布异常")
    parser.add_argument("--trade-date", required=True, help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=20, help="历史窗口天数")
    parser.add_argument("--min-total", type=int, default=8, help="最小样本数阈值")
    parser.add_argument("--single-type-dominance-threshold", type=float, default=0.95, help="单迁移类型集中阈值")
    parser.add_argument("--downgrade-jump-threshold", type=float, default=0.35, help="downgrade 相对历史均值抬升阈值")
    parser.add_argument("--fade-jump-threshold", type=float, default=0.15, help="fade 相对历史均值抬升阈值")
    parser.add_argument("--min-history-days", type=int, default=3, help="触发历史对比告警的最小历史天数")
    parser.add_argument("--disable-auto-tune", action="store_true", help="关闭按样本规模自动放宽阈值")
    parser.add_argument("--fail-on-alert", action="store_true", help="出现告警时返回非0退出码")
    return parser.parse_args()


class MainlineTransitionDistributionChecker:
    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            database=self.config.postgres_database,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            min_size=1,
            max_size=3,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _fetch_day_distribution(self, trade_date: date) -> Optional[TransitionDistribution]:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            total = int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM mainline_state_transition
                    WHERE trade_date = $1::date
                    """,
                    trade_date,
                )
                or 0
            )
            if total <= 0:
                return None

            rows = await conn.fetch(
                """
                SELECT transition_type, COUNT(*) AS cnt
                FROM mainline_state_transition
                WHERE trade_date = $1::date
                GROUP BY transition_type
                """,
                trade_date,
            )
            ratios: Dict[str, float] = {}
            for row in rows:
                t = str(row.get("transition_type") or "flat")
                ratios[t] = int(row.get("cnt") or 0) / float(total)
            return TransitionDistribution(trade_date=trade_date, total=total, ratios=ratios)

    async def _fetch_history(self, trade_date: date, lookback_days: int, min_total: int) -> List[TransitionDistribution]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH daily_total AS (
                    SELECT
                        trade_date,
                        COUNT(*) AS total
                    FROM mainline_state_transition
                    WHERE trade_date < $1::date
                      AND trade_date >= ($1::date - ($2 * INTERVAL '1 day'))
                    GROUP BY trade_date
                    HAVING COUNT(*) >= $3
                ),
                daily_type AS (
                    SELECT
                        trade_date,
                        transition_type,
                        COUNT(*) AS cnt
                    FROM mainline_state_transition
                    WHERE trade_date < $1::date
                      AND trade_date >= ($1::date - ($2 * INTERVAL '1 day'))
                    GROUP BY trade_date, transition_type
                )
                SELECT
                    t.trade_date,
                    t.total,
                    COALESCE(
                        jsonb_object_agg(
                            d.transition_type,
                            ROUND((d.cnt::numeric / NULLIF(t.total, 0)::numeric), 6)
                        ) FILTER (WHERE d.transition_type IS NOT NULL),
                        '{}'::jsonb
                    ) AS ratios
                FROM daily_total t
                LEFT JOIN daily_type d ON d.trade_date = t.trade_date
                GROUP BY t.trade_date, t.total
                ORDER BY t.trade_date ASC
                """,
                trade_date,
                lookback_days,
                min_total,
            )

        history: List[TransitionDistribution] = []
        for row in rows:
            raw_ratios = row.get("ratios") or {}
            if isinstance(raw_ratios, str):
                try:
                    ratios_obj = json.loads(raw_ratios)
                except json.JSONDecodeError:
                    ratios_obj = {}
            elif isinstance(raw_ratios, dict):
                ratios_obj = raw_ratios
            else:
                ratios_obj = dict(raw_ratios)
            ratios = {str(k): float(v) for k, v in ratios_obj.items()}
            history.append(
                TransitionDistribution(
                    trade_date=row["trade_date"],
                    total=int(row.get("total") or 0),
                    ratios=ratios,
                )
            )
        return history

    def _ratio_stats(self, values: List[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        return mean(values), pstdev(values) if len(values) > 1 else 0.0

    def _effective_thresholds(
        self,
        *,
        total: int,
        history_days: int,
        base_single_type_dominance_threshold: float,
        base_downgrade_jump_threshold: float,
        base_fade_jump_threshold: float,
        disable_auto_tune: bool,
    ) -> tuple[float, float, float]:
        if disable_auto_tune:
            return (
                base_single_type_dominance_threshold,
                base_downgrade_jump_threshold,
                base_fade_jump_threshold,
            )

        dominance = base_single_type_dominance_threshold
        downgrade_jump = base_downgrade_jump_threshold
        fade_jump = base_fade_jump_threshold

        # 小样本自动放宽阈值，避免首批数据产生单边误报。
        if total < 20:
            dominance += 0.03
            downgrade_jump += 0.06
            fade_jump += 0.03
        if total < 15:
            dominance += 0.05
            downgrade_jump += 0.08
            fade_jump += 0.04
        if total < 10:
            dominance += 0.07
            downgrade_jump += 0.10
            fade_jump += 0.05
        if history_days < 5:
            dominance += 0.03
            downgrade_jump += 0.05
            fade_jump += 0.03

        return min(dominance, 1.0), downgrade_jump, fade_jump

    async def run(
        self,
        trade_date: date,
        lookback_days: int,
        min_total: int,
        single_type_dominance_threshold: float,
        downgrade_jump_threshold: float,
        fade_jump_threshold: float,
        min_history_days: int,
        disable_auto_tune: bool,
    ) -> Dict[str, Any]:
        current = await self._fetch_day_distribution(trade_date)
        if current is None:
            return {
                "ok": False,
                "alerts": [f"{trade_date.isoformat()} 在 mainline_state_transition 无数据"],
                "current": None,
                "history_days": 0,
            }

        history = await self._fetch_history(trade_date, lookback_days, min_total)
        alerts: List[str] = []
        history_days = len(history)
        eff_single_type_threshold, eff_downgrade_jump_threshold, eff_fade_jump_threshold = self._effective_thresholds(
            total=current.total,
            history_days=history_days,
            base_single_type_dominance_threshold=single_type_dominance_threshold,
            base_downgrade_jump_threshold=downgrade_jump_threshold,
            base_fade_jump_threshold=fade_jump_threshold,
            disable_auto_tune=disable_auto_tune,
        )

        if current.total >= min_total and current.ratios:
            top_type, top_ratio = max(current.ratios.items(), key=lambda kv: kv[1])
            if top_ratio > eff_single_type_threshold:
                alerts.append(
                    f"迁移类型集中度异常: top={top_type}, ratio={top_ratio:.3f} > {eff_single_type_threshold:.3f}"
                )

        downgrade_values = [d.ratios.get("downgrade", 0.0) for d in history]
        fade_values = [d.ratios.get("fade", 0.0) for d in history]
        d_mean, d_std = self._ratio_stats(downgrade_values)
        f_mean, f_std = self._ratio_stats(fade_values)

        cur_d = current.ratios.get("downgrade", 0.0)
        cur_f = current.ratios.get("fade", 0.0)

        if history_days >= min_history_days and (
            (cur_d - d_mean) >= eff_downgrade_jump_threshold
            or (d_std > 0 and cur_d >= d_mean + 2.0 * d_std)
        ):
            alerts.append(
                f"downgrade 异常抬升: current={cur_d:.3f}, hist_mean={d_mean:.3f}, hist_std={d_std:.3f}"
            )

        if history_days >= min_history_days and (
            (cur_f - f_mean) >= eff_fade_jump_threshold
            or (f_std > 0 and cur_f >= f_mean + 2.0 * f_std)
        ):
            alerts.append(
                f"fade 异常抬升: current={cur_f:.3f}, hist_mean={f_mean:.3f}, hist_std={f_std:.3f}"
            )

        return {
            "ok": len(alerts) == 0,
            "alerts": alerts,
            "current": current,
            "history_days": len(history),
            "history_baseline": {
                "downgrade_mean": d_mean,
                "downgrade_std": d_std,
                "fade_mean": f_mean,
                "fade_std": f_std,
                "effective_single_type_dominance_threshold": eff_single_type_threshold,
                "effective_downgrade_jump_threshold": eff_downgrade_jump_threshold,
                "effective_fade_jump_threshold": eff_fade_jump_threshold,
                "min_history_days": min_history_days,
                "auto_tune_enabled": (not disable_auto_tune),
            },
        }


async def main_async() -> int:
    args = parse_args()
    trade_date = date.fromisoformat(args.trade_date)

    checker = MainlineTransitionDistributionChecker()
    await checker.connect()
    try:
        result = await checker.run(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
            min_total=args.min_total,
            single_type_dominance_threshold=args.single_type_dominance_threshold,
            downgrade_jump_threshold=args.downgrade_jump_threshold,
            fade_jump_threshold=args.fade_jump_threshold,
            min_history_days=max(1, args.min_history_days),
            disable_auto_tune=args.disable_auto_tune,
        )
    finally:
        await checker.close()

    cur = result.get("current")
    if cur:
        print(
            "[current] date={date} total={total} ratios={ratios}".format(
                date=cur.trade_date.isoformat(),
                total=cur.total,
                ratios=json.dumps(cur.ratios, ensure_ascii=False),
            )
        )
    print(
        "[history] days={days} baseline={baseline}".format(
            days=result.get("history_days"),
            baseline=json.dumps(result.get("history_baseline") or {}, ensure_ascii=False),
        )
    )

    alerts = result.get("alerts") or []
    if alerts:
        print("[alerts]")
        for item in alerts:
            print(f"- {item}")
    else:
        print("[alerts] none")

    if alerts and args.fail_on_alert:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
