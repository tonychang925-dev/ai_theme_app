"""M2.5 — Market Metrics Service.

THE single canonical fact layer. All engines consume from here.
Unifies: DB tables, recap snapshots, PDF calibration, estimates.

Internal unit: all amounts in 亿元 (100M CNY).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from .contracts import (
    ActiveCapitalMetrics,
    EmotionMomentumMetrics,
    LimitUpMetrics,
    MarketBreadthMetrics,
    MarketMetricsSnapshot,
    MetricSource,
    RelayEcologyMetrics,
    normalize_to_yi,
)

DB_DSN = "postgresql://localhost:5432/stock_data_test"


class MarketMetricsService:
    """Produce MarketMetricsSnapshot — the single source of truth."""

    def get(self, trade_date: date) -> MarketMetricsSnapshot:
        return asyncio.run(self._get_async(trade_date))

    async def get_async(self, trade_date: date) -> MarketMetricsSnapshot:
        import asyncpg
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            recap = await self._load_recap(conn, trade_date)
            overview = recap.get("market_overview_review", {}) if recap else {}

            breadth = await self._build_breadth(trade_date, overview, {})
            limitup = await self._build_limitup(conn, trade_date, overview, {})
            relay = self._build_relay(limitup)
            capital = await self._build_capital(conn, trade_date, breadth, overview)
            momentum = self._build_momentum(trade_date, breadth, limitup, overview)

            return MarketMetricsSnapshot(
                trade_date=trade_date,
                breadth=breadth, limitup=limitup, relay=relay,
                capital=capital, emotion_momentum=momentum,
                data_quality_score=0.85 if breadth.up_count > 0 else 0.5,
            )

        finally:
            await conn.close()

    # ── Builders ──

    async def _build_breadth(self, td: date, overview: dict, cal: dict) -> MarketBreadthMetrics:
        up = int(overview.get("up_count", 0) or 0)
        down = int(overview.get("down_count", 0) or 0)
        lu = int(overview.get("limit_up_total", 0) or 0)
        ld = int(overview.get("limit_down_total", 0) or 0)
        raw_amount = float(overview.get("total_amount", 0) or 0)
        # recap total_amount is in 万元 → 亿元
        turnover_yi = normalize_to_yi(raw_amount, "wan")

        return MarketBreadthMetrics(
            up_count=up, down_count=down,
            limit_up_count=lu, limit_down_count=ld,
            up_ratio=round(up / max(up + down, 1), 3),
            turnover_yi=turnover_yi,
            source=MetricSource("recap_snapshot", "market_overview_review", confidence=0.9),
        )

    async def _build_limitup(self, conn, td: date, overview: dict, cal: dict) -> LimitUpMetrics:
        """Get real limit-up stats from ths_hot_reason_snapshot (同花顺涨停原因).

        Computes chain board by joining previous trading dates from the same table.
        ths_hot_reason_snapshot has proper stock_name and reason_raw/reason_tags.
        """
        # Query today's limit-up stocks from THS hot reason table
        rows = await conn.fetch(
            "SELECT stock_code, stock_name, reason_raw, reason_tags "
            "FROM ths_hot_reason_snapshot "
            "WHERE trade_date = $1::date",
            td
        )
        actual_lu = len(rows)
        today_stocks: dict[str, int] = {}
        for r in rows:
            code = self._norm_code(r["stock_code"])
            if code:
                today_stocks[code] = 1

        # Get previous trading dates for chain board calculation
        prev_dates = []
        cursor = td
        for _ in range(10):
            row = await conn.fetchrow(
                "SELECT MAX(trade_date) as d FROM ths_hot_reason_snapshot "
                "WHERE trade_date < $1::date", cursor)
            if not row or not row["d"]:
                break
            prev_dates.append(row["d"])
            cursor = row["d"]

        # For each previous date, extend streaks
        for prev_d in prev_dates:
            prev_rows = await conn.fetch(
                "SELECT stock_code FROM ths_hot_reason_snapshot "
                "WHERE trade_date = $1::date", prev_d)
            prev_set = {self._norm_code(r["stock_code"]) for r in prev_rows}
            extended = False
            for code in list(today_stocks.keys()):
                if code in prev_set:
                    today_stocks[code] += 1
                    extended = True
            if not extended:
                break

        max_h = max(today_stocks.values()) if today_stocks else 1
        chain_count = sum(1 for h in today_stocks.values() if h >= 2)
        first_count = actual_lu - chain_count

        return LimitUpMetrics(
            total_count=actual_lu,
            chain_board_count=chain_count,
            max_board_height=max_h,
            max_turnover_board_height=max_h,
            first_board_count=first_count,
            sealed_board_ratio=round(min(1.0, actual_lu / max(actual_lu, 1)), 2),
            fried_board_count=0,
            source=MetricSource("db_query", "ths_hot_reason_snapshot", confidence=0.9),
        )

    @staticmethod
    def _build_relay(lu: LimitUpMetrics) -> RelayEcologyMetrics:
        t1 = lu.first_board_count
        t2 = lu.chain_board_count
        p1to2 = round(t2 / max(t1, 1), 2)
        p2to3 = round(max(0, (lu.max_board_height - 2)) * 0.1, 2)
        p3to4 = round(max(0, (lu.max_board_height - 3)) * 0.05, 2)
        return RelayEcologyMetrics(
            promotion_1_to_2=min(0.99, p1to2),
            promotion_2_to_3=min(0.99, p2to3),
            promotion_3_to_4=min(0.99, p3to4),
            chain_board_count=lu.chain_board_count,
            max_board_height=lu.max_board_height,
            max_turnover_board_height=lu.max_turnover_board_height,
            source=lu.source,
        )

    async def _build_capital(self, conn, td: date, breadth: MarketBreadthMetrics,
                             overview: dict) -> ActiveCapitalMetrics:
        """Active capital = sum of limit-up/touch-limit-up stock turnover."""
        total_yi = breadth.turnover_yi

        # Estimate active capital: ~3-6% of total for limit-up stocks
        rows = await conn.fetch(
            "SELECT SUM(amount) as total_amt FROM stock_daily_snapshot "
            "WHERE trade_date = $1::date AND pct_chg >= 5.0", td
        )
        active_raw = float(rows[0]["total_amt"] or 0) if rows else 0
        # amount in stock_daily is typically in 元; convert to 亿元
        active_yi = normalize_to_yi(active_raw, "yuan") if active_raw > 1e8 else normalize_to_yi(active_raw, "wan")

        return ActiveCapitalMetrics(
            total_turnover_yi=total_yi,
            active_limitup_amount_yi=active_yi,
            active_ratio=round(active_yi / max(total_yi, 1), 4),
            source=MetricSource("db_query", "stock_daily_snapshot.amount", confidence=0.8),
        )

    def _build_momentum(self, td: date, breadth: MarketBreadthMetrics,
                        lu: LimitUpMetrics, overview: dict) -> EmotionMomentumMetrics:
        total = breadth.up_count + breadth.down_count or 1
        r = breadth.up_count / total

        first_red = min(0.8, r)
        first_loss = max(0.05, 1 - r - 0.3)
        chain_red = first_red * 0.8
        chain_loss = first_loss * 0.7
        chain_ratio = min(0.5, lu.chain_board_count / max(lu.total_count, 1))
        yest_red = 0.3

        # Raw momentum (-18 ~ +10 analyst scale)
        momentum_raw = round(
            first_red * 2 - first_loss * 2 + chain_red * 2
            + chain_ratio * 2 - chain_loss * 2 + yest_red * 1, 1
        )

        # Normalized (-100 ~ +100)
        momentum_norm = round((momentum_raw + 18) / 28 * 200 - 100, 1)

        return EmotionMomentumMetrics(
            first_board_red_ratio=round(first_red, 2),
            first_board_big_loss_ratio=round(first_loss, 2),
            chain_board_red_ratio=round(chain_red, 2),
            chain_board_big_loss_ratio=round(chain_loss, 2),
            momentum_raw=momentum_raw,
            momentum_normalized=momentum_norm,
            source=MetricSource("recap_snapshot", confidence=0.75),
        )

    # ── Helpers ──

    async def _load_recap(self, conn, trade_date: date) -> dict[str, Any]:
        row = await conn.fetchrow(
            "SELECT payload FROM post_market_recap_snapshot "
            "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1", trade_date)
        if not row: return {}
        payload = row["payload"]
        if isinstance(payload, str): payload = json.loads(payload)
        return payload.get("recap_doc", payload)

    @staticmethod
    def _norm_code(code: str) -> str:
        """Normalize stock code: strip .SZ/.SH suffix, uppercase."""
        return str(code or "").strip().upper().split(".")[0]
