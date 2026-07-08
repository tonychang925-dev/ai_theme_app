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

    def get_range(self, start_date: date, end_date: date) -> list[MarketMetricsSnapshot]:
        """Batch fetch snapshots for trend charts."""
        return asyncio.run(self._get_range_async(start_date, end_date))

    async def get_async(self, trade_date: date) -> MarketMetricsSnapshot:
        import asyncpg
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            return await self._get_async_with_conn(conn, trade_date)
        finally:
            await conn.close()

    async def _get_range_async(self, start_date: date, end_date: date) -> list[MarketMetricsSnapshot]:
        """Batch fetch snapshots for a date range. Used by trend charts."""
        import asyncpg
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            # Get all trading dates in range from ths_hot_reason_snapshot
            rows = await conn.fetch(
                "SELECT DISTINCT trade_date FROM ths_hot_reason_snapshot "
                "WHERE trade_date >= $1::date AND trade_date <= $2::date "
                "ORDER BY trade_date",
                start_date, end_date,
            )
            dates = [r["trade_date"] for r in rows]
            snapshots = []
            for td in dates:
                try:
                    snap = await self._get_async_with_conn(conn, td)
                    snapshots.append(snap)
                except Exception:
                    continue
            return snapshots
        finally:
            await conn.close()

    async def _get_async_with_conn(self, conn, trade_date: date) -> MarketMetricsSnapshot:
        """Same as get_async but reuses an existing connection."""
        recap = await self._load_recap(conn, trade_date)
        overview = recap.get("market_overview_review", {}) if recap else {}

        breadth = await self._build_breadth(trade_date, overview, {})
        limitup, streak_dist = await self._build_limitup(conn, trade_date, overview, {})
        relay = self._build_relay(limitup, streak_dist)
        capital = await self._build_capital(conn, trade_date, breadth, overview)
        momentum = self._build_momentum(breadth, limitup)

        return MarketMetricsSnapshot(
            trade_date=trade_date,
            breadth=breadth, limitup=limitup, relay=relay,
            capital=capital, emotion_momentum=momentum,
            data_quality_score=0.85 if breadth.up_count > 0 else 0.5,
        )

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

    # ── Limit threshold by board type ──

    @staticmethod
    def _limit_threshold(stock_code: str, stock_name: str = "") -> float:
        """Return the expected limit-up pct_chg for sealed detection.

        Threshold is slightly below the actual limit to account for
        rounding and minor intra-day deviations.
        """
        name_upper = (stock_name or "").upper().strip()
        code = (stock_code or "").strip()

        # ST stocks: 5% limit
        if "ST" in name_upper:
            return 4.5

        # 科创板 STAR Market: 20% limit (688xxx, 689xxx)
        if len(code) >= 3 and code[:3] in ("688", "689"):
            return 19.5

        # 创业板 ChiNext: 20% limit (300xxx, 301xxx)
        if len(code) >= 3 and code[:3] in ("300", "301"):
            return 19.5

        # 北交所 Beijing Stock Exchange: 30% limit (8xx, 4xx)
        if code and code[0] in ("8", "4"):
            return 29.5

        # 主板 Main Board: 10% limit
        return 9.5

    @staticmethod
    def _board_class(stock_code: str, stock_name: str = "") -> str:
        """Classify a stock by board type for metrics breakdown."""
        name_upper = (stock_name or "").upper().strip()
        code = (stock_code or "").strip()

        if "ST" in name_upper:
            return "ST"

        if len(code) >= 3 and code[:3] in ("688", "689"):
            return "科创板"
        if len(code) >= 3 and code[:3] in ("300", "301"):
            return "创业板"
        if code and code[0] in ("8", "4"):
            return "北交所"
        return "主板"

    async def _build_limitup(self, conn, td: date, overview: dict, cal: dict) -> tuple[LimitUpMetrics, dict[int, int]]:
        """Build real LimitUpMetrics from ths_hot_reason_snapshot.

        Uses pct_chg to classify sealed vs fried per stock, with
        threshold varying by board type (主板 10%, 创业板/科创 20%, ST 5%).
        """
        rows = await conn.fetch(
            "SELECT stock_code, stock_name, reason_raw, reason_tags, "
            "       pct_chg, turnover_rate, amount, big_order_net "
            "FROM ths_hot_reason_snapshot "
            "WHERE trade_date = $1::date",
            td,
        )

        # ── Per-stock classification ──
        sealed_codes: set[str] = set()
        fried_codes: set[str] = set()
        all_codes: set[str] = set()

        sealed_turnovers: list[float] = []
        sealed_amounts: list[float] = []      # raw amounts (元 from THS API)
        sealed_big_orders: list[float] = []
        fried_amounts: list[float] = []

        board_type_counts: dict[str, int] = {}

        for r in rows:
            code = self._norm_code(r["stock_code"])
            if not code:
                continue
            all_codes.add(code)

            stock_name = str(r["stock_name"] or "")
            pct = float(r["pct_chg"] or 0)
            turnover = float(r["turnover_rate"] or 0)
            raw_amount = float(r["amount"] or 0)
            big_order = float(r["big_order_net"] or 0)

            threshold = self._limit_threshold(code, stock_name)
            board = self._board_class(code, stock_name)
            board_type_counts[board] = board_type_counts.get(board, 0) + 1

            if pct >= threshold:
                sealed_codes.add(code)
                if turnover > 0:
                    sealed_turnovers.append(turnover)
                if raw_amount > 0:
                    sealed_amounts.append(raw_amount)
                if big_order != 0:
                    sealed_big_orders.append(big_order)
            else:
                fried_codes.add(code)
                if raw_amount > 0:
                    fried_amounts.append(raw_amount)

        total = len(all_codes)
        sealed = len(sealed_codes)
        fried = len(fried_codes)

        # ── Streak calculation (chain board) ──
        today_streaks: dict[str, int] = {code: 1 for code in all_codes}

        prev_dates: list[date] = []
        cursor = td
        for _ in range(10):
            row = await conn.fetchrow(
                "SELECT MAX(trade_date) as d FROM ths_hot_reason_snapshot "
                "WHERE trade_date < $1::date", cursor)
            if not row or not row["d"]:
                break
            prev_dates.append(row["d"])
            cursor = row["d"]

        for prev_d in prev_dates:
            prev_rows = await conn.fetch(
                "SELECT stock_code FROM ths_hot_reason_snapshot "
                "WHERE trade_date = $1::date", prev_d)
            prev_set = {self._norm_code(r["stock_code"]) for r in prev_rows}
            extended = False
            for code in list(today_streaks.keys()):
                if code in prev_set:
                    today_streaks[code] += 1
                    extended = True
            if not extended:
                break

        max_h = max(today_streaks.values()) if today_streaks else 1
        chain_count = sum(1 for h in today_streaks.values() if h >= 2)
        first_count = total - chain_count
        high_board = sum(1 for h in today_streaks.values() if h >= 3)

        # ── Streak distribution for relay ──
        streak_dist: dict[int, int] = {}
        for h in today_streaks.values():
            streak_dist[h] = streak_dist.get(h, 0) + 1
        streak_dist.setdefault(1, first_count)
        streak_dist.setdefault(2, 0)
        streak_dist.setdefault(3, 0)
        streak_dist.setdefault(4, 0)

        # ── Board quality aggregates ──
        avg_turnover = round(sum(sealed_turnovers) / max(len(sealed_turnovers), 1), 2) if sealed_turnovers else None

        # Amount from THS API is in 元; normalize to 亿
        if sealed_amounts:
            avg_amt_yi = round(sum(sealed_amounts) / len(sealed_amounts), 2)
            avg_amt_yi = normalize_to_yi(avg_amt_yi, "yuan")
        else:
            avg_amt_yi = None

        if sealed_big_orders:
            avg_big_yi = round(sum(sealed_big_orders) / len(sealed_big_orders), 2)
            avg_big_yi = normalize_to_yi(avg_big_yi, "yuan")
        else:
            avg_big_yi = None

        total_fried_amt = sum(fried_amounts) or 0
        total_all_amt = total_fried_amt + sum(sealed_amounts) or 1
        fried_ratio = round(total_fried_amt / total_all_amt, 3) if total_all_amt > 0 else None

        metrics = LimitUpMetrics(
            total_count=total,
            sealed_count=sealed,
            fried_board_count=fried,
            chain_board_count=chain_count,
            max_board_height=max_h,
            max_turnover_board_height=max_h,  # TODO: proper turnover board height
            first_board_count=first_count,
            first_board_success_rate=round(first_count / max(total, 1), 3),
            sealed_board_ratio=round(sealed / max(total, 1), 3),
            high_board_count=high_board,
            avg_turnover_rate=avg_turnover,
            avg_amount_yi=avg_amt_yi,
            avg_big_order_net_yi=avg_big_yi,
            fried_amount_ratio=fried_ratio,
            board_type_counts=board_type_counts,
            source=MetricSource("db_query", "ths_hot_reason_snapshot", confidence=0.9),
        )
        return metrics, streak_dist

    @staticmethod
    def _build_relay(lu: LimitUpMetrics, streak_dist: dict[int, int] | None = None) -> RelayEcologyMetrics:
        """Compute real promotion rates from streak distribution.

        p1to2 = stocks at height >= 2 / stocks at height >= 1 (i.e. all)
        p2to3 = stocks at height >= 3 / stocks at height >= 2
        p3to4 = stocks at height >= 4 / stocks at height >= 3
        """
        if streak_dist:
            h1 = sum(v for h, v in streak_dist.items() if h >= 1)
            h2 = sum(v for h, v in streak_dist.items() if h >= 2)
            h3 = sum(v for h, v in streak_dist.items() if h >= 3)
            h4 = sum(v for h, v in streak_dist.items() if h >= 4)
            p1to2 = round(h2 / max(h1, 1), 3)
            p2to3 = round(h3 / max(h2, 1), 3)
            p3to4 = round(h4 / max(h3, 1), 3)
        else:
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

    @staticmethod
    def _build_momentum(breadth: MarketBreadthMetrics,
                        lu: LimitUpMetrics) -> EmotionMomentumMetrics:
        total = breadth.up_count + breadth.down_count or 1
        r = breadth.up_count / total

        first_red = min(0.8, r)
        first_loss = max(0.05, 1 - r - 0.3)
        chain_red = first_red * 0.8
        chain_loss = first_loss * 0.7
        chain_ratio = min(0.5, lu.chain_board_count / max(lu.total_count, 1))
        yest_red = 0.3  # yesterday chain not limit red — estimated when no history

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
            chain_board_ratio=round(chain_ratio, 2),
            chain_board_big_loss_ratio=round(chain_loss, 2),
            yesterday_chain_not_limit_red_ratio=round(yest_red, 2),
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
