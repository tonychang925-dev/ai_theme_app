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
    HighPositionDeathMetrics,
    LeaderEvolutionMetrics,
    LimitUpMetrics,
    LossAttributionMetrics,
    LossEffectMetrics,
    MarketBreadthMetrics,
    MarketMetricsSnapshot,
    MetricSource,
    RelayEcologyMetrics,
    normalize_to_yi,
)

DB_DSN = "postgresql://localhost:5432/stock_data_test"


class MarketMetricsService:
    """Produce MarketMetricsSnapshot — the single source of truth.

    Supports optional BoardPoolProvider for a-stock-data integration.
    When available, limit_days and promotion rates come from Eastmoney
    board pools instead of streak backtracking.
    """

    def __init__(self, board_provider=None):
        self._board_provider = board_provider  # BoardPoolProvider | None

    def get(self, trade_date: date) -> MarketMetricsSnapshot:
        return asyncio.run(self.get_async(trade_date))

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

        # ── Board pool data from a-stock-data (Eastmoney API) ──
        em_zt = em_zb = em_dt = em_yesterday_zt = None
        if self._board_provider:
            try:
                em_zt = await self._board_provider._client.fetch_zt_pool(trade_date)
                em_zb = await self._board_provider._client.fetch_zb_pool(trade_date)
                em_dt = await self._board_provider._client.fetch_dt_pool(trade_date)
                # YZT endpoint unreliable; use yesterday's ZT pool for promotion calc
                from datetime import timedelta
                em_yesterday_zt = await self._board_provider._client.fetch_zt_pool(trade_date - timedelta(days=1))
            except Exception:
                pass  # fallback to DB-backed computation

        breadth = await self._build_breadth(conn, trade_date, overview, {})
        limitup, streak_dist, yesterday_codes, stock_detail, today_streaks = await self._build_limitup(
            conn, trade_date, overview, {}, em_zt, em_zb)
        relay = await self._build_relay(conn, trade_date, limitup, streak_dist,
                                         yesterday_codes, today_streaks, em_yesterday_zt, em_zt)
        capital = await self._build_capital(conn, trade_date, breadth, overview)
        momentum = self._build_momentum(breadth, limitup, relay)
        loss_effect = await self._build_loss_effect(conn, trade_date, breadth, relay, em_dt)
        leader_evolution = self._build_leader_evolution(trade_date, stock_detail, streak_dist, yesterday_codes)
        loss_attr = self._build_loss_attribution(trade_date, loss_effect, relay, leader_evolution)
        death = self._build_death_index(leader_evolution, loss_effect, relay)
        death_prop = self._build_death_propagation(leader_evolution, relay, loss_effect)

        return MarketMetricsSnapshot(
            trade_date=trade_date,
            breadth=breadth, limitup=limitup, relay=relay,
            capital=capital, emotion_momentum=momentum,
            loss_effect=loss_effect,
            leader_evolution=leader_evolution,
            loss_attribution=loss_attr,
            high_position_death=death,
            death_propagation=death_prop,
            data_quality_score=0.85 if breadth.up_count > 0 else 0.5,
        )

    # ── Builders ──

    async def _build_breadth(self, conn, td: date, overview: dict, cal: dict) -> MarketBreadthMetrics:
        up = int(overview.get("up_count", 0) or 0)
        down = int(overview.get("down_count", 0) or 0)
        lu = int(overview.get("limit_up_total", 0) or 0)
        ld = int(overview.get("limit_down_total", 0) or 0)
        source = "recap_snapshot"

        # Fallback: query subject_stock_daily_snapshot directly when recap is missing
        if up == 0 and down == 0:
            try:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) FILTER (WHERE pct_chg > 0) AS up_count, "
                    "COUNT(*) FILTER (WHERE pct_chg < 0) AS down_count, "
                    "COUNT(*) FILTER (WHERE pct_chg >= 9.8) AS limit_up_count "
                    "FROM subject_stock_daily_snapshot WHERE trade_date = $1::date",
                    td,
                )
                if row and row["up_count"] > 0:
                    up = row["up_count"]
                    down = row["down_count"]
                    if lu == 0:
                        lu = row["limit_up_count"]
                    source = "subject_stock_daily_snapshot"
            except Exception:
                pass

        raw_amount = float(overview.get("total_amount", 0) or 0)
        # recap total_amount is in 万元 → 亿元
        turnover_yi = normalize_to_yi(raw_amount, "wan")

        return MarketBreadthMetrics(
            up_count=up, down_count=down,
            limit_up_count=lu, limit_down_count=ld,
            up_ratio=round(up / max(up + down, 1), 3),
            turnover_yi=turnover_yi,
            source=MetricSource(source, "market_overview_review", confidence=0.9 if source == "recap_snapshot" else 0.85),
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

    async def _build_limitup(self, conn, td: date, overview: dict, cal: dict,
                              em_zt=None, em_zb=None) -> tuple[LimitUpMetrics, dict[int, int], set[str], dict[str, dict], dict[str, int]]:
        """Build real LimitUpMetrics from ths_hot_reason_snapshot.

        Uses pct_chg to classify sealed vs fried per stock, with
        threshold varying by board type (主板 10%, 创业板/科创 20%, ST 5%).

        When ths_hot_reason_snapshot lacks pct_chg (NULL), cross-references
        stock_daily_snapshot for the missing data.
        """
        rows = await conn.fetch(
            "SELECT stock_code, stock_name, reason_raw, reason_tags, "
            "       pct_chg, turnover_rate, amount, big_order_net "
            "FROM ths_hot_reason_snapshot "
            "WHERE trade_date = $1::date",
            td,
        )

        # ── Detect pct_chg gap and backfill from stock_daily_snapshot ──
        ths_has_pct = any(float(r["pct_chg"] or 0) != 0 for r in rows) if rows else False
        sds_backfill: dict[str, dict] = {}
        if not ths_has_pct and rows:
            # Batch lookup from stock_daily_snapshot via stock_code + suffix join
            codes = [self._norm_code(r["stock_code"]) for r in rows]
            sds_rows = await conn.fetch(
                "SELECT stock_id, pct_chg, amount FROM stock_daily_snapshot "
                "WHERE trade_date = $1::date", td)
            sds_map: dict[str, dict] = {}
            for sr in sds_rows:
                sid = str(sr["stock_id"] or "")
                # stock_daily_snapshot.stock_id is like "000001.SZ"
                code = sid.split(".")[0] if "." in sid else sid
                sds_map[code] = {"pct_chg": float(sr["pct_chg"] or 0),
                                 "amount": float(sr["amount"] or 0)}
            for code in codes:
                if code in sds_map:
                    sds_backfill[code] = sds_map[code]

        # ── Per-stock classification ──
        sealed_codes: set[str] = set()
        fried_codes: set[str] = set()
        all_codes: set[str] = set()

        sealed_turnovers: list[float] = []
        sealed_amounts: list[float] = []      # raw amounts (元 from THS API)
        sealed_big_orders: list[float] = []
        fried_amounts: list[float] = []

        board_type_counts: dict[str, int] = {}
        stock_detail: dict[str, dict] = {}  # code → {name, pct_chg, sealed, reason_tags, turnover_rate}

        for r in rows:
            code = self._norm_code(r["stock_code"])
            if not code:
                continue
            all_codes.add(code)

            stock_name = str(r["stock_name"] or "")

            # Priority: THS pct_chg → stock_daily_snapshot backfill → assume sealed
            ths_pct = float(r["pct_chg"] or 0)
            ths_turnover = float(r["turnover_rate"] or 0)
            ths_has_data = ths_pct != 0.0 or ths_turnover != 0.0

            if ths_has_data:
                pct = ths_pct
                turnover = ths_turnover
                raw_amount = float(r["amount"] or 0)
                big_order = float(r["big_order_net"] or 0)
            elif code in sds_backfill:
                bf = sds_backfill[code]
                pct = bf["pct_chg"]
                turnover = 0.0  # sds doesn't have turnover_rate
                raw_amount = bf["amount"]
                big_order = 0.0
            else:
                pct = 10.0  # conservative: assume sealed at 10%
                turnover = 0.0
                raw_amount = 0.0
                big_order = 0.0

            threshold = self._limit_threshold(code, stock_name)
            board = self._board_class(code, stock_name)
            board_type_counts[board] = board_type_counts.get(board, 0) + 1

            sealed = pct >= threshold
            if sealed:
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

            # Store per-stock detail for leader evolution
            reason_tags = [t.strip() for t in str(r.get("reason_tags") or "").split("+") if t.strip()] if r.get("reason_tags") else []
            stock_detail[code] = {
                "name": stock_name,
                "pct_chg": pct,
                "sealed": sealed,
                "reason_tags": reason_tags,
                "turnover_rate": turnover,
            }

        # ── When EM provider active: use EM as single source of truth ──
        if em_zt:
            total = len(em_zt)     # EM ZT pool count (analyst-verified)
            sealed = len(em_zt)    # EM ZT = sealed (no fried in ZT pool)
            fried = len(em_zb) if em_zb else 0
        else:
            total = len(all_codes)
            sealed = len(sealed_codes)
            fried = len(fried_codes)

        # ── Streak / board height ──
        # Priority: Eastmoney API limit_days (a-stock-data) → streak backtracking
        today_streaks: dict[str, int] = {}
        yesterday_codes: set[str] = set()

        if em_zt:
            # ── Use Eastmoney board pool limit_days ──
            # Eastmoney returns plain 6-digit codes (e.g. "001229")
            em_code_map: dict[str, int] = {}
            for s in em_zt:
                code = (s.code or "").strip()
                if code:
                    em_code_map[code] = s.limit_days

            for code in all_codes:
                if code in em_code_map:
                    today_streaks[code] = max(1, em_code_map[code])
                else:
                    today_streaks[code] = 1

            # Yesterday codes: populated in _build_relay from em_yesterday_zt
            yesterday_codes = set()

        else:
            # ── Fallback: streak backtracking from ths_hot_reason_snapshot ──
            today_streaks = {code: 1 for code in all_codes}
            last_seen: dict[str, date] = {code: td for code in all_codes}

            prev_dates: list[date] = []
            cursor = td
            for _ in range(5):
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
                if not yesterday_codes:
                    yesterday_codes = prev_set.copy()
                extended = False
                for code in list(today_streaks.keys()):
                    if code in prev_set:
                        gap = (last_seen[code] - prev_d).days if code in last_seen else 0
                        if gap <= 3:
                            today_streaks[code] += 1
                        else:
                            today_streaks[code] = 1
                        last_seen[code] = prev_d
                        extended = True
                if not extended:
                    break

        if em_zt:
            # EM provides exact ladder: {board_height: stock_count}
            em_ladder: dict[int, int] = {}
            for s in em_zt:
                h = s.limit_days
                if h > 0:
                    em_ladder[h] = em_ladder.get(h, 0) + 1
            max_h = max(em_ladder.keys()) if em_ladder else 1
            current_board = em_ladder.get(2, 0)
            historical_streak = sum(v for h, v in em_ladder.items() if h >= 2)
            first_count = em_ladder.get(1, 0)
            high_board = sum(v for h, v in em_ladder.items() if h >= 3)
        else:
            max_h = max(today_streaks.values()) if today_streaks else 1
            current_board = sum(1 for h in today_streaks.values() if h == 2)
            historical_streak = sum(1 for h in today_streaks.values() if h >= 2)
            first_count = total - current_board
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
            # ths amount is same unit as sds (千元); normalize
            avg_amt_yi = normalize_to_yi(avg_amt_yi, "qian_yuan")
        else:
            avg_amt_yi = None

        if sealed_big_orders:
            avg_big_yi = round(sum(sealed_big_orders) / len(sealed_big_orders), 2)
            avg_big_yi = normalize_to_yi(avg_big_yi, "qian_yuan")
        else:
            avg_big_yi = None

        total_fried_amt = sum(fried_amounts) or 0
        total_all_amt = total_fried_amt + sum(sealed_amounts) or 1
        fried_ratio = round(total_fried_amt / total_all_amt, 3) if total_all_amt > 0 else None

        metrics = LimitUpMetrics(
            total_count=total,
            sealed_count=sealed,
            fried_board_count=fried,
            chain_board_count=current_board,  # backward compat → current_board_height
            current_board_height=current_board,
            historical_streak_height=historical_streak,
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
        return metrics, streak_dist, yesterday_codes, stock_detail, today_streaks

    @staticmethod
    async def _build_relay(conn, td: date, lu: LimitUpMetrics,
                           streak_dist: dict[int, int] | None = None,
                           yesterday_codes: set[str] | None = None,
                           today_streaks: dict[str, int] | None = None,
                           em_yesterday_zt=None, em_zt=None) -> RelayEcologyMetrics:
        """Compute promotion rates + yesterday feedback score (v2).

        v2 adds:
          - Yesterday limit-up cross-reference (continue / big loss / avg return)
          - LimitUp Feedback Score (-100 ~ +100)

        Promotion rates from streak_dist.
        Feedback score from yesterday ∩ today cross-reference.
        """
        _norm = MarketMetricsService._norm_code

        # ── Promotion rates (v4: Eastmoney 昨涨停池 OR fallback) ──
        if em_yesterday_zt and em_zt:
            # ── 昨日 ZT pool JOIN 今日 ZT pool: precise 晋级率 ──
            # em_yesterday_zt: yesterday's ZT stocks (ZT pool with limit_days)
            # em_zt: today's ZT stocks with limit_days
            y1_total = y2_total = y3_total = 0
            y1_success = y2_success = y3_success = 0

            em_today_codes: dict[str, int] = {}
            for s in (em_zt or []):
                code = (s.code or "").strip()
                if code:
                    em_today_codes[code] = s.limit_days

            for ys in (em_yesterday_zt or []):
                code = (ys.code or "").strip()
                # LimitUpPoolStock has limit_days (not y_limit_days)
                y_h = ys.limit_days
                today_h = em_today_codes.get(code, 0)

                if y_h == 1:
                    y1_total += 1
                    if today_h >= 2: y1_success += 1
                elif y_h == 2:
                    y2_total += 1
                    if today_h >= 3: y2_success += 1
                elif y_h >= 3:
                    y3_total += 1
                    if today_h >= 4: y3_success += 1

            p1to2 = round(y1_success / max(y1_total, 1), 3)
            p2to3 = round(y2_success / max(y2_total, 1), 3)
            p3to4 = round(y3_success / max(y3_total, 1), 3)

        elif yesterday_codes:
            today_rows = await conn.fetch(
                "SELECT stock_code FROM ths_hot_reason_snapshot "
                "WHERE trade_date = $1::date", td)
            today_set = {_norm(r["stock_code"]) for r in today_rows if _norm(r["stock_code"])}

            # Get the most recent previous trading date (yesterday)
            prev_row = await conn.fetchrow(
                "SELECT MAX(trade_date) as d FROM ths_hot_reason_snapshot "
                "WHERE trade_date < $1::date", td)
            yesterday_date = prev_row["d"] if prev_row else None

            # Compute yesterday's per-stock streaks
            yesterday_streaks: dict[str, int] = {}
            if yesterday_date:
                y_rows = await conn.fetch(
                    "SELECT stock_code FROM ths_hot_reason_snapshot "
                    "WHERE trade_date = $1::date", yesterday_date)
                for yr in y_rows:
                    code = _norm(yr["stock_code"])
                    if code:
                        yesterday_streaks[code] = 1

                # Backtrack one more day to compute yesterday's true streaks
                prev2_row = await conn.fetchrow(
                    "SELECT MAX(trade_date) as d FROM ths_hot_reason_snapshot "
                    "WHERE trade_date < $1::date", yesterday_date)
                if prev2_row and prev2_row["d"]:
                    p2_rows = await conn.fetch(
                        "SELECT stock_code FROM ths_hot_reason_snapshot "
                        "WHERE trade_date = $1::date", prev2_row["d"])
                    p2_set = {_norm(r["stock_code"]) for r in p2_rows if _norm(r["stock_code"])}
                    for code in list(yesterday_streaks.keys()):
                        if code in p2_set:
                            yesterday_streaks[code] += 1

            # Now compute promotion rates
            y1 = y2 = y3 = 0  # yesterday pools
            s1 = s2 = s3 = 0  # today successes
            for code, y_streak in yesterday_streaks.items():
                t_streak = today_streaks.get(code, 0) if today_streaks else 0
                if y_streak == 1:
                    y1 += 1
                    if t_streak >= 2: s1 += 1
                elif y_streak == 2:
                    y2 += 1
                    if t_streak >= 3: s2 += 1
                elif y_streak >= 3:
                    y3 += 1
                    if t_streak >= 4: s3 += 1

            p1to2 = round(s1 / max(y1, 1), 3)
            p2to3 = round(s2 / max(y2, 1), 3)
            p3to4 = round(s3 / max(y3, 1), 3)
        elif streak_dist:
            h_exact_2 = streak_dist.get(2, 0)
            h_exact_3 = streak_dist.get(3, 0)
            h_exact_4 = streak_dist.get(4, 0)
            h_total = lu.total_count
            p1to2 = round(h_exact_2 / max(h_total, 1), 3)
            p2to3 = round(h_exact_3 / max(h_exact_2 + h_exact_3 + h_exact_4, 1), 3)
            p3to4 = round(h_exact_4 / max(h_exact_3 + h_exact_4, 1), 3)
        else:
            t1 = lu.first_board_count
            t2 = lu.chain_board_count
            p1to2 = round(t2 / max(t1, 1), 2)
            p2to3 = round(max(0, (lu.max_board_height - 2)) * 0.1, 2)
            p3to4 = round(max(0, (lu.max_board_height - 3)) * 0.05, 2)

        # ── Yesterday feedback (v2) ──
        yesterday_count = 0
        today_continue = 0
        continue_ratio = 0.0
        big_loss_count = 0
        avg_return = None
        if em_yesterday_zt and em_zt:
            yesterday_count = len(em_yesterday_zt)
            today_codes = {s.code.strip(): s for s in em_zt}
            today_continue = 0
            for ys in em_yesterday_zt:
                if ys.code.strip() in today_codes:
                    today_continue += 1
            continue_ratio = round(today_continue / max(yesterday_count, 1), 3)
            # Populate yesterday_codes from EM so SDS big_loss query works
            yesterday_codes = {s.code.strip() for s in em_yesterday_zt}
        if yesterday_codes:
            # Compute SDS-based big_loss for failed codes (always, regardless of EM path)
            if not em_yesterday_zt:  # EM path already set yesterday_count/continue/ratio
                yesterday_count = len(yesterday_codes)
                # Today's limit-up stocks
                today_rows = await conn.fetch(
                    "SELECT stock_code FROM ths_hot_reason_snapshot "
                    "WHERE trade_date = $1::date", td)
                today_set = {_norm(r["stock_code"]) for r in today_rows if _norm(r["stock_code"])}
                continue_codes = yesterday_codes & today_set
                today_continue = len(continue_codes)
                continue_ratio = round(today_continue / max(yesterday_count, 1), 3)
                failed_codes = yesterday_codes - today_set
            else:
                # EM already computed continue; use today EM codes for failed detection
                em_today_set = {s.code.strip() for s in em_zt}
                failed_codes = yesterday_codes - em_today_set

            big_loss_count = 0
            failed_returns: list[float] = []

            if failed_codes:
                rows = await conn.fetch(
                    "SELECT stock_id, pct_chg FROM stock_daily_snapshot "
                    "WHERE trade_date = $1::date", td)
                today_pct: dict[str, float] = {}
                for r in rows:
                    code = _norm(r["stock_id"])
                    if code and code in failed_codes:
                        today_pct[code] = float(r["pct_chg"] or 0)

                for code in failed_codes:
                    pct = today_pct.get(code)
                    if pct is not None:
                        failed_returns.append(pct)
                        if pct <= -5.0:
                            big_loss_count += 1

            avg_return = round(sum(failed_returns) / max(len(failed_returns), 1), 2) if failed_returns else None

        # ── LimitUp Feedback Score (-100 ~ +100) ──
        if yesterday_count > 0:
            continue_score = (today_continue / yesterday_count) * 100
            loss_penalty = (big_loss_count / yesterday_count) * 100
            feedback_raw = continue_score - loss_penalty
            if avg_return is not None:
                feedback_raw += avg_return * 2

            feedback_comps = {
                "continue_bonus": round(continue_score, 1),
                "big_loss_penalty": round(-loss_penalty, 1),
                "avg_return_adjust": round(avg_return * 2, 1) if avg_return is not None else 0,
            }
        else:
            feedback_raw = 0.0
            feedback_comps = {"continue_bonus": 0, "big_loss_penalty": 0, "avg_return_adjust": 0}

        if feedback_raw >= 60:       fb_label = "强正反馈"
        elif feedback_raw >= 20:     fb_label = "正反馈"
        elif feedback_raw >= -20:    fb_label = "中性"
        elif feedback_raw >= -60:    fb_label = "负反馈"
        else:                        fb_label = "强负反馈"

        return RelayEcologyMetrics(
            promotion_1_to_2=min(0.99, p1to2),
            promotion_2_to_3=min(0.99, p2to3),
            promotion_3_to_4=min(0.99, p3to4),
            chain_board_count=lu.chain_board_count,
            max_board_height=lu.max_board_height,
            max_turnover_board_height=lu.max_turnover_board_height,
            yesterday_limitup_count=yesterday_count,
            today_continue_count=today_continue,
            continue_ratio=continue_ratio,
            yesterday_big_loss_count=big_loss_count,
            yesterday_avg_return_pct=avg_return,
            feedback_score=round(feedback_raw, 1),
            feedback_label=fb_label,
            feedback_components=feedback_comps,
            high_board_count=lu.high_board_count,
            high_board_break_count=0,  # TODO: needs yesterday board height per stock
            source=lu.source,
        )

    async def _build_capital(self, conn, td: date, breadth: MarketBreadthMetrics,
                             overview: dict) -> ActiveCapitalMetrics:
        """Active capital = limit-up/touch-limit-up stock turnover (analyst methodology).

        Cross-references ths_hot_reason_snapshot with stock_daily_snapshot
        to match the analyst's "今日所有涨停及触及涨停个股成交量之和".
        """
        total_yi = breadth.turnover_yi

        # Analyst methodology: SUM(amount) for all limit-up stocks
        # Use ths_hot_reason_snapshot to identify limit-up stocks, then
        # join with stock_daily_snapshot for amount (unit: 千元)
        rows = await conn.fetch(
            "SELECT SUM(s.amount) as total_amt "
            "FROM ths_hot_reason_snapshot t "
            "JOIN stock_daily_snapshot s ON s.trade_date = t.trade_date "
            "  AND (s.stock_id = t.stock_code || '.SZ' OR s.stock_id = t.stock_code || '.SH') "
            "WHERE t.trade_date = $1::date", td
        )
        active_raw = float(rows[0]["total_amt"] or 0) if rows else 0
        # stock_daily_snapshot.amount is in 千元; THS chengjiaoe has ~2x calibration gap
        # Calibrated against analyst: 7/7(897亿)+7/8(739亿) → factor ≈ 2.04
        active_yi = round(normalize_to_yi(active_raw, "qian_yuan") * 2.04, 2)

        return ActiveCapitalMetrics(
            total_turnover_yi=total_yi,
            active_limitup_amount_yi=active_yi,
            active_ratio=round(active_yi / max(total_yi, 1), 4),
            source=MetricSource("db_query", "ths+sds join", confidence=0.85),
        )

    @staticmethod
    def _build_momentum(breadth: MarketBreadthMetrics,
                        lu: LimitUpMetrics,
                        relay: RelayEcologyMetrics | None = None) -> EmotionMomentumMetrics:
        """Compute emotion momentum using actual per-stock tracking data.

        v3: Uses relay data for real ratios instead of breadth estimates.
        Analyst formula: 6-component weighted score.
        """
        # Use relay data when available (real per-stock tracking)
        if relay and relay.yesterday_limitup_count > 0:
            yest_total = relay.yesterday_limitup_count
            first_red = relay.continue_ratio              # 昨涨停→今继续
            first_loss = relay.yesterday_big_loss_count / max(yest_total, 1)  # 大面比
            chain_ratio = min(1.0, lu.chain_board_count / max(lu.total_count, 1))
            # 连板红盘比: estimated from relay feedback strength
            # feedback > 0 → chain board mostly green; feedback < -30 → mostly red
            chain_red = max(0.05, min(1.0, (relay.feedback_score + 100) / 200))
            chain_loss = relay.yesterday_big_loss_count / max(yest_total, 1) * 0.8
            yest_red = 0.5  # 昨日连板未涨停绿盘比 — estimated
        else:
            # Fallback: breadth-based estimates
            total = breadth.up_count + breadth.down_count or 1
            r = breadth.up_count / total
            first_red = min(0.8, r)
            first_loss = max(0.05, 1 - r - 0.3)
            chain_red = first_red * 0.8
            chain_loss = first_loss * 0.7
            chain_ratio = min(0.5, lu.chain_board_count / max(lu.total_count, 1))
            yest_red = 0.3

        # Analyst scale momentum (-18 ~ +10 range)
        base_raw = first_red * 2 - first_loss * 2 + chain_red * 2 + chain_ratio * 2 - chain_loss * 2 + yest_red * 1

        # Panic amplification: when relay feedback < -30 + severe loss, amplify negative
        if relay and relay.feedback_score < -30 and first_loss > 0.3:
            base_raw -= abs(relay.feedback_score) * 0.15  # add -6 at fb=-40

        momentum_raw = round(base_raw, 1)
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
            source=MetricSource("relay_data" if relay else "recap_snapshot", confidence=0.85 if relay else 0.75),
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

    def _build_leader_evolution(self, td: date,
                                 stock_detail: dict[str, dict],
                                 today_streaks: dict[str, int],
                                 yesterday_codes: set[str]) -> LeaderEvolutionMetrics:
        """Build leader evolution with expectation tracking (v2).

        Estimates yesterday heights from today's streaks:
        - today streak 3+ means yesterday streak 2+
        - subtract 1 from today's streak to estimate yesterday's height
        """
        from .leader_evolution import LeaderEvolutionBuilder

        # yesterday_high_boards: codes that were >= 2-board yesterday
        yesterday_high = {c for c, h in today_streaks.items()
                         if h >= 3 and c in yesterday_codes}

        # yesterday_heights: estimate from today streak - 1
        yesterday_heights = {}
        for c, h in today_streaks.items():
            if c in yesterday_codes:
                yesterday_heights[c] = max(1, h - 1)
        # Also include yesterday codes not in today's limitup (they broke)
        for c in yesterday_codes:
            if c not in today_streaks:
                yesterday_heights[c] = 1  # at minimum 1-board yesterday

        builder = LeaderEvolutionBuilder()
        market_max = max(today_streaks.values()) if today_streaks else 5
        return builder.build(td, stock_detail, today_streaks,
                            yesterday_codes, yesterday_high, yesterday_heights,
                            market_max_height=market_max)

    @staticmethod
    def _build_loss_attribution(td: date, loss: LossEffectMetrics | None,
                                 relay: RelayEcologyMetrics,
                                 leader: LeaderEvolutionMetrics | None) -> LossAttributionMetrics:
        """Attribute losses to their source: high-board, leader, or specific themes.

        Uses relay v2 data for yesterday's limit-up losses and leader evolution
        for high-board/leader-specific breakdowns.
        """
        if loss is None:
            return LossAttributionMetrics(trade_date=td)

        ld_count = loss.limit_down_count
        yest_loss = loss.big_loss_count  # from relay v2: 昨涨停今日大面
        leader_loss = leader.break_count if leader else 0
        hb_loss = leader_loss + min(ld_count, leader.yesterday_leader_count if leader else 0)

        # Theme loss from leader breaks
        theme_loss: dict[str, int] = {}
        if leader:
            for l in leader.leaders:
                if l.status == "BREAK" and l.theme_hint:
                    theme_loss[l.theme_hint] = theme_loss.get(l.theme_hint, 0) + 1

        primary_theme = max(theme_loss, key=theme_loss.get) if theme_loss else ""
        primary_count = theme_loss.get(primary_theme, 0)

        concentrated_hb = hb_loss > ld_count * 0.3 if ld_count > 0 else False
        concentrated_ldr = leader_loss > 0

        # One-line conclusion
        if ld_count == 0:
            conclusion = "今日无显著亏钱效应"
        elif concentrated_ldr and concentrated_hb:
            conclusion = f"亏损集中于高位龙头方向({primary_theme}断板{leader_loss}只)，退潮风险高"
        elif yest_loss > ld_count * 0.5:
            conclusion = f"亏损集中于昨日涨停股(大面{yest_loss}只)，接力情绪差"
        else:
            conclusion = f"跌停{ld_count}家，大面{yest_loss}只，分布较分散"

        return LossAttributionMetrics(
            trade_date=td,
            limit_down_count=ld_count,
            high_board_loss_count=hb_loss,
            yesterday_limitup_loss_count=yest_loss,
            leader_loss_count=leader_loss,
            theme_loss=theme_loss,
            primary_loss_theme=primary_theme,
            primary_loss_count=primary_count,
            concentrated_high_board=concentrated_hb,
            concentrated_leader=concentrated_ldr,
            loss_conclusion=conclusion,
            source=MetricSource("derived", "loss_effect + relay + leader_evolution", confidence=0.80),
        )

    async def _build_loss_effect(self, conn, td: date, breadth: MarketBreadthMetrics,
                                  relay: RelayEcologyMetrics, em_dt=None) -> LossEffectMetrics:
        """Build loss effect metrics from stock_daily_snapshot + relay data.

        Sources:
          - limit_down: Eastmoney DT pool (primary) or SDS pct_chg (fallback)
          - big_loss: relay.yesterday_big_loss_count
          - high_board_break: from relay
        """
        # ── Limit down stocks ──
        if em_dt:
            # Use Eastmoney DT pool for real limit-down count
            ld_count = len(em_dt)
            ld_amount = 0.0
        else:
            # Fallback: SDS pct_chg threshold
            rows = await conn.fetch(
                "SELECT pct_chg, amount FROM stock_daily_snapshot "
                "WHERE trade_date = $1::date", td)
            ld_count = 0
            ld_amount = 0.0
            for r in rows:
                pct = float(r["pct_chg"] or 0)
                amt = float(r["amount"] or 0)
                if pct <= -9.5:
                    ld_count += 1
                    ld_amount += amt

        total_stocks = breadth.up_count + breadth.down_count
        ld_ratio = round(ld_count / max(total_stocks, 1), 4)
        ld_amount_yi = normalize_to_yi(ld_amount, "qian_yuan") if ld_amount > 0 else 0.0

        # ── Big loss from relay ──
        big_loss = relay.yesterday_big_loss_count
        yesterday_total = relay.yesterday_limitup_count
        big_loss_ratio = round(big_loss / max(yesterday_total, 1), 3)

        # ── High board break ──
        hb_break = relay.high_board_break_count

        # ── Composite loss effect score (0~100) ──
        # 跌停权重 40%, 大面权重 40%, 高位断板权重 20%
        ld_contribution = min(100, (ld_count / max(total_stocks, 1)) * 1000)
        bl_contribution = min(100, (big_loss / max(yesterday_total, 1)) * 100)
        hb_contribution = min(100, hb_break * 20)

        raw_score = ld_contribution * 0.4 + bl_contribution * 0.4 + hb_contribution * 0.2
        score = round(min(100, raw_score), 1)

        if score >= 60:       label = "恐慌"
        elif score >= 35:     label = "严重"
        elif score >= 15:     label = "明显"
        elif score >= 3:      label = "轻微"
        else:                 label = "安全"

        # ── Total damage ──
        total_damage = ld_count + big_loss  # rough estimate, may overlap
        damage_ratio = round(total_damage / max(total_stocks, 1), 4)

        return LossEffectMetrics(
            limit_down_count=ld_count,
            limit_down_ratio=ld_ratio,
            limit_down_amount_yi=ld_amount_yi,
            big_loss_count=big_loss,
            big_loss_from_yesterday_ratio=big_loss_ratio,
            high_board_break_count=hb_break,
            loss_effect_score=score,
            loss_effect_label=label,
            total_damage_count=total_damage,
            damage_ratio=damage_ratio,
            source=MetricSource("db_query", "stock_daily_snapshot + relay", confidence=0.85),
        )

    @staticmethod
    def _build_death_index(leader: LeaderEvolutionMetrics | None,
                            loss: LossEffectMetrics | None,
                            relay: RelayEcologyMetrics) -> HighPositionDeathMetrics:
        """Death Index v2: relative height + death type + contagion.

        importance = relative_height_factor * strength_factor * death_type_factor

        Death type factors:
          NORMAL=1.0, FRIED=1.2, LIMIT_DOWN=2.0, HEAVEN_EARTH=3.0

        relative_height = stock_height / market_max — 5板 when max=5 >>> 5板 when max=8
        """
        # ── Death type factor mapping ──
        DEATH_TYPE_FACTOR = {"NORMAL": 1.0, "FRIED": 1.2, "LIMIT_DOWN": 2.0, "HEAVEN_EARTH": 3.0}

        lb_raw = 0
        lb_weighted = 0.0
        contagion_score = 0.0
        broken_leaders_detail: list[str] = []

        if leader:
            for l in leader.leaders:
                if l.status in ("BREAK", "WEAKEN_UNEXPECTED"):
                    lb_raw += 1
                    # relative_height: weight by stock/market ratio
                    rh_factor = l.relative_height if l.relative_height > 0 else (l.board_height / 5.0)
                    s_factor = l.strength_score / 100.0 if l.strength_score > 0 else 0.4
                    dt_factor = DEATH_TYPE_FACTOR.get(l.death_type, 1.0)
                    imp = rh_factor * s_factor * dt_factor
                    lb_weighted += imp
                    broken_leaders_detail.append(
                        f"{l.stock_name}({l.board_height}板,rh={rh_factor:.1f},dt={l.death_type},imp={imp:.2f})")

                    # Contagion: theme-hint leaders have followers, their death spreads
                    if l.theme_hint and dt_factor >= 1.2:
                        contagion_score += imp * 0.3  # weight contagion at 30% of importance

        # 4.0 importance units → 100
        lb_norm = min(100, lb_weighted * 25)
        contagion_norm = min(100, contagion_score * 25)

        hb = loss.high_board_break_count if loss else 0
        bl = loss.big_loss_count if loss else 0
        fb_inv = max(0, (100 - max(0, relay.feedback_score))) * 0.3

        hb_norm = min(100, hb * 12.5)
        fb_norm = min(100, fb_inv)
        bl_norm = min(100, bl * 10)

        # v2: contagion + relay-driven escalation
        death = round(lb_norm * 0.35 + contagion_norm * 0.15 + hb_norm * 0.10 + fb_norm * 0.25 + bl_norm * 0.15, 1)
        # Relay-driven death escalation: even without leader breaks,
        # terrible relay feedback signals systemic risk
        if death < 35 and relay.feedback_score < -35:
            death = min(50, death + (abs(relay.feedback_score) - 35) * 0.5)

        # ── Label ──
        if death >= 60:
            label = "CRITICAL"
            detail = "; ".join(broken_leaders_detail[:3]) if broken_leaders_detail else f"龙头断板{lb_raw}只"
            conclusion = f"高位核心死亡！{detail}"
        elif death >= 35:
            label = "DANGER"
            detail = "; ".join(broken_leaders_detail[:2]) if broken_leaders_detail else f"龙头断板{lb_raw}只"
            conclusion = f"高位风险释放：{detail}"
        elif death >= 15:
            label = "WARNING"
            conclusion = f"高位出现松动，龙头断板{lb_raw}只"
        else:
            label = "SAFE"
            conclusion = "高位核心安全，无明显死亡信号"

    @staticmethod
    def _build_death_propagation(leader: LeaderEvolutionMetrics | None,
                                   relay: RelayEcologyMetrics,
                                   loss: LossEffectMetrics | None) -> DeathPropagationMetrics:
        """Death propagation v2: adds capital_escape as early warning signal.

        Capital flight often precedes visible losses — money leaves before
        prices crash. v2 weights: leader 30% + theme 25% + high_board 20%
        + yesterday 10% + capital_escape 15%
        """
        from .contracts import DeathPropagationMetrics

        lb = leader.break_count if leader else 0
        tf_ratio = relay.continue_ratio if relay else 0
        theme_fail = round(1 - tf_ratio, 2) if tf_ratio > 0 else 0.5
        hb_loss = loss.high_board_break_count if loss else 0
        yest_fail = round(1 - tf_ratio, 2)

        # Capital escape: proxy from relay feedback (negative = outflow)
        capital_escape = min(100, max(0, -relay.feedback_score)) if relay.feedback_score < 0 else 0

        prop = round(
            min(lb * 15, 30) +              # leader failure: max 30
            theme_fail * 25 +                # theme follow: max 25
            min(hb_loss * 5, 20) +           # high board: max 20
            yest_fail * 10 +                 # yesterday: max 10
            capital_escape * 0.15,           # capital flight: max 15
            1)

        if prop >= 60:
            label, narrative = "SYSTEMIC", "系统性崩溃：龙头死亡已扩散至全市场"
        elif prop >= 30:
            label, narrative = "SPREADING", "扩散中：龙头死亡正向外传播"
        else:
            label, narrative = "CONTAINED", "局部调整：龙头死亡未明显扩散"

        return DeathPropagationMetrics(
            propagation_index=prop, propagation_label=label,
            leader_failure_count=lb, theme_failure_ratio=theme_fail,
            high_position_loss_count=hb_loss,
            yesterday_limit_failure_ratio=yest_fail,
            narrative=narrative, source=MetricSource("derived", confidence=0.78))

        return HighPositionDeathMetrics(
            death_index=death,
            death_label=label,
            leader_break_count=lb_raw,
            high_board_loss_count=hb,
            yesterday_feedback_inverted=fb_norm,
            big_loss_count=bl,
            death_conclusion=conclusion,
            risk_escalation=death >= 60,
            source=MetricSource("derived", "leader + loss + relay", confidence=0.82),
        )

    @staticmethod
    def _norm_code(code: str) -> str:
        """Normalize stock code: strip .SZ/.SH suffix, uppercase."""
        return str(code or "").strip().upper().split(".")[0]
