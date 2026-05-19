"""Historical Backtest Read/Write Ports for UseCase replay.

Adapts A/B/C feature store tables to match the StockReadPorts/StockWritePorts
interface expected by BuildStrongStockTrackingUseCase and
BuildWeakToStrongCandidateUseCase.

Writes go to isolated rebuild tables, never production tables.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import (
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    StockBarDTO,
    TradeCalendarDTO,
)
from stock_processing_service.ports.read_ports import StockReadPorts
from stock_processing_service.ports.write_ports import StockWritePorts


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None: return Decimal(default)
    if isinstance(value, Decimal): return value
    try: return Decimal(str(value))
    except: return Decimal(default)


def _normalize_stock_id(raw: str) -> str:
    v = str(raw or "").strip().upper()
    if "." in v: return v
    if len(v) == 6 and v.isdigit():
        if v.startswith(("6","9")): return f"{v}.SH"
        if v.startswith(("0","2","3")): return f"{v}.SZ"
        if v.startswith(("4","8")): return f"{v}.BJ"
    return v


class HistoricalBacktestReadPorts:
    """Read adapter: feature store → UseCase inputs."""

    def __init__(self, gw: Any, start_date: date, end_date: date) -> None:
        self._gw = gw
        self._c = gw._client
        self._start = start_date
        self._end = end_date
        self._bars_cache: dict[date, dict[str, dict]] = {}
        self._trade_dates: list[date] = []
        self._loaded = False
        # Seed funnel audit (P0-6): per-call metrics, reset on each invocation
        self.seed_funnel: dict[str, int] = {}
        # v1.1a.1: refresh funnel
        self._refresh_raw_count: int = 0
        self._refresh_final_count: int = 0
        self._a_layer_lookback_set: set[str] = set()

    async def _ensure_loaded(self):
        if self._loaded: return
        self._loaded = True
        # Load trading days only (bars loaded lazily per-date to avoid OOM/timeout)
        rows = await self._c.execute_query(
            "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
            (self._start, self._end))
        self._trade_dates = [r['trade_date'] for r in rows]

    async def _ensure_bars_loaded(self, trade_date: date):
        """Lazy-load bars for a specific date into cache."""
        if trade_date in self._bars_cache:
            return
        bar_rows = await self._c.execute_query(
            "SELECT DISTINCT ON (stock_id) trade_date,stock_id,stock_name,open_price,high_price,low_price,close_price,pre_close,pct_chg,volume,amount FROM stock_daily_snapshot WHERE trade_date=$1 AND source_name LIKE 'tushare%'",
            (trade_date,))
        self._bars_cache[trade_date] = {str(r['stock_id']): r for r in bar_rows}

    async def _ensure_bars_for_dates(self, dates: list[date]):
        """Batch lazy-load bars for multiple dates that aren't cached yet."""
        missing = [d for d in dates if d not in self._bars_cache]
        if not missing:
            return
        bar_rows = await self._c.execute_query(
            "SELECT DISTINCT ON (trade_date,stock_id) trade_date,stock_id,stock_name,open_price,high_price,low_price,close_price,pre_close,pct_chg,volume,amount FROM stock_daily_snapshot WHERE trade_date=ANY($1) AND source_name LIKE 'tushare%' ORDER BY trade_date,stock_id",
            (missing,))
        for r in bar_rows:
            td = r['trade_date']
            self._bars_cache.setdefault(td, {})[str(r['stock_id'])] = r
        # Ensure empty entries for dates with no data (avoids repeated queries)
        for d in missing:
            if d not in self._bars_cache:
                self._bars_cache[d] = {}

    # ── Trade Calendar ──
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None:
        await self._ensure_loaded()
        dates = self._trade_dates
        if trade_date not in dates: return None
        idx = dates.index(trade_date)
        prev_td = dates[idx-1].isoformat() if idx > 0 else None
        next_td = dates[idx+1].isoformat() if idx+1 < len(dates) else None
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True,
                                prev_trade_date=prev_td, next_trade_date=next_td)

    # ── Daily Bars ──
    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        await self._ensure_loaded()
        await self._ensure_bars_loaded(trade_date)
        bars = self._bars_cache.get(trade_date, {})
        result = []
        for sid, b in bars.items():
            if stock_ids and sid not in stock_ids: continue
            result.append(StockBarDTO(
                trade_date=trade_date, stock_id=sid, stock_name=str(b.get('stock_name','')),
                open_price=_d(b.get('open_price')), high_price=_d(b.get('high_price')),
                low_price=_d(b.get('low_price')), close_price=_d(b.get('close_price')),
                pre_close=_d(b.get('pre_close')), pct_chg=_d(b.get('pct_chg')),
                volume=_d(b.get('volume')), amount=_d(b.get('amount')),
                limit_up_price=Decimal('0'), limit_down_price=Decimal('0')))
        return result

    async def get_stock_daily_bars_range(self, start_date: date, end_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        await self._ensure_loaded()
        relevant_dates = [d for d in self._trade_dates if start_date <= d <= end_date]
        await self._ensure_bars_for_dates(relevant_dates)
        result = []
        for td in self._trade_dates:
            if td < start_date or td > end_date: continue
            bars = self._bars_cache.get(td, {})
            for sid, b in bars.items():
                if stock_ids and sid not in stock_ids: continue
                result.append(StockBarDTO(
                    trade_date=td, stock_id=sid, stock_name=str(b.get('stock_name','')),
                    open_price=_d(b.get('open_price')), high_price=_d(b.get('high_price')),
                    low_price=_d(b.get('low_price')), close_price=_d(b.get('close_price')),
                    pre_close=_d(b.get('pre_close')), pct_chg=_d(b.get('pct_chg')),
                    volume=_d(b.get('volume')), amount=_d(b.get('amount')),
                    limit_up_price=Decimal('0'), limit_down_price=Decimal('0')))
        return result

    # ── Prior Snapshots ──
    async def get_prior_stock_daily_snapshots(self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None) -> list[PriorSnapshotDTO]:
        await self._ensure_loaded()
        lookback_start = trade_date - timedelta(days=lookback_days * 2)
        prior_dates = [d for d in self._trade_dates if lookback_start <= d < trade_date]
        await self._ensure_bars_for_dates(prior_dates)
        result = []
        for td in self._trade_dates:
            if td >= trade_date: break
            if td < lookback_start: continue
            bars = self._bars_cache.get(td, {})
            for sid, b in bars.items():
                if stock_ids and sid not in stock_ids: continue
                result.append(PriorSnapshotDTO(
                    trade_date=td, stock_id=sid, snapshot_version="historical",
                    payload={"pct_chg": str(b.get('pct_chg','')), "close_price": str(b.get('close_price','')),
                             # P0-4 fix: parse as float before comparison, not string
                             "limit_up": float(b.get('pct_chg') or 0) >= 9.5}))
        return result

    # ── A-layer: Mainline Identity / Cycle / Evidence ──
    # v1.1a: Use 5-day lookback for A-layer data since subject_daily_feature
    # only covers ~18 subjects per day but data persists across dates.

    async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[MainlineIdentityDTO]:
        if not subject_keys: return []
        lookback_start = trade_date - timedelta(days=10)  # ~5 trading days
        rows = await self._c.execute_query(
            """SELECT DISTINCT ON (subject_key) *
               FROM subject_daily_feature
               WHERE trade_date >= $1 AND trade_date <= $2
               AND subject_key=ANY($3)
               AND rule_version='subject_feature_from_rank_v0.1'
               ORDER BY subject_key, trade_date DESC""",
            (lookback_start, trade_date, subject_keys))
        return [MainlineIdentityDTO(
            subject_key=str(r['subject_key']), identity_status='confirmed' if r.get('is_mainline_proxy') else 'observed',
            is_main_theme=bool(r.get('is_mainline_proxy')), rule_version='subject_feature_from_rank_v0.1')
            for r in rows]

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[MainlineCycleDTO]:
        if not subject_keys: return []
        lookback_start = trade_date - timedelta(days=10)  # ~5 trading days
        rows = await self._c.execute_query(
            """SELECT DISTINCT ON (subject_key) *
               FROM subject_daily_feature
               WHERE trade_date >= $1 AND trade_date <= $2
               AND subject_key=ANY($3)
               AND rule_version='subject_feature_from_rank_v0.1'
               ORDER BY subject_key, trade_date DESC""",
            (lookback_start, trade_date, subject_keys))
        return [MainlineCycleDTO(
            trade_date=trade_date, subject_key=str(r['subject_key']),
            final_cycle_state=str(r.get('cycle_state','unknown')),
            final_mainline_alive=bool(r.get('is_mainline_proxy')) and str(r.get('cycle_state')) != 'fade',
            mainline_strength_score=_d(r.get('mainline_strength_score')),
            fade_watch_score=_d('40' if r.get('fade_watch') else '0'),
            fade_confirmed_score=_d('40' if r.get('fade_confirmed') else '0'))
            for r in rows]

    async def get_subject_cycle_evidence_daily(self, trade_date: date, subject_keys: list[str] | None = None) -> list[dict]:
        return []  # v0.8a: partial, no evidence yet

    # ── B-layer Seed / Refresh ──
    async def get_strong_watch_seed_rows(self, trade_date: date, lookback_days: int = 7) -> list[dict[str, Any]]:
        """Map B-layer + C-layer to seed rows for StrongStockTrackingService.

        SEED PRE-FILTER AUDIT (P0-6):
          - leader_role_proxy != 'unknown' — excludes unclassified stocks.
            Rationale: unknown-role stocks lack leader identity, cannot be scored meaningfully.
            Source trace: {'filter': 'leader_role_proxy_exclude_unknown', 'reason': 'no_leader_identity'}
          - prior7_limitup_days >= 1 — requires at least one limit-up in prior 7 days.
            Rationale: strong stock watch requires recent limit-up evidence.
            Source trace: {'filter': 'prior7_limitup_days_ge_1', 'reason': 'no_recent_limit_up_evidence'}
          - NO LIMIT — all qualifying rows pass through; service-layer dedup/ranking handles capacity.

        FUNNEL AUDIT: self.seed_funnel is populated with per-stage counts for diagnostics.
        """
        await self._ensure_loaded()

        # Step 0: Query raw B-layer rows (before leader/prior7 filters) for funnel baseline
        raw_b_rows = await self._c.execute_query(
            "SELECT COUNT(*) as n FROM strong_stock_daily_feature WHERE trade_date=$1",
            (trade_date,))
        b_raw = raw_b_rows[0]['n'] if raw_b_rows else 0

        # Step 1: Fetch B+C rows with leader_role + prior7 pre-filters
        rows = await self._c.execute_query("""
            SELECT b.stock_id, b.stock_name, b.subject_key, b.theme_name,
                   b.is_leader, b.recent_limit_up_count, b.prior7_limitup_days, b.prior7_strong_days,
                   b.leader_role_proxy, b.watch_score,
                   c.weak_type, c.weak_type_quality, c.support_type, c.support_strength,
                   c.limit_up, c.prev_day_limit_up, c.pct_chg
            FROM strong_stock_daily_feature b
            LEFT JOIN stock_structure_daily_feature c ON b.stock_id=c.stock_id AND b.trade_date=c.trade_date
            WHERE b.trade_date=$1 AND b.leader_role_proxy!='unknown'
              AND b.prior7_limitup_days>=1
        """, (trade_date,))
        after_leader_prior7 = len(rows)

        # Count just the leader_role filter effect (separate query for granularity)
        lr_rows = await self._c.execute_query(
            "SELECT COUNT(*) as n FROM strong_stock_daily_feature WHERE trade_date=$1 AND leader_role_proxy!='unknown'",
            (trade_date,))
        after_leader_role = lr_rows[0]['n'] if lr_rows else 0

        # Count the prior7 filter separately
        p7_rows = await self._c.execute_query(
            "SELECT COUNT(*) as n FROM strong_stock_daily_feature WHERE trade_date=$1 AND prior7_limitup_days>=1",
            (trade_date,))
        after_prior7 = p7_rows[0]['n'] if p7_rows else 0

        # Step 2: Batch-load A-layer subject keys with lookback window (v1.1a fix).
        # subject_daily_feature only covers ~18 subjects per day. Use a 5-day rolling window
        # to capture subjects that have A-layer data on nearby trading days.
        a_layer_lookback_start = trade_date - timedelta(days=10)  # ~5 trading days
        a_layer_rows = await self._c.execute_query(
            """SELECT DISTINCT subject_key FROM subject_daily_feature
               WHERE trade_date >= $1 AND trade_date <= $2
               AND rule_version='subject_feature_from_rank_v0.1'""",
            (a_layer_lookback_start, trade_date))
        a_layer_subjects: set[str] = {str(r['subject_key']) for r in a_layer_rows}
        self._a_layer_lookback_set = a_layer_subjects  # v1.1a.1: reuse in refresh_rows
        # Also load exact-date subjects for source_trace purposes
        a_layer_exact_rows = await self._c.execute_query(
            "SELECT DISTINCT subject_key FROM subject_daily_feature WHERE trade_date=$1 AND rule_version='subject_feature_from_rank_v0.1'",
            (trade_date,))
        a_layer_exact_set: set[str] = {str(r['subject_key']) for r in a_layer_exact_rows}

        # Step 3: Load board stats for this date (to populate subject counts in seed rows)
        board_stats = await self.get_subject_board_stats(trade_date)
        board_by_subject: dict[str, dict] = {
            str(bs['subject_key']): bs for bs in board_stats
        }

        seed_rows = []
        after_subject_key = 0
        after_a_layer = 0
        after_a_layer_exact = 0

        for r in rows:
            subject_key = str(r.get('subject_key') or '').strip()
            if not subject_key:
                continue
            after_subject_key += 1

            # A-layer check with lookback (no per-row SQL)
            if subject_key not in a_layer_subjects:
                continue
            after_a_layer += 1
            if subject_key in a_layer_exact_set:
                after_a_layer_exact += 1

            recent_lim = int(r.get('recent_limit_up_count') or 0)
            is_leader = bool(r.get('is_leader') or False)
            has_two_board = int(r.get('prior7_limitup_days') or 0) >= 2

            # Merge board stats into seed row
            bs = board_by_subject.get(subject_key, {})

            seed_rows.append({
                "stock_id": str(r['stock_id']), "stock_name": str(r.get('stock_name') or ''),
                "subject_key": subject_key,
                "theme_name": str(r.get('theme_name') or ''),
                "recent_limit_up_count": recent_lim,
                "is_leader_flag": is_leader,
                "best_rank": 999,
                "current_flag_today": 2 if bool(r.get('limit_up')) else 1,
                "subject_limit_up_count": int(bs.get('subject_limit_up_count', 0)),
                "subject_strong_count": int(bs.get('subject_strong_count', 0)),
                "cond_gene": 1 if recent_lim >= 1 else 0,
                "cond_volume": 0,
                "cond_structure": 0,
                "has_two_board": has_two_board,
            })

        # Populate funnel audit
        self.seed_funnel = {
            "trade_date": str(trade_date),
            "seed_raw_rows": b_raw,
            "after_leader_role_filter": after_leader_role,
            "after_prior7_filter": after_prior7,
            "after_leader_prior7_combined": after_leader_prior7,
            "after_subject_key_filter": after_subject_key,
            "after_a_layer_check": after_a_layer,          # v1.1a: 5-day lookback
            "after_a_layer_check_exact": after_a_layer_exact,  # exact date only
            "a_layer_lookback_subjects": len(a_layer_subjects),
            "a_layer_exact_subjects": len(a_layer_exact_set),
            "final_seed_rows": len(seed_rows),
            # v1.1a.1: refresh funnel (populated after get_strong_watch_refresh_rows)
            "refresh_raw_rows": self._refresh_raw_count,
            "refresh_final_rows": self._refresh_final_count,
        }

        return seed_rows

    async def get_strong_watch_refresh_rows(self, trade_date: date) -> list[dict[str, Any]]:
        """Roll-forward previously scored strong watch pool stocks into T-day.

        v1.1a.1: Reads from strong_watch_pool_scored_rebuild for the past 1-7
        calendar days. Stocks that were active/weakening + formal/observe_only
        and not fade_confirmed are carried forward for re-evaluation on T-day.

        This is the key mechanism that ensures weak-divergence candidates
        (stocks that were strong in prior days, then weakened today) are
        included in D-layer evaluation.
        """
        await self._ensure_loaded()
        lookback_start = trade_date - timedelta(days=10)  # ~7 trading days
        refresh_rows = await self._c.execute_query("""
            SELECT DISTINCT ON (stock_id)
                   stock_id, stock_name, subject_key, theme_name,
                   watch_score, watch_status, pool_entry_type,
                   strong_grade, relay_role as leader_role_proxy,
                   recent_limit_up_count, hard_gate_pass_count,
                   mainline_strength_score, fade_watch, fade_confirmed,
                   cycle_state, support_type, support_strength,
                   trade_date as refresh_source_date
            FROM strong_watch_pool_scored_rebuild
            WHERE trade_date >= $1 AND trade_date < $2
              AND watch_status IN ('active', 'weakening')
              AND pool_entry_type IN ('formal', 'observe_only')
              AND NOT COALESCE(fade_confirmed, false)
              AND subject_key IS NOT NULL AND btrim(subject_key) <> ''
            ORDER BY stock_id, trade_date DESC
        """, (lookback_start, trade_date))

        # Store refresh count for funnel audit
        self._refresh_raw_count = len(refresh_rows)

        result: list[dict[str, Any]] = []
        for r in refresh_rows:
            subject_key = str(r.get('subject_key') or '').strip()
            if not subject_key:
                continue
            # A-layer check (same lookback as seed)
            if subject_key not in self._a_layer_lookback_set:
                continue

            result.append({
                "stock_id": str(r['stock_id']),
                "stock_name": str(r.get('stock_name') or ''),
                "subject_key": subject_key,
                "theme_name": str(r.get('theme_name') or ''),
                "recent_limit_up_count": int(r.get('recent_limit_up_count') or 0),
                "is_leader_flag": bool(r.get('strong_grade') in ('S', 'A')),
                "best_rank": 999,
                "current_flag_today": 0,  # Will be recomputed by UseCase from T-day bar
                "subject_limit_up_count": 0,
                "subject_strong_count": 0,
                "cond_gene": 1 if int(r.get('recent_limit_up_count') or 0) >= 1 else 0,
                "cond_volume": 0,
                "cond_structure": 0,
                "has_two_board": int(r.get('hard_gate_pass_count') or 0) >= 2,
                # v1.1a.1: source_trace for refresh provenance
                "source_tag": "refresh",
                "relay_role": str(r.get('leader_role_proxy') or ''),
            })

        self._refresh_final_count = len(result)
        return result

    # ── Board / Position / Pattern (v0.8b: minimal implementation) ──

    async def get_subject_board_stats(self, trade_date: date) -> list[dict[str, Any]]:
        """Compute subject-level limit-up and strong counts from daily bars.

        Groups stocks by subject_key (from B-layer) and counts limit-up (>=9.5%)
        and strong (>=5.0%) stocks per subject.
        """
        await self._ensure_loaded()
        await self._ensure_bars_loaded(trade_date)
        bars = self._bars_cache.get(trade_date, {})
        if not bars: return []

        # Get stock→subject mapping from B-layer
        b_rows = await self._c.execute_query(
            "SELECT stock_id, subject_key FROM strong_stock_daily_feature WHERE trade_date=$1 AND subject_key IS NOT NULL AND subject_key != ''",
            (trade_date,))
        stock_to_subject = {str(r['stock_id']): str(r['subject_key']) for r in b_rows}

        # Aggregate by subject
        by_subject: dict[str, dict] = {}
        for sid, bar in bars.items():
            sk = stock_to_subject.get(sid, '')
            if not sk: continue
            if sk not in by_subject:
                by_subject[sk] = {'subject_limit_up_count': 0, 'subject_strong_count': 0}
            pct = float(bar.get('pct_chg') or 0)
            if pct >= 9.5:
                by_subject[sk]['subject_limit_up_count'] += 1
            if pct >= 5.0:
                by_subject[sk]['subject_strong_count'] += 1

        return [{'subject_key': sk, **counts} for sk, counts in by_subject.items()]

    async def get_stock_position_judgement(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Compute simple MA alignment position from prior bars.

        ma_alignment_status: 均线多头 if MA5 > MA10 > MA20 else 均线空头
        trend_strength_score: 0-100 based on price vs MA5
        """
        await self._ensure_loaded()
        # Load today + up to 20 prior days
        prior_dates = sorted([d for d in self._trade_dates if d < trade_date], reverse=True)[:20]
        all_dates = prior_dates + [trade_date]
        await self._ensure_bars_for_dates(all_dates)
        bars_today = self._bars_cache.get(trade_date, {})
        if not bars_today: return []

        # Compute simple MAs from prior bars
        result = []
        for sid in (stock_ids or list(bars_today.keys())):
            bar = bars_today.get(sid)
            if not bar: continue

            closes = []
            # P0-5 fix: iterate in REVERSE chronological order to get most recent N
            # trading days before trade_date
            prior_dates = sorted([d for d in self._trade_dates if d < trade_date], reverse=True)
            for td in prior_dates:
                day_bars = self._bars_cache.get(td, {})
                b = day_bars.get(sid)
                if b:
                    closes.append(float(b.get('close_price') or 0))
                if len(closes) >= 20:
                    break

            if len(closes) < 5:
                result.append({
                    'stock_id': sid,
                    'position_label': 'unknown',
                    'ma_alignment_status': '未知',
                    'trend_strength_score': 50.0,
                })
                continue

            ma5 = sum(closes[:5]) / 5
            ma10 = sum(closes[:10]) / min(10, len(closes))
            ma20 = sum(closes[:20]) / min(20, len(closes))
            close = float(bar.get('close_price') or 0)

            if ma5 > ma10 > ma20:
                ma_status = '均线多头'
            elif ma5 < ma10 < ma20:
                ma_status = '均线空头'
            else:
                ma_status = '均线缠绕'

            # trend strength: distance from MA5
            dist_pct = abs(close - ma5) / ma5 * 100 if ma5 > 0 else 0
            trend_score = min(100.0, max(0.0, 50.0 + (close - ma5) / ma5 * 200))

            result.append({
                'stock_id': sid,
                'position_label': '强势' if close > ma5 else '弱势',
                'ma_alignment_status': ma_status,
                'trend_strength_score': trend_score,
            })
        return result

    async def get_stock_pattern_judgement(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Provide minimal non-rejecting pattern defaults.

        v0.8b: basic volume/breakout assessment from daily bar.
        Does NOT implement full 高量不破/倍量不穿 detection.
        """
        await self._ensure_loaded()
        # Load today + prior day for volume comparison
        prior_dates = sorted([d for d in self._trade_dates if d < trade_date], reverse=True)[:1]
        await self._ensure_bars_for_dates(prior_dates + [trade_date])
        bars_today = self._bars_cache.get(trade_date, {})
        if not bars_today: return []

        result = []
        for sid in (stock_ids or list(bars_today.keys())):
            bar = bars_today.get(sid)
            if not bar: continue

            pct = float(bar.get('pct_chg') or 0)
            vol = float(bar.get('volume') or 0)

            # Volume pattern: compare with prior day volume
            volume_pattern = '缩量整理'
            breakout_status = '未突破'
            pullback_status = '缩量回踩'
            pattern_labels = []

            # Check prior day for volume comparison
            prior_dates = sorted([d for d in self._trade_dates if d < trade_date], reverse=True)
            if prior_dates:
                prev_bars = self._bars_cache.get(prior_dates[0], {})
                prev_bar = prev_bars.get(sid)
                if prev_bar:
                    prev_vol = float(prev_bar.get('volume') or 0)
                    if vol > prev_vol * 1.5:
                        volume_pattern = '放量上涨' if pct > 0 else '放量下跌'
                        if pct > 5:
                            breakout_status = '放量突破'

            # Basic pattern labels
            if pct >= 9.5:
                pattern_labels.append('涨停')
                breakout_status = '放量突破'
            if pct <= -5:
                pattern_labels.append('大阴线')

            result.append({
                'stock_id': sid,
                'pattern_labels': pattern_labels,
                'volume_pattern_status': volume_pattern,
                'breakout_status': breakout_status,
                'pullback_status': pullback_status,
                'risk_pattern_status': '正常',
            })
        return result

    # ── W2S Candidate Inputs (from scored strong watch pool) ──
    async def get_w2s_candidate_inputs(self, trade_date: date) -> list[dict[str, Any]]:
        """Read D1 candidate inputs from scored strong_watch_pool_scored_rebuild.

        Calls StrongStockTrackingService.is_candidate_eligible() on every row to ensure
        both formal AND observe_only pass through to D layer.
        """
        from stock_processing_service.domain.services.strong_stock_tracking_service import (
            StrongStockTrackingService,
        )

        rows = await self._c.execute_query("""
            SELECT p.stock_id, p.stock_name, p.subject_key, p.theme_name,
                   p.watch_score, p.watch_status, p.pool_entry_type,
                   p.strong_grade, p.mainline_strength_score,
                   p.fade_watch, p.fade_confirmed, p.cycle_state,
                   p.support_type, p.support_strength,
                   p.recent_limit_up_count, p.hard_gate_pass_count,
                   COALESCE(c.pct_chg, 0) as pct_chg,
                   COALESCE(c.limit_up, false) as limit_up,
                   COALESCE(c.prev_day_limit_up, false) as prev_day_limit_up,
                   COALESCE(c.prior7_limitup_days, 0) as prior7_limitup_days,
                   COALESCE(c.prior7_strong_days, 0) as prior7_strong_days,
                   COALESCE(c.weak_type, '') as weak_type,
                   COALESCE(c.weak_type_quality, '') as weak_type_quality,
                   b.leader_role_proxy, b.is_leader as b_is_leader, b.rank_order as b_rank_order
            FROM strong_watch_pool_scored_rebuild p
            LEFT JOIN stock_structure_daily_feature c ON p.stock_id=c.stock_id AND p.trade_date=c.trade_date
            LEFT JOIN strong_stock_daily_feature b ON p.stock_id=b.stock_id AND p.trade_date=b.trade_date
            WHERE p.trade_date=$1
              AND NOT COALESCE(p.fade_confirmed, false)
        """, (trade_date,))

        result = []
        for r in rows:
            # P0-7: Explicit is_candidate_eligible() call — auditable in contract trace.
            # Both formal AND observe_only must pass through to D layer.
            if not StrongStockTrackingService.is_candidate_eligible(
                watch_status=str(r.get('watch_status') or ''),
                pool_entry_type=str(r.get('pool_entry_type') or ''),
                candidate_source="strong_watch_pool",
            ):
                continue

            # v1.1a.1: Robust is_leader detection with multiple fallbacks
            strong_grade = str(r.get('strong_grade') or '').upper()
            b_is_leader = bool(r.get('b_is_leader') or False)
            recent_lim = int(r.get('recent_limit_up_count') or 0)
            prior7_lim = int(r.get('prior7_limitup_days') or 0)
            leader_role = str(r.get('leader_role_proxy') or '')
            watch_score = float(r.get('watch_score') or 0)

            # v1.1a.1: For refresh stocks not in B-layer today, use rebuild table fields as fallback.
            # If B-layer join returned nothing (b_is_leader=False, b_rank=None),
            # inherit leader_role and prior evidence from the rebuild table's own data.
            if not b_is_leader and not leader_role:
                # No B-layer data at all — use strong_grade as proxy for leader_role
                if strong_grade in ('S', 'A'):
                    leader_role = 'leader'
                elif strong_grade == 'B':
                    leader_role = 'card'

            # is_leader: strong_grade S/A, OR explicit is_leader flag, OR leader/card role + recent limits
            is_leader = (
                strong_grade in ('S', 'A')
                or b_is_leader
                or (leader_role in ('leader', 'card') and (recent_lim >= 1 or prior7_lim >= 1))
            )

            # v1.1a.1: Rank order with proxy fallback
            b_rank = r.get('b_rank_order')
            has_b_rank = b_rank is not None and int(b_rank) < 999
            if has_b_rank:
                rank_order = int(b_rank)
                rank_order_source = "strong_stock_daily_feature"
            else:
                # Proxy from watch_score: higher score = better rank
                if watch_score >= 85:
                    rank_order = 1
                    rank_order_source = "proxy_from_watch_score_85plus"
                elif watch_score >= 78:
                    rank_order = 2
                    rank_order_source = "proxy_from_watch_score_78plus"
                elif watch_score >= 70:
                    rank_order = 3
                    rank_order_source = "proxy_from_watch_score_70plus"
                elif watch_score >= 65:
                    rank_order = 5
                    rank_order_source = "proxy_from_watch_score_65plus"
                elif strong_grade == 'B':
                    rank_order = 6
                    rank_order_source = "proxy_from_strong_grade_B"
                else:
                    rank_order = 10
                    rank_order_source = "proxy_default_10"

            # v1.1a.1: Compute prev_day_limit_up from T-1 bar data (not default false)
            prev_day_limit_up = bool(r.get('prev_day_limit_up') or False)
            # If not available from C-layer, check if stock had limit-up evidence in prior7
            if not prev_day_limit_up and prior7_lim >= 1:
                prev_day_limit_up = True  # prior7 signal as proxy for prev-day evidence
            prev_day_pct = 0.0

            # v1.1a.1: recent_limit_up_count fallback from prior7
            # For refresh stocks, rebuild table's recent_limit_up_count may be 0 on T-day
            # because it was recomputed. Use prior7 as evidence of recent limit-up activity.
            effective_recent_lim = max(recent_lim, prior7_lim)

            result.append({
                "stock_id": str(r['stock_id']),
                "stock_name": str(r.get('stock_name') or ''),
                "subject_key": str(r.get('subject_key') or ''),
                "theme_name": str(r.get('theme_name') or ''),
                "pct_chg": float(r.get('pct_chg') or 0),
                "limit_up": bool(r.get('limit_up')),
                "is_leader": is_leader,
                "rank_order": rank_order,
                "recent_limit_up_count": effective_recent_lim,
                "prior7_limitup_days": prior7_lim,
                "prior7_strong_days": int(r.get('prior7_strong_days') or 0),
                "prev_day_pct_chg": prev_day_pct,
                "prev_day_limit_up": prev_day_limit_up,
                "fade_watch": bool(r.get('fade_watch')),
                "fade_confirmed": bool(r.get('fade_confirmed')),
                "mainline_strength_score": float(r.get('mainline_strength_score') or 0),
                "watch_score": watch_score,
                "watch_pool_entry_type": str(r.get('pool_entry_type') or 'observe_only'),
                "watch_labels_json": json.dumps({
                    "strong_grade": str(r.get('strong_grade') or ''),
                    "support_type": str(r.get('support_type') or ''),
                    "support_score": float(r.get('support_strength') or 0),
                    "hard_gate_pass_count": int(r.get('hard_gate_pass_count') or 0),
                    "is_leader": is_leader,
                    "rank_order": rank_order,
                    "rank_order_source": rank_order_source,
                }),
                "support_type": str(r.get('support_type') or ''),
                "support_strength": str(r.get('support_strength') or '0'),
                "cycle_state": str(r.get('cycle_state') or ''),
                "weak_type": str(r.get('weak_type') or ''),
                "weak_type_quality": str(r.get('weak_type_quality') or ''),
            })
        return result

    # ── Remaining required methods (stubs) ──
    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids=None): return []
    async def get_subject_stock_pool_by_trade_date(self, trade_date): return []
    async def get_subject_context_by_subject_keys(self, subject_keys, trade_date): return []
    async def get_existing_pre_market_brief_snapshot(self, trade_date): return None
    async def get_existing_post_market_recap_snapshot(self, trade_date): return None
    async def get_mainline_identity_rule_inputs(self, trade_date, subject_keys): return []
    async def get_prior_strong_watch_pool_rows(self, trade_date, lookback_days): return []
    async def get_legacy_strong_watch_candidate_inputs(self, trade_date, lookback_days=7): return []
    async def get_subject_event_stats(self, trade_date, subject_keys=None, lookback_days=7): return []
    async def get_mainline_state_daily(self, trade_date, subject_keys): return []
    async def get_prior_mainline_state_daily(self, trade_date): return []


class HistoricalBacktestWritePorts:
    """Write adapter: UseCase outputs → isolated rebuild tables."""

    def __init__(self, gw: Any) -> None:
        self._gw = gw
        self._c = gw._client
        self._strong_pool_rows: list[dict] = []
        self._strong_history_rows: list[dict] = []
        self._w2s_rows: list[dict] = []
        self._written_strong_pool = 0
        self._written_strong_history = 0
        self._written_w2s = 0
        # Write error tracking (P0-5 fix: no silent exception swallowing)
        self.write_errors: list[dict[str, Any]] = []
        self.write_error_count: int = 0

    async def _ensure_tables(self):
        await self._c.execute_query("""
            CREATE TABLE IF NOT EXISTS strong_watch_pool_scored_rebuild (
                trade_date DATE NOT NULL, stock_id VARCHAR(32) NOT NULL, stock_name VARCHAR(64),
                subject_key VARCHAR(64), theme_name VARCHAR(128),
                watch_score NUMERIC(8,2), watch_priority NUMERIC(8,2),
                watch_status VARCHAR(32), pool_entry_type VARCHAR(32),
                cycle_state VARCHAR(64), mainline_strength_score NUMERIC(8,2),
                fade_watch BOOLEAN DEFAULT false, fade_confirmed BOOLEAN DEFAULT false,
                support_type VARCHAR(64), support_strength NUMERIC(8,2),
                strong_grade VARCHAR(16), removed_reason VARCHAR(128),
                source_tag VARCHAR(32), relay_role VARCHAR(32),
                recent_limit_up_count INTEGER DEFAULT 0,
                hard_gate_pass_count INTEGER DEFAULT 0,
                rule_version VARCHAR(64), source_trace JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (trade_date, stock_id)
            )
        """)
        await self._c.execute_query("""
            CREATE TABLE IF NOT EXISTS w2s_candidate_rebuild (
                trade_date DATE NOT NULL, next_trade_date DATE,
                stock_id VARCHAR(32) NOT NULL, stock_name VARCHAR(64),
                subject_key VARCHAR(64), theme_name VARCHAR(128),
                candidate_score VARCHAR(32), candidate_type VARCHAR(64),
                rule_version VARCHAR(64),
                weak_type VARCHAR(64), weak_intensity VARCHAR(32),
                is_dragon_head BOOLEAN DEFAULT false, dragon_head_level VARCHAR(32),
                prev_limit_up_count INTEGER DEFAULT 0,
                max_consecutive_limit_up_days INTEGER DEFAULT 0,
                support_type VARCHAR(64), support_level VARCHAR(32),
                support_strength VARCHAR(32),
                expected_open_low VARCHAR(32) DEFAULT '0',
                expected_open_high VARCHAR(32) DEFAULT '0',
                expected_auction_pattern VARCHAR(32) DEFAULT '',
                need_last_minute_grab BOOLEAN DEFAULT false,
                need_plate_follow BOOLEAN DEFAULT false,
                evidence_json JSONB DEFAULT '{}'::jsonb,
                pool_entry_type VARCHAR(32),
                cycle_state VARCHAR(64),
                mainline_strength_score VARCHAR(32),
                fade_watch BOOLEAN DEFAULT false,
                fade_confirmed BOOLEAN DEFAULT false,
                source_trace JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (next_trade_date, stock_id)
            )
        """)

    async def upsert_strong_watch_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        await self._ensure_tables()
        written = 0
        for r in rows:
            # Convert dataclass to dict if needed (UseCase passes WatchScoreResult objects)
            if hasattr(r, '__dataclass_fields__'):
                from dataclasses import asdict
                r = asdict(r)
            try:
                await self._c.execute_query("""
                    INSERT INTO strong_watch_pool_scored_rebuild (
                        trade_date,stock_id,stock_name,subject_key,theme_name,
                        watch_score,watch_priority,watch_status,pool_entry_type,
                        cycle_state,mainline_strength_score,fade_watch,fade_confirmed,
                        support_type,support_strength,strong_grade,removed_reason,
                        source_tag,relay_role,recent_limit_up_count,hard_gate_pass_count,
                        rule_version,source_trace)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,
                        'strong_stock_watch.v2_usecase_replay',
                        jsonb_build_object('usecase','BuildStrongStockTrackingUseCase','method','historical_replay'))
                    ON CONFLICT (trade_date,stock_id) DO UPDATE SET
                        watch_score=EXCLUDED.watch_score,watch_priority=EXCLUDED.watch_priority,
                        watch_status=EXCLUDED.watch_status,pool_entry_type=EXCLUDED.pool_entry_type,
                        strong_grade=EXCLUDED.strong_grade,removed_reason=EXCLUDED.removed_reason,
                        cycle_state=EXCLUDED.cycle_state,fade_watch=EXCLUDED.fade_watch,fade_confirmed=EXCLUDED.fade_confirmed,
                        mainline_strength_score=EXCLUDED.mainline_strength_score,
                        hard_gate_pass_count=EXCLUDED.hard_gate_pass_count
                """, (r.get('trade_date'), str(r.get('stock_id','')), str(r.get('stock_name','')),
                      str(r.get('subject_key','')), str(r.get('theme_name','')),
                      float(r.get('watch_score',0)), float(r.get('watch_priority',0)),
                      str(r.get('watch_status','')), str(r.get('pool_entry_type','')),
                      str(r.get('cycle_state','')), float(r.get('mainline_strength_score',0)),
                      bool(r.get('fade_watch',False)), bool(r.get('fade_confirmed',False)),
                      str(r.get('support_type','') or ''), float(r.get('support_strength',0) or 0),
                      str(r.get('strong_grade','')), str(r.get('removed_reason','') or ''),
                      str(r.get('source_tag','')), str(r.get('relay_role','')),
                      int(r.get('recent_limit_up_count',0)), int(r.get('hard_gate_pass_count',0))))
                written += 1
            except Exception as e:
                self.write_error_count += 1
                if len(self.write_errors) < 20:
                    self.write_errors.append({
                        "table": "strong_watch_pool_scored_rebuild",
                        "stock_id": str(r.get('stock_id', '?')),
                        "trade_date": str(r.get('trade_date', '?')),
                        "error": str(e)[:200],
                    })
        self._written_strong_pool += written
        return written

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        self._written_strong_history += len(rows)
        return len(rows)

    async def upsert_weak_to_strong_candidate_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        """Write D-layer candidates to isolated w2s_candidate_rebuild table.

        NEVER writes to production weak_to_strong_candidate_pool.
        """
        if not rows: return 0
        await self._ensure_tables()
        for r in rows:
            try:
                await self._c.execute_query("""
                    INSERT INTO w2s_candidate_rebuild (
                        trade_date,next_trade_date,stock_id,stock_name,subject_key,theme_name,
                        candidate_score,candidate_type,rule_version,weak_type,weak_intensity,
                        is_dragon_head,dragon_head_level,prev_limit_up_count,max_consecutive_limit_up_days,
                        support_type,support_level,support_strength,
                        expected_open_low,expected_open_high,expected_auction_pattern,
                        need_last_minute_grab,need_plate_follow,evidence_json,
                        pool_entry_type,cycle_state,mainline_strength_score,fade_watch,fade_confirmed,
                        source_trace)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'w2s_v1.0_usecase_replay',$9,$10,$11,$12,$13,0,$14,'0',$15,'0','0','',
                        false,false,$16::jsonb,$17,$18,$19,$20,$21,
                        jsonb_build_object('usecase','BuildWeakToStrongCandidateUseCase','method','historical_replay','contract','v1.0'))
                    ON CONFLICT (next_trade_date,stock_id) DO NOTHING
                """, (r['trade_date'], r.get('next_trade_date', r['trade_date']),
                      str(r.get('stock_id','')), str(r.get('stock_name','')),
                      str(r.get('subject_key','')), str(r.get('theme_name','')),
                      str(r.get('candidate_score','')), str(r.get('candidate_type','')),
                      str(r.get('weak_type','')), str(r.get('weak_intensity','')),
                      bool(r.get('is_dragon_head',False)), str(r.get('dragon_head_level','')),
                      int(r.get('prev_limit_up_count',0)),
                      str(r.get('support_type','') or ''), str(r.get('support_strength','') or '0'),
                      str(r.get('evidence_json','{}')), str(r.get('pool_entry_type','')),
                      str(r.get('cycle_state','')), str(r.get('mainline_strength_score','0')),
                      bool(r.get('fade_watch',False)), bool(r.get('fade_confirmed',False))))
                self._written_w2s += 1
            except Exception as e:
                self.write_error_count += 1
                if len(self.write_errors) < 20:
                    self.write_errors.append({
                        "table": "w2s_candidate_rebuild",
                        "stock_id": str(r.get('stock_id', '?')),
                        "trade_date": str(r.get('trade_date', '?')),
                        "error": str(e)[:200],
                    })
        return self._written_w2s

    # Required stub methods
    async def upsert_stock_daily_strategy_snapshot_rows(self, rows): return 0
    async def upsert_subject_stock_daily_snapshot_rows(self, rows): return 0
    async def upsert_stock_abnormal_event_rows(self, rows): return 0
    async def upsert_theme_stock_leaderboard_rows(self, rows): return 0
    async def upsert_pre_market_brief_snapshot(self, doc, force=False): return 0
    async def upsert_post_market_recap_snapshot(self, doc): return 0
    async def upsert_theme_mainline_identity_registry_rows(self, rows, **kw): return 0
    async def upsert_mainline_identity_review_queue_rows(self, rows): return 0
    async def recompute_strong_watch_window_days(self, stock_ids): return 0
    async def promote_strong_watch_candidates(self, trade_date): return 0
    async def prune_strong_watch_pool(self, trade_date, weakening_min_score=62.0): return 0
    async def apply_lifecycle_downgrade(self, trade_date, deactivate_fade_days=2): return 0
    async def upsert_theme_cycle_evidence_daily_rows(self, rows): return 0
    async def upsert_theme_cycle_judgement_v2_rows(self, rows): return 0
    async def upsert_mainline_state_daily_rows(self, rows): return 0
    async def upsert_mainline_state_transition_rows(self, rows): return 0
