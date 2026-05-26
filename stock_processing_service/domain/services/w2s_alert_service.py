"""P1-I-1: 竞价弱转强确认告警服务。

读取 D1 弱转强候选池 + 竞价快照数据，
筛选 A/B 级确认候选，生成 w2s_auction_alert。

数据流:
  weak_to_strong_candidate_pool (D1候选)
  + pre_market_auction_snapshot (竞价快照)
  → W2SAuctionAlert (A/B 级)
  → Redis Stream: stream:w2s:alerts
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_alert")

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class W2SAuctionAlert:
    trade_date: str
    candidate_trade_date: str
    candidate_id: int
    stock_id: str
    stock_name: str
    theme_name: str
    candidate_type: str
    weak_type: str
    confirm_level: str        # A / B / C
    confirm_score: float
    auction_open_pct: float
    carry_ratio: float
    last_minute_ratio: float
    price_path_stability_score: float
    shape_features: list[str]
    severity: str             # important / observe
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class W2SAlertResult:
    alerts: list[W2SAuctionAlert]
    total_candidates: int
    level_a_count: int
    level_b_count: int
    level_c_count: int


class W2SAlertService:
    """竞价弱转强确认告警服务。"""

    # 告警等级 → 评分阈值
    LEVEL_A_SCORE = 75.0
    LEVEL_B_SCORE = 55.0

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    async def load_candidates_with_auction(
        self, candidate_trade_date: str,
    ) -> list[dict[str, Any]]:
        """加载 D1 候选 + 竞价快照，stock_id 格式统一。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT
                 c.id AS candidate_id,
                 c.stock_id,
                 c.stock_name,
                 COALESCE(c.theme_name, '') AS theme_name,
                 c.candidate_type,
                 c.weak_type,
                 c.trade_date AS candidate_trade_date,
                 c.next_trade_date,
                 a.auction_open_pct,
                 a.carry_ratio,
                 a.last_minute_ratio,
                 a.price_path_stability_score,
                 a.shape_features,
                 a.auction_open_price,
                 a.auction_amount,
                 a.has_end_spike,
                 a.has_end_drop
               FROM weak_to_strong_candidate_pool c
               LEFT JOIN pre_market_auction_snapshot a
                 ON a.trade_date = c.next_trade_date
                 AND (a.stock_id = c.stock_id
                      OR a.stock_id = split_part(c.stock_id, '.', 1))
               WHERE c.trade_date = $1::date
               ORDER BY c.candidate_score DESC""",
            date.fromisoformat(candidate_trade_date),
        )
        return [dict(r) for r in rows]

    def score_auction(self, row: dict[str, Any]) -> tuple[str, float]:
        """简化竞价评分: open_pct + carry + stability → A/B/C。"""
        score = 0.0
        open_pct = float(row.get("auction_open_pct") or 0)
        carry = float(row.get("carry_ratio") or 0)
        stability = float(row.get("price_path_stability_score") or 0)
        last_min = float(row.get("last_minute_ratio") or 0)
        has_spike = bool(row.get("has_end_spike"))
        has_drop = bool(row.get("has_end_drop"))

        # 竞价涨幅 (0-30)
        if open_pct >= 5:
            score += 30
        elif open_pct >= 3:
            score += 22
        elif open_pct >= 1:
            score += 14
        elif open_pct >= 0:
            score += 7
        elif open_pct >= -2:
            score += 3

        # 承接比 (0-30)
        if carry >= 1.0:
            score += 30
        elif carry >= 0.5:
            score += 20
        elif carry >= 0.2:
            score += 10

        # 稳定性 (0-25)
        if stability >= 70:
            score += 25
        elif stability >= 50:
            score += 15
        elif stability >= 30:
            score += 8

        # 尾端抢筹 (0-15)
        if last_min >= 0.3:
            score += 15
        elif last_min >= 0.15:
            score += 8

        # 形态惩罚
        if has_drop:
            score -= 10
        if has_spike:
            score += 5

        score = max(0, min(100, score))
        if score >= self.LEVEL_A_SCORE:
            return ("A", round(score, 1))
        elif score >= self.LEVEL_B_SCORE:
            return ("B", round(score, 1))
        return ("C", round(score, 1))

    async def build_alerts(self, candidate_trade_date: str) -> W2SAlertResult:
        """构建竞价弱转强告警列表。"""
        rows = await self.load_candidates_with_auction(candidate_trade_date)
        now_str = datetime.now(TZ_CN).isoformat()
        alerts: list[W2SAuctionAlert] = []
        level_counts = {"A": 0, "B": 0, "C": 0}

        for row in rows:
            cid = row.get("candidate_id")
            if not cid:
                continue

            # 计算竞价确认等级
            level, score = self.score_auction(row)
            level_counts[level] = level_counts.get(level, 0) + 1

            # C 级不推送正式告警
            if level not in ("A", "B"):
                continue

            shape_raw = row.get("shape_features")
            if isinstance(shape_raw, list):
                shapes = [str(s) for s in shape_raw]
            elif isinstance(shape_raw, str):
                import json
                try:
                    shapes = json.loads(shape_raw)
                except Exception:
                    shapes = [s.strip() for s in shape_raw.split(",") if s.strip()]
            else:
                shapes = []

            alerts.append(W2SAuctionAlert(
                trade_date=str(row.get("next_trade_date") or "")[:10],
                candidate_trade_date=candidate_trade_date,
                candidate_id=int(cid),
                stock_id=str(row.get("stock_id") or ""),
                stock_name=str(row.get("stock_name") or ""),
                theme_name=str(row.get("theme_name") or ""),
                candidate_type=str(row.get("candidate_type") or ""),
                weak_type=str(row.get("weak_type") or ""),
                confirm_level=level,
                confirm_score=score,
                auction_open_pct=round(float(row.get("auction_open_pct") or 0), 2),
                carry_ratio=round(float(row.get("carry_ratio") or 0), 3),
                last_minute_ratio=round(float(row.get("last_minute_ratio") or 0), 3),
                price_path_stability_score=round(float(row.get("price_path_stability_score") or 0), 1),
                shape_features=shapes,
                severity="important",
                generated_at=now_str,
                extra={
                    "auction_open_price": float(row.get("auction_open_price") or 0),
                    "auction_amount": float(row.get("auction_amount") or 0),
                    "has_end_spike": bool(row.get("has_end_spike")),
                    "has_end_drop": bool(row.get("has_end_drop")),
                },
            ))

        return W2SAlertResult(
            alerts=alerts,
            total_candidates=len(rows),
            level_a_count=level_counts.get("A", 0),
            level_b_count=level_counts.get("B", 0),
            level_c_count=level_counts.get("C", 0),
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
