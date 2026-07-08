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

# PDF paths for analyst calibration
PDF_PATHS: dict[str, dict[str, Any]] = {
    "2026-07-07": {
        "path": "/Users/admin/Desktop/7:7日复盘.pdf",
        "limit_up": 33,
        "turnover_wan_yi": 2.5,   # 2.5万亿
        "emotion": "情绪冰点",
        "max_turnover_board": "宜宾纸业",
    },
}


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
            calibration = PDF_PATHS.get(trade_date.isoformat(), {})

            # ── Breadth ──
            breadth = await self._build_breadth(trade_date, overview, calibration)

            # ── Limit-up ──
            limitup = await self._build_limitup(conn, trade_date, overview, calibration)

            # ── Relay Ecology ──
            relay = self._build_relay(limitup)

            # ── Active Capital ──
            capital = await self._build_capital(conn, trade_date, breadth, overview)

            # ── Emotion Momentum ──
            momentum = self._build_momentum(trade_date, breadth, limitup, overview)

            # ── Fund Flow ──
            # (placeholder — requires fund_flow table)

            # Build calibrated fields list
            calibrated_fields: list[str] = []
            if calibration.get("limit_up"):
                calibrated_fields.append("limit_up_count")
            if calibration.get("turnover_wan_yi"):
                calibrated_fields.append("turnover_yi")
            if calibration.get("emotion"):
                calibrated_fields.append("emotion_node")

            return MarketMetricsSnapshot(
                trade_date=trade_date,
                breadth=breadth,
                limitup=limitup,
                relay=relay,
                capital=capital,
                emotion_momentum=momentum,
                calibration_applied=bool(calibration),
                calibration_source="analyst_pdf" if calibration else "",
                calibration_fields=tuple(calibrated_fields),
                data_quality_score=0.85 if breadth.up_count > 0 else 0.5,
            )

        finally:
            await conn.close()

    # ── Builders ──

    async def _build_breadth(self, td: date, overview: dict, cal: dict) -> MarketBreadthMetrics:
        up = int(overview.get("up_count", 0) or 0)
        down = int(overview.get("down_count", 0) or 0)
        lu_raw = int(overview.get("limit_up_total", 0) or 0)
        ld = int(overview.get("limit_down_total", 0) or 0)
        raw_amount = float(overview.get("total_amount", 0) or 0)

        # PDF calibration overrides
        lu = cal.get("limit_up", lu_raw)
        if cal.get("turnover_wan_yi"):
            turnover_yi = normalize_to_yi(cal["turnover_wan_yi"], "wan_yi")
        else:
            # recap total_amount is in 万元 → convert to 亿元
            turnover_yi = normalize_to_yi(raw_amount, "wan")

        is_cal = lu != lu_raw or cal.get("turnover_wan_yi")

        return MarketBreadthMetrics(
            up_count=up, down_count=down,
            limit_up_count=lu, limit_down_count=ld,
            up_ratio=round(up / max(up + down, 1), 3),
            turnover_yi=turnover_yi,
            source=MetricSource(
                "recap_snapshot" if not is_cal else "pdf_calibrated",
                "market_overview_review",
                confidence=0.9,
                is_calibrated=is_cal,
            ),
        )

    async def _build_limitup(self, conn, td: date, overview: dict, cal: dict) -> LimitUpMetrics:
        """Get real limit-up and chain board stats from stock_daily_snapshot."""
        lu_total = cal.get("limit_up") or int(overview.get("limit_up_total", 0) or 0)

        # Query real data: stocks with pct_chg >= 9.5
        rows = await conn.fetch(
            "SELECT stock_id, stock_name, pct_chg FROM stock_daily_snapshot "
            "WHERE trade_date = $1::date AND pct_chg >= 9.5 "
            "ORDER BY pct_chg DESC", td
        )
        actual_lu = len(rows)

        # Chain board: check if stock was also limit-up yesterday
        chain_count = 0
        max_h = 1
        if actual_lu > 0:
            yesterday_date = await self._prev_trade_date(conn, td)
            if yesterday_date:
                y_rows = await conn.fetch(
                    "SELECT stock_id FROM stock_daily_snapshot "
                    "WHERE trade_date = $1::date AND pct_chg >= 9.5", yesterday_date
                )
                y_set = {r["stock_id"] for r in y_rows}
                for r in rows:
                    if r["stock_id"] in y_set:
                        chain_count += 1
                # 3板+: check 2 days ago
                if chain_count > 0:
                    day3 = await self._prev_trade_date(conn, yesterday_date)
                    if day3:
                        d3_set = {r["stock_id"] for r in await conn.fetch(
                            "SELECT stock_id FROM stock_daily_snapshot "
                            "WHERE trade_date = $1::date AND pct_chg >= 9.5", day3
                        )}
                        for r in rows:
                            if r["stock_id"] in y_set and r["stock_id"] in d3_set:
                                max_h = max(max_h, 3)
                if chain_count > 0:
                    max_h = max(max_h, 2)

        # Use calibrated LU if available, otherwise use actual query count
        lu_final = cal.get("limit_up", actual_lu or lu_total)
        max_turnover_h = max(1, max_h)
        first_count = max(0, lu_final - chain_count)

        return LimitUpMetrics(
            total_count=lu_final,
            chain_board_count=chain_count,
            max_board_height=max_h,
            max_turnover_board_height=max_turnover_h,
            first_board_count=first_count,
            sealed_board_ratio=round(min(1.0, actual_lu / max(lu_final, 1)), 2) if lu_final else 0.7,
            fried_board_count=max(0, lu_final - actual_lu),
            source=MetricSource(
                "db_query" if not cal.get("limit_up") else "pdf_calibrated",
                "stock_daily_snapshot",
                confidence=0.85,
                is_calibrated=bool(cal.get("limit_up")),
            ),
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

    async def _prev_trade_date(self, conn, trade_date: date):
        row = await conn.fetchrow(
            "SELECT MAX(trade_date) as d FROM post_market_recap_snapshot "
            "WHERE trade_date < $1::date", trade_date)
        return row["d"] if row else None
