#!/usr/bin/env python3
"""
主线周期状态分布监控脚本

用途：
- 检查指定交易日 theme_cycle_judgement_v2 的状态分布是否异常集中
- 对比历史窗口均值，识别 fade_confirmed 异常抬升、mainline_alive 异常下滑
- 可作为定时任务告警前置检查

用法：
  python stock_service/scripts/check_cycle_state_distribution.py --trade-date 2026-04-07
  python stock_service/scripts/check_cycle_state_distribution.py --trade-date 2026-04-07 --fail-on-alert
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
class DayDistribution:
    trade_date: date
    total: int
    mainline_alive_ratio: float
    fade_confirmed_ratio: float
    state_ratios: Dict[str, float]
    source_table: str = "theme_cycle_judgement_v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查主题周期状态分布异常")
    parser.add_argument("--trade-date", required=True, help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=20, help="历史基线窗口天数，默认20")
    parser.add_argument("--min-total", type=int, default=80, help="最小样本数阈值，默认80")
    parser.add_argument("--dominance-threshold", type=float, default=0.78, help="单状态集中度阈值，默认0.78")
    parser.add_argument(
        "--fade-confirmed-jump-threshold",
        type=float,
        default=0.08,
        help="fade_confirmed 相对历史均值的绝对抬升阈值，默认0.08",
    )
    parser.add_argument(
        "--mainline-alive-drop-threshold",
        type=float,
        default=0.15,
        help="mainline_alive 相对历史均值的绝对下滑阈值，默认0.15",
    )
    parser.add_argument("--fail-on-alert", action="store_true", help="出现告警时返回非0退出码")
    return parser.parse_args()


class CycleStateDistributionChecker:
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

    async def _fetch_day_distribution(self, trade_date: date) -> Optional[DayDistribution]:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            total = int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM theme_cycle_judgement_v2
                    WHERE trade_date = $1::date
                    """,
                    trade_date,
                )
                or 0
            )
            if total <= 0:
                return None

            alive_ratio = float(
                await conn.fetchval(
                    """
                    SELECT COALESCE(AVG(CASE WHEN final_mainline_alive THEN 1.0 ELSE 0.0 END), 0.0)
                    FROM theme_cycle_judgement_v2
                    WHERE trade_date = $1::date
                    """,
                    trade_date,
                )
                or 0.0
            )
            fade_confirmed_ratio = float(
                await conn.fetchval(
                    """
                    SELECT COALESCE(AVG(CASE WHEN fade_confirmed THEN 1.0 ELSE 0.0 END), 0.0)
                    FROM theme_cycle_judgement_v2
                    WHERE trade_date = $1::date
                    """,
                    trade_date,
                )
                or 0.0
            )
            rows = await conn.fetch(
                """
                SELECT final_cycle_state, COUNT(*) AS cnt
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $1::date
                GROUP BY final_cycle_state
                """,
                trade_date,
            )
            ratios: Dict[str, float] = {}
            for row in rows:
                state = str(row["final_cycle_state"] or "unknown")
                ratios[state] = int(row["cnt"]) / float(total)
            return DayDistribution(
                trade_date=trade_date,
                total=total,
                mainline_alive_ratio=alive_ratio,
                fade_confirmed_ratio=fade_confirmed_ratio,
                state_ratios=ratios,
                source_table="theme_cycle_judgement_v2",
            )

    async def _fetch_history(
        self,
        trade_date: date,
        lookback_days: int,
        min_total: int,
    ) -> List[DayDistribution]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH daily_total AS (
                    SELECT
                        trade_date,
                        COUNT(*) AS total,
                        AVG(CASE WHEN final_mainline_alive THEN 1.0 ELSE 0.0 END) AS alive_ratio,
                        AVG(CASE WHEN fade_confirmed THEN 1.0 ELSE 0.0 END) AS fc_ratio
                    FROM theme_cycle_judgement_v2
                    WHERE trade_date < $1::date
                      AND trade_date >= ($1::date - ($2 * INTERVAL '1 day'))
                    GROUP BY trade_date
                    HAVING COUNT(*) >= $3
                ),
                daily_state AS (
                    SELECT
                        trade_date,
                        final_cycle_state,
                        COUNT(*) AS cnt
                    FROM theme_cycle_judgement_v2
                    WHERE trade_date < $1::date
                      AND trade_date >= ($1::date - ($2 * INTERVAL '1 day'))
                    GROUP BY trade_date, final_cycle_state
                )
                SELECT
                    t.trade_date,
                    t.total,
                    t.alive_ratio,
                    t.fc_ratio,
                    COALESCE(
                        jsonb_object_agg(
                            s.final_cycle_state,
                            ROUND((s.cnt::numeric / NULLIF(t.total, 0)::numeric), 6)
                        ) FILTER (WHERE s.final_cycle_state IS NOT NULL),
                        '{}'::jsonb
                    ) AS ratios
                FROM daily_total t
                LEFT JOIN daily_state s ON s.trade_date = t.trade_date
                GROUP BY t.trade_date, t.total, t.alive_ratio, t.fc_ratio
                ORDER BY t.trade_date ASC
                """,
                trade_date,
                lookback_days,
                min_total,
            )
        history: List[DayDistribution] = []
        for row in rows:
            raw_ratios = row["ratios"] or {}
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
                DayDistribution(
                    trade_date=row["trade_date"],
                    total=int(row["total"] or 0),
                    mainline_alive_ratio=float(row["alive_ratio"] or 0.0),
                    fade_confirmed_ratio=float(row["fc_ratio"] or 0.0),
                    state_ratios=ratios,
                )
            )
        return history

    def _ratio_stats(self, values: List[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        return mean(values), pstdev(values) if len(values) > 1 else 0.0

    async def run(
        self,
        trade_date: date,
        lookback_days: int,
        min_total: int,
        dominance_threshold: float,
        fade_confirmed_jump_threshold: float,
        mainline_alive_drop_threshold: float,
    ) -> Dict[str, Any]:
        current = await self._fetch_day_distribution(trade_date)
        if current is None:
            return {
                "ok": False,
                "alerts": [f"{trade_date.isoformat()} 在 theme_cycle_judgement_v2 无数据"],
                "current": None,
                "history_days": 0,
            }

        history = await self._fetch_history(trade_date, lookback_days, min_total)
        alerts: List[str] = []

        # 1) 单状态过度集中告警
        if current.total >= min_total and current.state_ratios:
            top_state, top_ratio = max(current.state_ratios.items(), key=lambda kv: kv[1])
            if top_ratio >= dominance_threshold:
                alerts.append(
                    f"状态集中度异常: top_state={top_state}, ratio={top_ratio:.3f} >= {dominance_threshold:.3f}"
                )

        # 2) fade_confirmed 抬升告警（对历史窗口）
        hist_fc_values = [d.fade_confirmed_ratio for d in history]
        hist_fc_mean, hist_fc_std = self._ratio_stats(hist_fc_values)
        cur_fc = current.fade_confirmed_ratio
        if history and (
            (cur_fc - hist_fc_mean) >= fade_confirmed_jump_threshold
            or (hist_fc_std > 0 and cur_fc >= hist_fc_mean + 2.0 * hist_fc_std)
        ):
            alerts.append(
                f"fade_confirmed 异常抬升: current={cur_fc:.3f}, hist_mean={hist_fc_mean:.3f}, hist_std={hist_fc_std:.3f}"
            )

        # 3) mainline_alive 异常下滑告警
        alive_values = [d.mainline_alive_ratio for d in history]
        hist_alive_mean, hist_alive_std = self._ratio_stats(alive_values)
        if history and (
            (hist_alive_mean - current.mainline_alive_ratio) >= mainline_alive_drop_threshold
            or (hist_alive_std > 0 and current.mainline_alive_ratio <= hist_alive_mean - 2.0 * hist_alive_std)
        ):
            alerts.append(
                f"mainline_alive 异常下滑: current={current.mainline_alive_ratio:.3f}, hist_mean={hist_alive_mean:.3f}, hist_std={hist_alive_std:.3f}"
            )

        return {
            "ok": len(alerts) == 0,
            "alerts": alerts,
            "current": current,
            "history_days": len(history),
            "history_baseline": {
                "fade_confirmed_mean": hist_fc_mean,
                "fade_confirmed_std": hist_fc_std,
                "mainline_alive_mean": hist_alive_mean,
                "mainline_alive_std": hist_alive_std,
            },
        }


async def main_async() -> int:
    args = parse_args()
    trade_date = date.fromisoformat(args.trade_date)
    checker = CycleStateDistributionChecker()
    await checker.connect()
    try:
        result = await checker.run(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
            min_total=args.min_total,
            dominance_threshold=args.dominance_threshold,
            fade_confirmed_jump_threshold=args.fade_confirmed_jump_threshold,
            mainline_alive_drop_threshold=args.mainline_alive_drop_threshold,
        )
    finally:
        await checker.close()

    current = result.get("current")
    print(f"[DATE] {trade_date.isoformat()}")
    if current:
        print(
            f"[CURRENT] source={current.source_table} total={current.total} mainline_alive_ratio={current.mainline_alive_ratio:.3f} "
            f"fade_confirmed_ratio={current.fade_confirmed_ratio:.3f}"
        )
        top_items = sorted(current.state_ratios.items(), key=lambda kv: kv[1], reverse=True)[:8]
        print("[CURRENT_STATES]")
        for state, ratio in top_items:
            print(f"  - {state}: {ratio:.3f}")
    else:
        print("[CURRENT] no_data")

    print(f"[HISTORY] days={result.get('history_days', 0)}")
    baseline = result.get("history_baseline") or {}
    if baseline:
        print(
            "[BASELINE] "
            f"fade_confirmed_mean={baseline.get('fade_confirmed_mean', 0.0):.3f} "
            f"fade_confirmed_std={baseline.get('fade_confirmed_std', 0.0):.3f} "
            f"mainline_alive_mean={baseline.get('mainline_alive_mean', 0.0):.3f} "
            f"mainline_alive_std={baseline.get('mainline_alive_std', 0.0):.3f}"
        )

    alerts = result.get("alerts") or []
    if alerts:
        print("[ALERTS]")
        for item in alerts:
            print(f"  - {item}")
    else:
        print("[ALERTS] none")

    if args.fail_on_alert and alerts:
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
