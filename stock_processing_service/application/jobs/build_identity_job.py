from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult, SubjectEventStatsDTO
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.identity_decider import IdentityDecider
from stock_processing_service.domain.services.identity_llm_review_service import IdentityLLMReviewService
from stock_processing_service.domain.services.identity_rule_engine import IdentityRuleEngine, IdentityRuleInput
from stock_processing_service.domain.services.identity_scoring_service import IdentityScoringService
from stock_processing_service.domain.services.one_day_tour_detector import OneDayTourDetector
from stock_processing_service.domain.services.enhanced_mainline_judgement_service import (
    EnhancedMainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    IdempotencyPort,
    StockEventPort,
    StockReadPort,
)


class BuildIdentityJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: AlgorithmStateWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        scoring_service: IdentityScoringService | None = None,
        tour_detector: OneDayTourDetector | None = None,
        llm_review_service: IdentityLLMReviewService | None = None,
        decider: IdentityDecider | None = None,
        rule_engine: IdentityRuleEngine | None = None,
        enhanced_service: EnhancedMainlineJudgementService | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._scoring_service = scoring_service or IdentityScoringService()
        self._tour_detector = tour_detector or OneDayTourDetector()
        self._llm_review_service = llm_review_service or IdentityLLMReviewService()
        self._decider = decider or IdentityDecider()
        self._rule_engine = rule_engine or IdentityRuleEngine()
        self._enhanced_service = enhanced_service or EnhancedMainlineJudgementService()

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _normalize_rows(rows: list[dict[str, Any]]) -> list[Any]:
        """Convert dict rows to SimpleNamespace so attribute access works.
        
        Fills in missing keys that the DB may not return but the Job expects:
        - subject_name: falls back to subject_key (pool rows lack this column)
        - metadata: defaults to {}
        - theme_context_tags: defaults to []
        """
        result: list[Any] = []
        for r in rows:
            if isinstance(r, dict):
                r_filled = dict(r)
                if "subject_name" not in r_filled:
                    r_filled["subject_name"] = r_filled.get("subject_key", "")
                if "metadata" not in r_filled:
                    r_filled["metadata"] = {}
                if "theme_context_tags" not in r_filled:
                    r_filled["theme_context_tags"] = []
                result.append(SimpleNamespace(**r_filled))
            else:
                result.append(r)
        return result

    @staticmethod
    def _map_theme_tier_to_status(theme_tier: str, one_day_tour_flag: bool) -> str:
        """Map EnhancedMainlineJudgementService theme_tier to identity_status."""
        if theme_tier == "main":
            return "observed" if one_day_tour_flag else "confirmed"
        elif theme_tier == "strong_branch":
            return "observed"
        else:
            return "dismissed"

    # ── JSONL enrichment helpers ──────────────────────────────────────────
    _HISTORY_DIR = Path("theme_data_complete/history")
    _STOCK_DAILY_DIR = Path("theme_data_complete/stock_daily")

    @staticmethod
    def _compute_limit_up_from_bars(
        pool_rows: list[Any], bars_by_stock: dict[str, Any]
    ) -> tuple[int, float]:
        """Compute limit_up_count and limit_up_ratio_today from bars data (already in memory)."""
        if not pool_rows:
            return 0, 0.0
        limit_up_count = 0
        for row in pool_rows:
            bar = bars_by_stock.get(row.stock_id)
            if bar is None:
                continue
            limit_price = getattr(bar, 'limit_up_price', None)
            close_price = getattr(bar, 'close_price', None)
            if limit_price is not None and limit_price > 0 and close_price is not None and close_price >= limit_price:
                limit_up_count += 1
            elif getattr(bar, 'pct_chg', None) is not None:
                try:
                    if float(bar.pct_chg) >= 9.5:
                        limit_up_count += 1
                except (ValueError, TypeError):
                    pass
        return limit_up_count, limit_up_count / len(pool_rows)

    @classmethod
    def _read_history_jsonl(cls, subject_key: str, trade_date: date) -> dict[str, Any]:
        """Read history JSONL for a subject and compute heat_latest, avg_heat_5d.
        
        Returns dict with keys: heat_latest, avg_heat_5d.
        heat=1 in JSONL is calibrated to 100 (old chain: heat*100 if raw<=1.2).
        """
        result = {"heat_latest": Decimal("0"), "avg_heat_5d": Decimal("0")}
        hist_file = cls._HISTORY_DIR / f"{subject_key}_history.jsonl"
        if not hist_file.exists():
            return result

        window_start = trade_date - timedelta(days=4)
        days_with_heat: set[str] = set()

        try:
            with open(hist_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rank_date_str = (entry.get("rankDate") or "")[:10]
                    if not rank_date_str:
                        continue
                    try:
                        rank_date = date.fromisoformat(rank_date_str)
                    except ValueError:
                        continue
                    if window_start <= rank_date <= trade_date:
                        days_with_heat.add(rank_date_str)
        except Exception:
            pass

        if not days_with_heat:
            return result

        raw_latest = Decimal("1") if trade_date.isoformat() in days_with_heat else Decimal("0")
        raw_avg = Decimal(str(len(days_with_heat))) / Decimal("5")

        # Old chain calibration: heat * 100 if raw <= 1.2
        heat_latest = raw_latest * 100 if raw_latest <= Decimal("1.2") else raw_latest
        avg_heat_5d = raw_avg * 100 if raw_avg <= Decimal("1.2") else raw_avg

        result["heat_latest"] = heat_latest
        result["avg_heat_5d"] = avg_heat_5d
        return result

    @classmethod
    def _read_stock_daily_jsonl(cls, subject_key: str, trade_date: date) -> dict[str, Any]:
        """Read stock_daily JSONL for a subject + date. Compute per-subject aggregates.
        
        Returns dict with: net_inflow, limit_up_count, limit_up_ratio.
        main_net_inflow is at index [34]; pct_chg is at index [10].
        """
        result = {
            "net_inflow": Decimal("0"),
            "limit_up_count": 0,
            "limit_up_ratio": 0.0,
            "stock_count": 0,
            "strong_count": 0,
            "strong_ratio": 0.0,
        }
        sd_file = cls._STOCK_DAILY_DIR / f"{subject_key}_{trade_date.isoformat()}_stocks.jsonl"
        if not sd_file.exists():
            return result

        total_inflow = Decimal("0")
        limit_up_count = 0
        strong_count = 0
        stock_count = 0

        try:
            with open(sd_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        arr = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(arr, list) or len(arr) < 38:
                        continue
                    stock_count += 1

                    # main_net_inflow at index [34]
                    raw_inflow = arr[34]
                    if raw_inflow is not None:
                        try:
                            total_inflow += Decimal(str(raw_inflow))
                        except Exception:
                            pass

                    # pct_chg at index [10]; approximate limit_up: pct_chg >= 9.5%
                    try:
                        pct = float(arr[10]) if arr[10] is not None else 0.0
                    except (ValueError, TypeError):
                        pct = 0.0
                    if pct >= 9.5:
                        limit_up_count += 1
                    if pct >= 5.0:
                        strong_count += 1
        except Exception:
            pass

        result["net_inflow"] = total_inflow
        result["limit_up_count"] = limit_up_count
        result["stock_count"] = stock_count
        result["limit_up_ratio"] = (limit_up_count / stock_count) if stock_count > 0 else 0.0
        result["strong_count"] = strong_count
        result["strong_ratio"] = (strong_count / stock_count) if stock_count > 0 else 0.0
        return result

    @classmethod
    def _compute_5d_metrics(
        cls, subject_key: str, trade_date: date, _cache: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Read stock_daily JSONL for 7-day window; return board_boom, net_inflow, limit_up, and event proxy stats.

        Event proxy fields (derived from market data when DB has no event metadata):
        - strong_event_count_7d: days with strong_ratio >= 10% OR limit_up_count >= 2
        - event_count_3d: days in last 3 with strong_ratio >= 5%
        - event_recency_days: days since most recent strong day (0=today, 99=none)
        - event_strength_score: scaled avg strong_ratio over 7d (0-100)
        - event_continuity_score: max consecutive strong days * 20 (0-100)
        """
        if _cache is None:
            _cache = {}
        daily: list[dict[str, Any]] = []
        for offset in range(7):  # Extended to 7 days for event proxy computation
            d = trade_date - timedelta(days=offset)
            cache_key = f"{subject_key}:{d.isoformat()}"
            if cache_key not in _cache:
                _cache[cache_key] = cls._read_stock_daily_jsonl(subject_key, d)
            daily.append(_cache[cache_key])

        today = daily[0]  # offset 0 = trade_date
        # 5-day metrics (computed from first 5 days, backward compatible)
        five_day = daily[:5]
        board_boom_days = sum(1 for sd in five_day if sd["limit_up_count"] >= 2)
        total_inflow = sum((sd["net_inflow"] for sd in five_day), start=Decimal("0"))
        days_with_inflow = sum(1 for sd in five_day if sd["net_inflow"] > 0)
        # Market heat proxy: a day is "hot" if strong_ratio >= 10% or limit_up_count >= 2
        days_hot_5d = sum(1 for sd in five_day if sd.get("strong_ratio", 0.0) >= 0.10 or sd.get("limit_up_count", 0) >= 2)

        # ── Event proxy metrics from 7-day window ──
        # Strong event day: strong_ratio >= 10% OR limit_up_count >= 2
        def _is_strong_day(sd: dict[str, Any]) -> bool:
            return sd.get("strong_ratio", 0.0) >= 0.10 or sd.get("limit_up_count", 0) >= 2

        def _is_event_day(sd: dict[str, Any]) -> bool:
            return sd.get("strong_ratio", 0.0) >= 0.05

        strong_days = [sd for sd in daily if _is_strong_day(sd)]
        strong_event_count_7d = len(strong_days)

        # Event count in 3-day window
        event_count_3d = sum(1 for sd in daily[:3] if _is_event_day(sd))

        # Event recency: offset of most recent strong day (0 = today, 99 = none)
        event_recency_days = 99
        for i, sd in enumerate(daily):
            if _is_strong_day(sd):
                event_recency_days = i
                break

        # Event strength score: scaled avg strong_ratio over 7d
        strong_ratios = [sd.get("strong_ratio", 0.0) for sd in daily]
        avg_sr = sum(strong_ratios) / len(strong_ratios)
        event_strength_score = Decimal(str(round(min(avg_sr * 500, 100), 2)))

        # Event continuity score: max consecutive strong days * 25, capped at 100
        # (25 multiplier calibrated so 2 consecutive days=50 passes market_ok threshold
        #  — meaningful continuity in the 3-day data window)
        max_consecutive = 0
        cur = 0
        for sd in daily:
            if _is_strong_day(sd):
                cur += 1
                if cur > max_consecutive:
                    max_consecutive = cur
            else:
                cur = 0
        event_continuity_score = Decimal(str(min(max_consecutive * 25, 100)))

        return {
            "board_boom_days_5d": board_boom_days,
            "net_inflow_sum_5d": total_inflow,
            "net_inflow_days_5d": days_with_inflow,
            "limit_up_count_today": today["limit_up_count"],
            "limit_up_ratio_today": today["limit_up_ratio"],
            "stock_count_today": today["stock_count"],
            "strong_ratio_today": today.get("strong_ratio", 0.0),
            "days_hot_5d_proxy": days_hot_5d,
            # Event proxy fields
            "strong_event_count_7d_proxy": strong_event_count_7d,
            "event_count_3d_proxy": event_count_3d,
            "event_recency_days_proxy": event_recency_days,
            "event_strength_score_proxy": event_strength_score,
            "event_continuity_score_proxy": event_continuity_score,
        }


    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
    ) -> BuildResult:
        job_key = f"build_identity:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_identity",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # ── Feature flags ──
        USE_ENHANCED_MAINLINE = os.environ.get("USE_ENHANCED_MAINLINE", "0") == "1"
        DUAL_RUN_TRACE_ENABLED = os.environ.get("DUAL_RUN_TRACE", "1") == "1"

        raw_pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        pool_rows = self._normalize_rows(raw_pool_rows)
        subject_keys = sorted({row.subject_key for row in pool_rows})
        raw_contexts = await self._read_port.get_subject_context_by_subject_keys(subject_keys, trade_date) if subject_keys else []
        contexts = self._normalize_rows(raw_contexts)
        raw_bars = await self._read_port.get_stock_daily_bars(trade_date)
        bars = self._normalize_rows(raw_bars)

        # ── Fetch real event data from news_event/event_theme_map (Path A: fundamental fix) ──
        raw_event_stats = await self._read_port.get_subject_event_stats(
            trade_date, subject_keys
        ) if subject_keys else []
        # Normalize: handle both DTO objects and plain dicts from different adapters
        _normalized_event_stats: list[Any] = []
        for _es in raw_event_stats:
            if isinstance(_es, dict):
                _normalized_event_stats.append(SimpleNamespace(
                    subject_key=_es.get("subject_key", ""),
                    theme_name=_es.get("theme_name", ""),
                    today_event_count=_es.get("today_event_count", 0),
                    recent_event_count=_es.get("recent_event_count", 0),
                    distinct_event_days=_es.get("distinct_event_days", 0),
                    key_event_count=_es.get("key_event_count", 0),
                    sample_summaries=_es.get("sample_summaries", []),
                ))
            else:
                _normalized_event_stats.append(_es)
        event_stats_by_subject: dict[str, Any] = {
            es.subject_key: es for es in _normalized_event_stats
        }

        ctx_by_subject = {c.subject_key: c for c in contexts}
        bars_by_stock = {bar.stock_id: bar for bar in bars}

        identity_registry_rows: list[dict[str, Any]] = []
        review_queue_rows: list[dict[str, Any]] = []
        _comparisons: list[dict[str, Any]] = []

        grouped: dict[str, list[Any]] = {}
        for row in pool_rows:
            grouped.setdefault(row.subject_key, []).append(row)

        _sd_cache: dict[str, dict[str, Any]] = {}
        for subject_key, rows in grouped.items():
            subject_name = rows[0].subject_name
            context_tags = list((ctx_by_subject.get(subject_key).theme_context_tags if subject_key in ctx_by_subject else []) or [])

            pct_values: list[Decimal] = []
            for row in rows:
                bar = bars_by_stock.get(row.stock_id)
                if bar is not None:
                    pct_values.append(bar.pct_chg)
            avg_pct = sum(pct_values, start=Decimal("0")) / Decimal(str(len(pct_values) or 1))

            # ── Compute market stats for enhanced mainline service ──
            _strong_count = sum(1 for v in pct_values if float(v) >= 5.0)
            _leader_pct = max((float(v) for v in pct_values), default=0.0)
            _leader_lu = False
            for _row in rows:
                _bar = bars_by_stock.get(_row.stock_id)
                if _bar is not None:
                    _lp = float(getattr(_bar, 'limit_up_price', 0) or 0)
                    _cp = float(getattr(_bar, 'close_price', 0) or 0)
                    if _lp > 0 and _cp >= _lp:
                        _leader_lu = True
                        break

            context_metadata = (ctx_by_subject.get(subject_key).metadata if subject_key in ctx_by_subject else {}) or {}

            strong_event_count_7d = int(context_metadata.get("strong_event_count_7d") or 0)
            event_count_3d = int(context_metadata.get("event_count_3d") or 0)
            event_recency_days_raw = context_metadata.get("event_recency_days")
            event_recency_days = int(event_recency_days_raw) if event_recency_days_raw is not None else 99
            event_strength_score = self._d(context_metadata.get("event_strength_score"), default="0")
            event_continuity_score = self._d(context_metadata.get("event_continuity_score"), default="0")
            # ── JSONL enrichment: heat from theme_data_complete/history/ ──
            _heat_data = self._read_history_jsonl(subject_key, trade_date)
            heat_latest = _heat_data["heat_latest"]
            avg_heat_5d = _heat_data["avg_heat_5d"]
            # ── Bar-based enrichment: limit_up computed from actual bar data ──
            _lu_count, _lu_ratio = self._compute_limit_up_from_bars(rows, bars_by_stock)
            limit_up_count = _lu_count
            limit_up_ratio_today = Decimal(str(_lu_ratio))
            # ── JSONL enrichment: 7-day metrics from stock_daily files (board_boom + net_inflow + event proxy) ──
            _5d = self._compute_5d_metrics(subject_key, trade_date, _sd_cache)
            # ── Event proxy: when DB context_metadata is empty (always), use market-derived proxies ──
            if strong_event_count_7d == 0 and event_count_3d == 0:
                strong_event_count_7d = _5d["strong_event_count_7d_proxy"]
                event_count_3d = _5d["event_count_3d_proxy"]
                event_recency_days = _5d["event_recency_days_proxy"]
                event_strength_score = _5d["event_strength_score_proxy"]
                event_continuity_score = _5d["event_continuity_score_proxy"]
            board_boom_days_5d = _5d["board_boom_days_5d"]
            net_inflow_sum_5d = _5d["net_inflow_sum_5d"]
            net_inflow_days_5d = _5d["net_inflow_days_5d"]
            # Use JSONL-based limit_up for today if bar data didn't capture it
            if limit_up_count == 0 and _5d["limit_up_count_today"] > 0:
                limit_up_count = _5d["limit_up_count_today"]
                limit_up_ratio_today = Decimal(str(_5d["limit_up_ratio_today"]))
            # ── Heat fallback: if no JYHF heat data, use market heat proxy from stock_daily ──
            # "Hot" = strong_ratio >= 10% OR limit_up_count >= 2 (binary, matches old chain heat=1 semantics)
            if heat_latest == 0 and avg_heat_5d == 0:
                market_hot_today = (
                    _5d.get("strong_ratio_today", 0.0) >= 0.10
                    or _5d.get("limit_up_count_today", 0) >= 2
                )
                heat_latest = Decimal("100") if market_hot_today else Decimal("0")
                days_hot_5d = _5d.get("days_hot_5d_proxy", 0)
                avg_heat_5d = Decimal(str(days_hot_5d)) / Decimal("5") * Decimal("100")
            front_row_strength_score = self._d(context_metadata.get("front_row_strength_score"), default="0")
            front_row_alive_ratio = self._d(context_metadata.get("front_row_alive_ratio"), default="0")
            kline_support_hold = bool(context_metadata.get("kline_support_hold", False))
            platform_breakout_flag = bool(context_metadata.get("platform_breakout_flag", False))

            score = self._scoring_service.score(
                subject_key=subject_key,
                subject_name=subject_name,
                context_tags=context_tags,
                stock_count=len(rows),
            )
            tour_signal = self._tour_detector.detect(avg_pct_chg=avg_pct, stock_count=len(rows))
            rule_input = IdentityRuleInput(
                subject_key=subject_key,
                subject_name=subject_name,
                strong_event_count_7d=strong_event_count_7d,
                event_count_3d=event_count_3d,
                event_recency_days=event_recency_days,
                event_strength_score=event_strength_score,
                event_continuity_score=event_continuity_score,
                heat_latest=heat_latest,
                avg_heat_5d=avg_heat_5d,
                limit_up_count=limit_up_count,
                limit_up_ratio_today=limit_up_ratio_today,
                board_boom_days_5d=board_boom_days_5d,
                front_row_strength_score=front_row_strength_score,
                front_row_alive_ratio=front_row_alive_ratio,
                net_inflow_sum_5d=net_inflow_sum_5d,
                net_inflow_days_5d=net_inflow_days_5d,
                one_day_tour_flag=tour_signal.one_day_tour_flag,
                kline_support_hold=kline_support_hold,
                platform_breakout_flag=platform_breakout_flag,
            )
            rule = self._rule_engine.evaluate(rule_input)
            llm_verdict = self._llm_review_service.review(
                composite_score=rule.composite_score,
                one_day_tour_flag=tour_signal.one_day_tour_flag,
            )
            llm_verdict_for_decider = llm_verdict.verdict
            if llm_verdict_for_decider == "confirmed" and not rule.rule_is_main_theme:
                llm_verdict_for_decider = "review_pending"
            decision = self._decider.decide(
                composite_score=rule.composite_score,
                llm_verdict=llm_verdict_for_decider,
                one_day_tour_flag=tour_signal.one_day_tour_flag,
            )

            identity_row_old = {
                "trade_date": trade_date.isoformat(),
                "subject_key": subject_key,
                "subject_name": subject_name,
                "logic_score": str(rule.logic_score),
                "market_score": str(rule.market_score),
                "composite_score": str(rule.composite_score),
                "one_day_tour_flag": tour_signal.one_day_tour_flag,
                "continuity_signal": tour_signal.continuity_signal,
                "logic_ok": rule.logic_ok,
                "market_ok": rule.market_ok,
                "rule_is_main_theme": rule.rule_is_main_theme,
                "rule_reasons": rule.reasons,
                "legacy_composite_score": str(score.composite_score),
                "llm_verdict": llm_verdict.verdict,
                "llm_reason": llm_verdict.reason,
                "identity_status": decision.identity_status,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "source_trace_id": trace_id,
            }

            # ── Enhanced Mainline path (Path A: real event data from news_event/event_theme_map) ──
            _event_dto = event_stats_by_subject.get(subject_key)
            _event_stats = ThemeEventStats(
                subject_key=subject_key,
                theme_name=_event_dto.theme_name if _event_dto else subject_name,
                today_event_count=_event_dto.today_event_count if _event_dto else 0,
                recent_event_count=_event_dto.recent_event_count if _event_dto else 0,
                distinct_event_days=_event_dto.distinct_event_days if _event_dto else 0,
                key_event_count=_event_dto.key_event_count if _event_dto else 0,
                sample_summaries=list(_event_dto.sample_summaries) if _event_dto else [],
            )
            _market_stats = ThemeMarketStats(
                subject_key=subject_key,
                theme_name=subject_name,
                limit_up_count=limit_up_count,
                strong_stock_count=_strong_count,
                leader_pct_chg=_leader_pct,
                member_count=len(rows),
                leader_limit_up=_leader_lu,
            )
            _judgement = self._enhanced_service.build_judgement(
                trade_date=trade_date.isoformat(),
                event_stats=_event_stats,
                market_stats=_market_stats,
            )
            _new_status = self._map_theme_tier_to_status(
                _judgement.theme_tier, tour_signal.one_day_tour_flag
            )
            identity_row_new = {
                "trade_date": trade_date.isoformat(),
                "subject_key": subject_key,
                "subject_name": subject_name,
                "logic_score": str(_judgement.event_chain_score),
                "market_score": str(_judgement.market_recognition_score),
                "composite_score": str(_judgement.mainline_stability_score),
                "one_day_tour_flag": tour_signal.one_day_tour_flag,
                "continuity_signal": tour_signal.continuity_signal,
                "logic_ok": _judgement.event_chain_score >= 20.0,
                "market_ok": _judgement.market_recognition_score >= 35.0,
                "rule_is_main_theme": _judgement.is_main_theme,
                "rule_reasons": [_judgement.conclusion] + _judgement.evidence_logic + _judgement.evidence_market,
                "legacy_composite_score": str(score.composite_score),
                "llm_verdict": "enhanced",
                "llm_reason": _judgement.conclusion,
                "identity_status": _new_status,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "source_trace_id": trace_id,
            }

            # ── Dual-run comparison ──
            _comparisons.append({
                "subject_key": subject_key,
                "subject_name": subject_name,
                "old": {
                    "identity_status": identity_row_old["identity_status"],
                    "rule_is_main_theme": identity_row_old["rule_is_main_theme"],
                    "composite_score": identity_row_old["composite_score"],
                    "logic_score": identity_row_old["logic_score"],
                    "market_score": identity_row_old["market_score"],
                },
                "new": {
                    "identity_status": identity_row_new["identity_status"],
                    "rule_is_main_theme": identity_row_new["rule_is_main_theme"],
                    "composite_score": identity_row_new["composite_score"],
                    "logic_score": identity_row_new["logic_score"],
                    "market_score": identity_row_new["market_score"],
                    "theme_tier": _judgement.theme_tier,
                    "conclusion": _judgement.conclusion,
                },
                "agreement": identity_row_old["identity_status"] == identity_row_new["identity_status"],
            })

            if USE_ENHANCED_MAINLINE:
                identity_registry_rows.append(identity_row_new)
                _selected_row = identity_row_new
            else:
                identity_registry_rows.append(identity_row_old)
                _selected_row = identity_row_old

            if _selected_row["identity_status"] == "review_pending":
                review_queue_rows.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "subject_key": subject_key,
                        "subject_name": subject_name,
                        "reason": decision.reason if _selected_row is identity_row_old else _judgement.conclusion,
                        "llm_confidence": str(llm_verdict.confidence) if _selected_row is identity_row_old else "0.0",
                        "llm_verdict": _selected_row.get("llm_verdict", ""),
                        "rule_is_main_theme": _selected_row["rule_is_main_theme"],
                        "rule_reasons": _selected_row["rule_reasons"],
                        "snapshot_version": snapshot_version,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    }
                )

        # ── Write dual-run comparison JSON to tmp/ ──
        if _comparisons and DUAL_RUN_TRACE_ENABLED:
            _comparison_path = Path("tmp") / f"dual_run_identity_{trade_date.isoformat()}_{snapshot_version}.json"
            _comparison_path.parent.mkdir(parents=True, exist_ok=True)
            _comparison_payload = {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "new_path_active": USE_ENHANCED_MAINLINE,
                "total_subjects": len(_comparisons),
                "agreement_count": sum(1 for c in _comparisons if c["agreement"]),
                "disagreement_count": sum(1 for c in _comparisons if not c["agreement"]),
                "comparisons": _comparisons,
            }
            _comparison_path.write_text(json.dumps(_comparison_payload, ensure_ascii=False, indent=2, default=str))

        written_registry = await self._write_port.upsert_theme_mainline_identity_registry_rows(identity_registry_rows)
        written_review = await self._write_port.upsert_mainline_identity_review_queue_rows(review_queue_rows)

        await self._event_port.publish_stock_processing_event(
            EventEnvelope(
                event_id=str(uuid4()),
                event_name="snapshot_built",
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
                producer="stock_processing_service",
                occurred_at=datetime.now(timezone.utc),
                payload_version="v1",
                payload=SnapshotBuiltPayload(
                    domain="identity",
                    snapshot_version=snapshot_version,
                    object_name="theme_mainline_identity_registry",
                    row_count=written_registry,
                    success=True,
                ),
            )
        )
        published_events = ["snapshot_built"]

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "identity_rows": written_registry,
                "review_rows": written_review,
            },
        )

        return BuildResult(
            name="build_identity",
            trade_date=trade_date.isoformat(),
            affected_rows=written_registry + written_review,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "identity_registry_rows": written_registry,
                "identity_review_rows": written_review,
                "subject_count": len(grouped),
            },
            published_events=published_events,
        )
