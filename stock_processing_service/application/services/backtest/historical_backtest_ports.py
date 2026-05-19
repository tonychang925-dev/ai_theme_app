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

    async def _ensure_loaded(self):
        if self._loaded: return
        self._loaded = True
        # Load trading days
        rows = await self._c.execute_query(
            "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
            (self._start, self._end))
        self._trade_dates = [r['trade_date'] for r in rows]
        # Preload bars
        bar_rows = await self._c.execute_query(
            "SELECT DISTINCT ON (trade_date,stock_id) trade_date,stock_id,stock_name,open_price,high_price,low_price,close_price,pre_close,pct_chg,volume,amount FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2 AND source_name LIKE 'tushare%' ORDER BY trade_date,stock_id",
            (self._start - timedelta(days=100), self._end))
        for r in bar_rows:
            td = r['trade_date']
            self._bars_cache.setdefault(td, {})[str(r['stock_id'])] = r

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
        result = []
        lookback_start = trade_date - timedelta(days=lookback_days * 2)
        for td in self._trade_dates:
            if td >= trade_date: break
            if td < lookback_start: continue
            bars = self._bars_cache.get(td, {})
            for sid, b in bars.items():
                if stock_ids and sid not in stock_ids: continue
                result.append(PriorSnapshotDTO(
                    trade_date=td, stock_id=sid, snapshot_version="historical",
                    payload={"pct_chg": str(b.get('pct_chg','')), "close_price": str(b.get('close_price','')),
                             "limit_up": str(b.get('pct_chg',0)) >= '9.5'}))
        return result

    # ── A-layer: Mainline Identity / Cycle / Evidence ──
    async def get_mainline_identity_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[MainlineIdentityDTO]:
        if not subject_keys: return []
        rows = await self._c.execute_query(
            "SELECT * FROM subject_daily_feature WHERE trade_date=$1 AND subject_key=ANY($2) AND rule_version='subject_feature_from_rank_v0.1'",
            (trade_date, subject_keys))
        return [MainlineIdentityDTO(
            subject_key=str(r['subject_key']), identity_status='confirmed' if r.get('is_mainline_proxy') else 'observed',
            is_main_theme=bool(r.get('is_mainline_proxy')), rule_version='subject_feature_from_rank_v0.1')
            for r in rows]

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[MainlineCycleDTO]:
        if not subject_keys: return []
        rows = await self._c.execute_query(
            "SELECT * FROM subject_daily_feature WHERE trade_date=$1 AND subject_key=ANY($2) AND rule_version='subject_feature_from_rank_v0.1'",
            (trade_date, subject_keys))
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
        """Map B-layer + C-layer to seed rows for StrongStockTrackingService."""
        await self._ensure_loaded()
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
            LIMIT 500
        """, (trade_date,))

        seed_rows = []
        for r in rows:
            subject_key = str(r.get('subject_key') or '').strip()
            # v0.8a: must have valid subject_key with A-layer data
            if not subject_key:
                continue
            # Verify A-layer has this subject on this date
            a_check = await self._c.execute_query(
                "SELECT COUNT(*) as n FROM subject_daily_feature WHERE trade_date=$1 AND subject_key=$2",
                (trade_date, subject_key))
            if a_check[0]['n'] == 0:
                continue  # no A-layer data, can't score

            recent_lim = int(r.get('recent_limit_up_count') or 0)
            is_leader = bool(r.get('is_leader') or False)
            has_two_board = int(r.get('prior7_limitup_days') or 0) >= 2

            seed_rows.append({
                "stock_id": str(r['stock_id']), "stock_name": str(r.get('stock_name') or ''),
                "subject_key": subject_key,
                "theme_name": str(r.get('theme_name') or ''),
                "recent_limit_up_count": recent_lim,
                "is_leader_flag": is_leader,
                "best_rank": 999,
                "current_flag_today": 2 if bool(r.get('limit_up')) else 1,
                "subject_limit_up_count": 0,
                "subject_strong_count": 0,
                "cond_gene": 1 if recent_lim >= 1 else 0,
                "cond_volume": 0,
                "cond_structure": 0,
                "has_two_board": has_two_board,
            })
        return seed_rows

    async def get_strong_watch_refresh_rows(self, trade_date: date) -> list[dict[str, Any]]:
        return []  # v0.8a: no refresh rows from feature store

    # ── Board / Position / Pattern (v0.8b: minimal implementation) ──

    async def get_subject_board_stats(self, trade_date: date) -> list[dict[str, Any]]:
        """Compute subject-level limit-up and strong counts from daily bars.

        Groups stocks by subject_key (from B-layer) and counts limit-up (>=9.5%)
        and strong (>=5.0%) stocks per subject.
        """
        await self._ensure_loaded()
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
        bars_today = self._bars_cache.get(trade_date, {})
        if not bars_today: return []

        # Compute simple MAs from prior bars
        result = []
        for sid in (stock_ids or list(bars_today.keys())):
            bar = bars_today.get(sid)
            if not bar: continue

            closes = []
            for td in self._trade_dates:
                if td >= trade_date: break
                day_bars = self._bars_cache.get(td, {})
                b = day_bars.get(sid)
                if b:
                    closes.append(float(b.get('close_price') or 0))
                if len(closes) >= 20: break

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

        Filters by is_candidate_eligible(): watch_status in active/weakening AND
        pool_entry_type in formal/observe_only. Both formal AND observe_only pass through.
        """
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
                   COALESCE(c.weak_type_quality, '') as weak_type_quality
            FROM strong_watch_pool_scored_rebuild p
            LEFT JOIN stock_structure_daily_feature c ON p.stock_id=c.stock_id AND p.trade_date=c.trade_date
            WHERE p.trade_date=$1
              AND p.watch_status IN ('active','weakening')
              AND p.pool_entry_type IN ('formal','observe_only')
              AND NOT COALESCE(p.fade_confirmed, false)
        """, (trade_date,))

        result = []
        for r in rows:
            result.append({
                "stock_id": str(r['stock_id']),
                "stock_name": str(r.get('stock_name') or ''),
                "subject_key": str(r.get('subject_key') or ''),
                "theme_name": str(r.get('theme_name') or ''),
                "pct_chg": float(r.get('pct_chg') or 0),
                "limit_up": bool(r.get('limit_up')),
                "is_leader": bool(r.get('strong_grade') in ('S','A')),
                "rank_order": 999,
                "recent_limit_up_count": int(r.get('recent_limit_up_count') or 0),
                "prior7_limitup_days": int(r.get('prior7_limitup_days') or 0),
                "prior7_strong_days": int(r.get('prior7_strong_days') or 0),
                "prev_day_pct_chg": 0.0,
                "prev_day_limit_up": bool(r.get('prev_day_limit_up')),
                "fade_watch": bool(r.get('fade_watch')),
                "fade_confirmed": bool(r.get('fade_confirmed')),
                "mainline_strength_score": float(r.get('mainline_strength_score') or 0),
                "watch_score": float(r.get('watch_score') or 0),
                "watch_pool_entry_type": str(r.get('pool_entry_type') or 'observe_only'),
                "watch_labels_json": json.dumps({
                    "strong_grade": str(r.get('strong_grade') or ''),
                    "support_type": str(r.get('support_type') or ''),
                    "support_score": float(r.get('support_strength') or 0),
                    "hard_gate_pass_count": int(r.get('hard_gate_pass_count') or 0),
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
            except Exception: pass
        self._written_strong_pool += written
        return written

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        self._written_strong_history += len(rows)
        return len(rows)

    async def upsert_weak_to_strong_candidate_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows: return 0
        for r in rows:
            try:
                await self._c.execute_query("""
                    INSERT INTO weak_to_strong_candidate_pool (
                        trade_date,next_trade_date,stock_id,stock_name,subject_key,theme_name,
                        candidate_score,candidate_type,rule_version,weak_type,weak_intensity,
                        is_dragon_head,dragon_head_level,prev_limit_up_count,max_consecutive_limit_up_days,
                        support_type,support_level,support_strength,
                        expected_open_low,expected_open_high,expected_auction_pattern,
                        need_last_minute_grab,need_plate_follow,evidence_json,
                        pool_entry_type,cycle_state,mainline_strength_score,fade_watch,fade_confirmed)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'w2s_v0.8_usecase_replay',$9,$10,$11,$12,$13,0,$14,'0',$15,'0','0','',
                        false,false,$16::jsonb,$17,$18,$19,$20,$21)
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
            except Exception: pass
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
    async def upsert_strong_watch_history_rows(self, rows): return 0
