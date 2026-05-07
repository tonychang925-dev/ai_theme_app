from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.contracts.dto import (
    BuildResult,
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectStockPoolDTO,
)
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PostMarketRecapSnapshot
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord
from stock_processing_service.domain.services.strong_watch_service import StrongWatchService
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    SnapshotWritePort,
)


class BuildPostMarketRecapJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: SnapshotWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        candidate_service: W2SCandidateService | None = None,
        strong_watch_service: StrongWatchService | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._cache_writer = SnapshotCacheWriter(cache_port)
        self._candidate_service = candidate_service or W2SCandidateService()
        self._strong_watch_service = strong_watch_service or StrongWatchService()

    @staticmethod
    def _d(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _normalize_stock_id(value: Any) -> str:
        stock_id = str(value or "").strip().upper()
        if not stock_id:
            return ""
        if "." in stock_id:
            return stock_id
        if len(stock_id) == 6 and stock_id.isdigit():
            if stock_id.startswith(("6", "9")):
                return f"{stock_id}.SH"
            if stock_id.startswith(("0", "2", "3")):
                return f"{stock_id}.SZ"
            if stock_id.startswith(("4", "8")):
                return f"{stock_id}.BJ"
        return stock_id

    @staticmethod
    def _to_stock_bar(row: Any, default_trade_date: date) -> StockBarDTO:
        if isinstance(row, StockBarDTO):
            return row
        p = dict(row or {})
        return StockBarDTO(
            trade_date=p.get("trade_date", default_trade_date),
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
            stock_name=str(p.get("stock_name", "")),
            open_price=BuildPostMarketRecapJob._d(p.get("open_price")),
            high_price=BuildPostMarketRecapJob._d(p.get("high_price")),
            low_price=BuildPostMarketRecapJob._d(p.get("low_price")),
            close_price=BuildPostMarketRecapJob._d(p.get("close_price")),
            pre_close=BuildPostMarketRecapJob._d(p.get("pre_close")),
            pct_chg=BuildPostMarketRecapJob._d(p.get("pct_chg")),
            volume=BuildPostMarketRecapJob._d(p.get("volume")),
            amount=BuildPostMarketRecapJob._d(p.get("amount")),
            limit_up_price=BuildPostMarketRecapJob._d(p.get("limit_up_price")),
            limit_down_price=BuildPostMarketRecapJob._d(p.get("limit_down_price")),
        )

    @staticmethod
    def _to_pool_row(row: Any, default_trade_date: date) -> SubjectStockPoolDTO:
        if isinstance(row, SubjectStockPoolDTO):
            return row
        p = dict(row or {})
        metadata = p.get("metadata")
        return SubjectStockPoolDTO(
            trade_date=p.get("trade_date", default_trade_date),
            subject_key=str(p.get("subject_key", "")),
            subject_name=str(p.get("subject_name") or p.get("theme_name") or p.get("subject_key") or ""),
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
            stock_name=p.get("stock_name"),
            pool_rank=p.get("pool_rank", p.get("rank_order")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    @staticmethod
    def _to_prior_row(row: Any, default_trade_date: date) -> PriorSnapshotDTO:
        if isinstance(row, PriorSnapshotDTO):
            return row
        p = dict(row or {})
        payload = p.get("payload")
        if not isinstance(payload, dict):
            payload = {}
            for key in ("open_price", "high_price", "low_price", "close_price", "pre_close", "pct_chg", "watch_score"):
                if p.get(key) is not None:
                    payload[key] = str(p.get(key))
        return PriorSnapshotDTO(
            trade_date=p.get("trade_date", default_trade_date),
            stock_id=BuildPostMarketRecapJob._normalize_stock_id(p.get("stock_id", "")),
            snapshot_version=str(p.get("snapshot_version", "")),
            payload=payload,
        )

    @staticmethod
    def _to_identity(row: Any) -> MainlineIdentityDTO:
        if isinstance(row, MainlineIdentityDTO):
            return row
        p = dict(row or {})
        return MainlineIdentityDTO(
            subject_key=str(p.get("subject_key", "")),
            identity_status=str(p.get("identity_status", "")),
            is_main_theme=bool(p.get("is_main_theme", False)),
            first_confirmed_date=p.get("first_confirmed_date"),
            last_review_date=p.get("last_review_date"),
            rule_version=str(p.get("rule_version", "")),
        )

    @staticmethod
    def _to_cycle(row: Any, default_trade_date: date) -> MainlineCycleDTO:
        if isinstance(row, MainlineCycleDTO):
            return row
        p = dict(row or {})
        trigger_flags = p.get("trigger_flags")
        return MainlineCycleDTO(
            trade_date=p.get("trade_date", default_trade_date),
            subject_key=str(p.get("subject_key", "")),
            final_cycle_state=str(p.get("final_cycle_state", "")),
            final_mainline_alive=bool(p.get("final_mainline_alive", False)),
            transition_type=str(p.get("transition_type", "")),
            transition_confidence=BuildPostMarketRecapJob._d(p.get("transition_confidence")),
            trigger_flags=list(trigger_flags) if isinstance(trigger_flags, list) else [],
            mainline_strength_score=BuildPostMarketRecapJob._d(p.get("mainline_strength_score")),
            repair_score=BuildPostMarketRecapJob._d(p.get("repair_score")),
            divergence_score=BuildPostMarketRecapJob._d(p.get("divergence_score")),
            fade_watch_score=BuildPostMarketRecapJob._d(p.get("fade_watch_score")),
            fade_confirmed_score=BuildPostMarketRecapJob._d(p.get("fade_confirmed_score")),
        )

    @staticmethod
    def _grade_from_watch_score(score: Decimal) -> str:
        if score >= Decimal("78"):
            return "S"
        if score >= Decimal("66"):
            return "A"
        if score >= Decimal("54"):
            return "B"
        return "REJECT"

    @staticmethod
    def _build_prior_active_strong_watch_records(prior_watch_rows: list[Any]) -> list[StrongWatchRecord]:
        grouped: dict[str, list[Any]] = {}
        for row in prior_watch_rows:
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id:
                continue
            grouped.setdefault(stock_id, []).append(row)

        records: list[StrongWatchRecord] = []
        for stock_id, rows in grouped.items():
            latest = rows[0]
            md = getattr(latest, "metadata", {}) or {}
            watch_status = str(md.get("watch_status") or "")
            pool_entry_type = str(md.get("pool_entry_type") or "")
            if not StrongWatchService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source=str(md.get("candidate_source") or "strong_watch_pool"),
            ):
                continue
            watch_score = BuildPostMarketRecapJob._d(md.get("watch_score"))
            support_score = BuildPostMarketRecapJob._d(md.get("support_score"))
            strong_grade = str(md.get("strong_grade") or "") or BuildPostMarketRecapJob._grade_from_watch_score(watch_score)
            role_tags = dict(md.get("role_tags") or {})
            for key in (
                "final_cycle_state",
                "transition_type",
                "transition_confidence",
                "trigger_flags",
            ):
                if key in md and key not in role_tags:
                    role_tags[key] = md[key]
            if "final_mainline_alive" not in role_tags:
                final_state = str(role_tags.get("final_cycle_state") or "")
                role_tags["final_mainline_alive"] = final_state not in {"fade_watch", "fade_confirmed", ""}
            watch_age_days = int(md.get("watch_age_days") or len({getattr(r, "trade_date", None) for r in rows if getattr(r, "trade_date", None)}) or 1)
            records.append(
                StrongWatchRecord(
                    stock_id=stock_id,
                    stock_name=str(getattr(latest, "stock_name", "") or ""),
                    subject_key=str(getattr(latest, "subject_key", "") or ""),
                    subject_name=str(getattr(latest, "subject_name", "") or ""),
                    pool_rank=getattr(latest, "pool_rank", None),
                    watch_score=watch_score,
                    strong_grade=strong_grade,
                    support_type=str(md.get("support_type") or ""),
                    support_level=BuildPostMarketRecapJob._d(md.get("support_level")),
                    support_score=support_score,
                    role_tags=role_tags,
                    watch_status=watch_status,
                    watch_age_days=watch_age_days,
                    weak_days=int(md.get("weak_days") or 0),
                    mainline_context_score=BuildPostMarketRecapJob._d(md.get("mainline_context_score")),
                    strong_gene_score=BuildPostMarketRecapJob._d(md.get("strong_gene_score")),
                    weakness_tolerance_score=BuildPostMarketRecapJob._d(md.get("weakness_tolerance_score")),
                    prior7_limitup_days=int(md.get("prior7_limitup_days") or 0),
                    prior7_strong_days=int(md.get("prior7_strong_days") or 0),
                    prior7_best_watch_score=BuildPostMarketRecapJob._d(md.get("prior7_best_watch_score")),
                    prior7_peak_rank=int(md.get("prior7_peak_rank") or 99),
                    admission_status=pool_entry_type if pool_entry_type in {"formal", "observe_only"} else "formal",
                )
            )
        return records

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 7,
    ) -> BuildResult:
        job_key = f"build_post_market_recap:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_post_market_recap",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
                warnings=["idempotency_key_already_completed"],
                metrics={"job_key": job_key},
            )

        pool_rows_raw = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        pool_rows = [self._to_pool_row(row, trade_date) for row in pool_rows_raw]
        prior_watch_rows = await self._get_prior_strong_watch_rows(trade_date=trade_date, lookback_days=lookback_days)
        stock_ids = sorted(
            {
                row.stock_id
                for row in [*pool_rows, *prior_watch_rows]
                if str(getattr(row, "stock_id", "") or "")
            }
        )
        subject_keys = sorted(
            {
                row.subject_key
                for row in [*pool_rows, *prior_watch_rows]
                if str(getattr(row, "subject_key", "") or "")
            }
        )
        prior_active_rows = self._build_prior_active_strong_watch_records(prior_watch_rows)

        bars_raw = await self._read_port.get_stock_daily_bars(trade_date)
        prior_rows_raw = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=stock_ids or None,
        )
        bars = [self._to_stock_bar(row, trade_date) for row in bars_raw]
        prior_rows = [self._to_prior_row(row, trade_date) for row in prior_rows_raw]
        history_start = trade_date - timedelta(days=90)
        history_bars_raw = await self._read_port.get_stock_daily_bars_range(
            start_date=history_start,
            end_date=trade_date,
            stock_ids=stock_ids or None,
        )
        history_bars = [self._to_stock_bar(row, history_start) for row in history_bars_raw]
        identities_raw = await self._read_port.get_mainline_identity_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
        cycles_raw = await self._read_port.get_mainline_cycle_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
        identities = [self._to_identity(row) for row in identities_raw]
        cycles = [self._to_cycle(row, trade_date) for row in cycles_raw]
        identities_by_subject = {x.subject_key: x for x in identities}
        cycles_by_subject = {x.subject_key: x for x in cycles}
        layer_a_identity_source = "theme_mainline_identity_registry"
        layer_b_cycle_source = "theme_cycle_judgement_v2"
        layer_a_identity_hit_count = len(identities_by_subject)
        layer_b_cycle_hit_count = len(cycles_by_subject)
        input_fingerprint = self._build_input_fingerprint(
            trade_date=trade_date,
            bars=bars,
            pool_rows=pool_rows,
            prior_rows=prior_rows,
            history_bars=history_bars,
            subject_keys=subject_keys,
            stock_ids=stock_ids,
        )

        layer_c_input_mode = str(os.getenv("SPS_LAYER_C_INPUT_MODE", "legacy_watch_pool")).strip().lower()
        layer_c_shadow_enabled = str(os.getenv("SPS_LAYER_C_SHADOW_ENABLED", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        run_new_layer_c = layer_c_input_mode != "legacy_watch_pool" or layer_c_shadow_enabled
        shadow_summary: dict[str, Any] = {}
        promoted_pool_rows: list[Any] = []
        strong_watch_rows: list[Any] = []
        strong_watch_history: list[Any] = []
        if run_new_layer_c:
            if hasattr(self._strong_watch_service, "build_promoted_pool_with_history_and_shadow"):
                promoted_pool_rows, strong_watch_rows, strong_watch_history, shadow = self._strong_watch_service.build_promoted_pool_with_history_and_shadow(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                    prior_active_rows=prior_active_rows,
                    identities_by_subject=identities_by_subject,
                    cycles_by_subject=cycles_by_subject,
                )
                shadow_summary = asdict(shadow)
            else:
                promoted_pool_rows, strong_watch_rows, strong_watch_history = self._strong_watch_service.build_promoted_pool_with_history(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                    prior_active_rows=prior_active_rows,
                    identities_by_subject=identities_by_subject,
                    cycles_by_subject=cycles_by_subject,
                )
        legacy_watch_input_count = 0
        if layer_c_input_mode == "legacy_watch_pool":
            fn = getattr(self._read_port, "get_legacy_strong_watch_candidate_inputs", None)
            if not callable(fn):
                raise RuntimeError("SPS_LAYER_C_INPUT_MODE=legacy_watch_pool requires get_legacy_strong_watch_candidate_inputs")
            candidate_input_rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
            legacy_watch_input_count = len(candidate_input_rows)
            promoted_pool_rows = list(candidate_input_rows)
            strong_watch_rows = []
            strong_watch_history = []
        else:
            candidate_input_rows = self._build_candidate_input_rows(
                trade_date=trade_date,
                strong_watch_rows=strong_watch_rows,
                promoted_pool_rows=promoted_pool_rows,
                prior_watch_rows=prior_watch_rows,
            )
        candidates = self._candidate_service.build_candidates(
            bars=bars,
            pool_rows=candidate_input_rows,
            prior_rows=prior_rows,
        )
        all_candidates = getattr(self._candidate_service, "all_candidates", candidates)
        formal_candidates = [
            c
            for c in all_candidates
            if str(getattr(c, "candidate_level", "")).lower() in {"formal", "s", "a", "b"}
        ]
        observe_candidates = [c for c in all_candidates if str(getattr(c, "candidate_level", "")).lower() == "observe_only"]
        candidate_service_observe_candidates = getattr(self._candidate_service, "observe_candidates", observe_candidates)

        recap_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "identity_gate_mode": str(os.getenv("SPS_IDENTITY_GATE_MODE", "asof")).strip().lower(),
            "candidate_source": "strong_watch_pool",
            "layer_c_input_mode": layer_c_input_mode,
            "layer_c_shadow_enabled": layer_c_shadow_enabled,
            "legacy_watch_input_count": legacy_watch_input_count,
            "strong_watch_input_count": len(strong_watch_rows),
            "strong_watch_input_7d_count": len(candidate_input_rows),
            "strong_watch_promoted_count": len(promoted_pool_rows),
            "strong_watch_history_count": len(strong_watch_history),
            "strong_watch_shadow_summary": shadow_summary,
            "shadow_layer_c_formal_count": int(shadow_summary.get("admission_formal_count") or 0),
            "shadow_layer_c_observe_count": int(shadow_summary.get("admission_observe_count") or 0),
            "shadow_layer_c_reject_count": int(shadow_summary.get("admission_reject_count") or 0),
            "shadow_layer_c_pass_4of3_fail_count": int(shadow_summary.get("admission_pass_4of3_fail_count") or 0),
            "shadow_layer_c_hard_reject_count": int(shadow_summary.get("admission_hard_reject_count") or 0),
            "layer_a_identity_source": layer_a_identity_source,
            "layer_b_cycle_source": layer_b_cycle_source,
            "layer_a_identity_hit_count": layer_a_identity_hit_count,
            "layer_b_cycle_hit_count": layer_b_cycle_hit_count,
            "layer_ab_subject_key_count": len(subject_keys),
            "input_fingerprint": input_fingerprint,
            "strong_watch_history": [
                {
                    "stock_id": row.stock_id,
                    "subject_key": row.subject_key,
                    "watch_status": row.watch_status,
                    "strong_grade": row.strong_grade,
                    "watch_score": str(row.watch_score),
                    "support_score": str(row.support_score),
                    "support_type": row.support_type,
                    "final_cycle_state": str((getattr(row, "role_tags", {}) or {}).get("final_cycle_state", "")),
                    "transition_type": str((getattr(row, "role_tags", {}) or {}).get("transition_type", "")),
                    "transition_confidence": str((getattr(row, "role_tags", {}) or {}).get("transition_confidence", "0")),
                    "trigger_flags": list((getattr(row, "role_tags", {}) or {}).get("trigger_flags", []) or []),
                    "prune_mode": row.prune_mode,
                    "prune_reason_code": row.prune_reason_code,
                    "removed_reason": row.removed_reason,
                    "kept_because": row.kept_because,
                }
                for row in strong_watch_history[:100]
            ],
            # Primary count follows the actual candidate list, with formal/observe split preserved separately.
            "candidate_count": len(candidates),
            "candidate_count_total": len(candidates),
            "candidate_count_all": len(all_candidates),
            "candidate_count_formal": len(formal_candidates),
            "candidate_count_observe": len(observe_candidates),
            "observe_candidates_count": len(candidate_service_observe_candidates),
            "top_candidates_scope": "formal_plus_observe_ranked",
            "formal_top_candidates": [
                {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "subject_key": c.subject_key,
                    "candidate_score": str(c.candidate_score),
                    "support_type": c.support_type,
                }
                for c in formal_candidates[:15]
            ],
            "observe_candidates": [
                {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "subject_key": c.subject_key,
                    "subject_name": c.subject_name,
                    "candidate_score": str(c.candidate_score),
                    "candidate_level": c.candidate_level,
                    "support_type": c.support_type,
                    "support_score": str(c.support_score),
                    "gap_hit": c.gap_hit,
                    "gap_hit_mode": c.gap_hit_mode,
                    "evidence_rules": c.evidence_rules[:30],
                }
                for c in candidate_service_observe_candidates[:20]
            ],
            "candidate_diagnostics": [
                {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "subject_key": c.subject_key,
                    "subject_name": c.subject_name,
                    "candidate_score": str(c.candidate_score),
                    "candidate_level": c.candidate_level,
                    "support_type": c.support_type,
                    "support_score": str(c.support_score),
                    "weakness_valid_score": str(c.weakness_valid_score),
                    "repair_or_takeover_score": str(c.repair_or_takeover_score),
                    "gap_hit": c.gap_hit,
                    "gap_hit_mode": c.gap_hit_mode,
                    "candidate_rank": idx,
                }
                for idx, c in enumerate(all_candidates, start=1)
            ],
            "strong_watch_input_7d_preview": [
                {
                    "stock_id": r.stock_id,
                    "stock_name": r.stock_name,
                    "subject_key": r.subject_key,
                    "subject_name": r.subject_name,
                    "candidate_source": str((r.metadata or {}).get("candidate_source", "")),
                    "watch_score": str((r.metadata or {}).get("watch_score", "")),
                    "strong_grade": str((r.metadata or {}).get("strong_grade", "")),
                    "support_type": str((r.metadata or {}).get("support_type", "")),
                    "seed_gate_pass": bool((r.metadata or {}).get("seed_gate_pass") or False),
                    "seed_gate_reason": str((r.metadata or {}).get("seed_gate_reason", "")),
                    "strong_gene_seed": bool((r.metadata or {}).get("strong_gene_seed") or False),
                    "strong_gene_seed_reason": str((r.metadata or {}).get("strong_gene_seed_reason", "")),
                    "two_board_entry": bool((r.metadata or {}).get("two_board_entry") or False),
                    "final_cycle_state": str((r.metadata or {}).get("final_cycle_state", "")),
                    "transition_type": str((r.metadata or {}).get("transition_type", "")),
                    "transition_confidence": str((r.metadata or {}).get("transition_confidence", "0")),
                }
                for r in candidate_input_rows[:100]
            ],
            "strong_watch_input_7d_stock_ids": sorted(
                {str(r.stock_id) for r in candidate_input_rows if str(getattr(r, "stock_id", "") or "")}
            ),
            "strong_watch_input_7d_source": (
                "legacy_strong_watch_pool_or_history"
                if layer_c_input_mode == "legacy_watch_pool"
                else "strong_watch_pool_history_single_source"
            ),
            "promoted_pool_stock_ids": sorted(
                {str(getattr(r, "stock_id", "") or "") for r in promoted_pool_rows if str(getattr(r, "stock_id", "") or "")}
            ),
            "promoted_pool_preview": [
                {
                    "stock_id": r.stock_id,
                    "stock_name": r.stock_name,
                    "subject_key": r.subject_key,
                    "subject_name": r.subject_name,
                    "pool_rank": r.pool_rank,
                    "watch_status": str((getattr(r, "metadata", {}) or {}).get("watch_status", "")),
                    "strong_grade": str((getattr(r, "metadata", {}) or {}).get("strong_grade", "")),
                    "watch_score": str((getattr(r, "metadata", {}) or {}).get("watch_score", "")),
                    "support_score": str((getattr(r, "metadata", {}) or {}).get("support_score", "")),
                    "support_type": str((getattr(r, "metadata", {}) or {}).get("support_type", "")),
                    "gap_hit": bool((getattr(r, "metadata", {}) or {}).get("gap_hit") or False),
                    "seed_gate_pass": bool((getattr(r, "metadata", {}) or {}).get("seed_gate_pass") or False),
                    "seed_gate_reason": str((getattr(r, "metadata", {}) or {}).get("seed_gate_reason", "")),
                    "strong_gene_seed": bool((getattr(r, "metadata", {}) or {}).get("strong_gene_seed") or False),
                    "strong_gene_seed_reason": str((getattr(r, "metadata", {}) or {}).get("strong_gene_seed_reason", "")),
                    "two_board_entry": bool((getattr(r, "metadata", {}) or {}).get("two_board_entry") or False),
                    "admission_status": str((getattr(r, "metadata", {}) or {}).get("admission_status", "")),
                    "promote_bucket": str((getattr(r, "metadata", {}) or {}).get("promote_bucket", "")),
                    "promote_reason": str((getattr(r, "metadata", {}) or {}).get("promote_reason", "")),
                    "prior7_limitup_days": int((getattr(r, "metadata", {}) or {}).get("prior7_limitup_days") or 0),
                    "recent_limit_up_count": int(((getattr(r, "metadata", {}) or {}).get("role_tags", {}) or {}).get("recent_limit_up_count") or 0),
                    "final_cycle_state": str(((getattr(r, "metadata", {}) or {}).get("role_tags", {}) or {}).get("final_cycle_state", "")),
                }
                for r in promoted_pool_rows[:200]
            ],
            "top_candidates": [
                {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "subject_key": c.subject_key,
                    "subject_name": c.subject_name,
                    "candidate_score": str(c.candidate_score),
                    "candidate_level": c.candidate_level,
                    "transition_type": str(getattr(c, "transition_type", "") or ""),
                    "transition_confidence": str(getattr(c, "transition_confidence", "0")),
                    "trigger_flags": list(getattr(c, "trigger_flags", []) or []),
                    "evidence_rules": c.evidence_rules,
                }
                for c in candidates[:30]
            ],
        }

        snapshot = PostMarketRecapSnapshot(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            source_trace_id=trace_id,
            recap_doc=recap_doc,
        )

        affected = await self._write_port.upsert_post_market_recap_snapshot(snapshot)
        history_written = await self._upsert_strong_watch_history(strong_watch_history)

        if self._cache_port is not None:
            await self._cache_writer.write_value_cache(
                f"sps:post_market_recap:{trade_date}",
                asdict(snapshot),
                ttl_seconds=SnapshotCacheWriter.TTL_24H,
            )
            await self._cache_writer.write_grouped_cache(
                f"sps:strong_watch_history:{trade_date}",
                [
                    {
                        "stock_id": row.stock_id,
                        "subject_key": row.subject_key,
                        "watch_status": row.watch_status,
                        "strong_grade": row.strong_grade,
                        "watch_score": str(row.watch_score),
                        "support_score": str(row.support_score),
                        "support_type": row.support_type,
                        "prune_mode": row.prune_mode,
                        "prune_reason_code": row.prune_reason_code,
                        "removed_reason": row.removed_reason,
                        "kept_because": row.kept_because,
                    }
                    for row in strong_watch_history
                ],
                ttl_seconds=SnapshotCacheWriter.TTL_24H,
            )
            await self._cache_writer.write_current_version(
                "sps:post_market_recap",
                trade_date,
                snapshot_version,
            )

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
                    domain="post_market",
                    snapshot_version=snapshot_version,
                    object_name="post_market_recap_snapshot",
                    row_count=1,
                    success=True,
                ),
            )
        )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "candidate_count": len(candidates),
                "strong_watch_history_rows": history_written,
            },
        )

        return BuildResult(
            name="build_post_market_recap",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "strong_watch_input_count": len(strong_watch_rows),
                "strong_watch_promoted_count": len(promoted_pool_rows),
                "strong_watch_history_count": len(strong_watch_history),
                "strong_watch_history_written": history_written,
                "strong_watch_shadow_universe_formal_count": int(shadow_summary.get("universe_formal_count") or 0),
                "strong_watch_shadow_universe_observe_count": int(shadow_summary.get("universe_observe_count") or 0),
                "strong_watch_shadow_universe_blocked_count": int(shadow_summary.get("universe_blocked_count") or 0),
                "strong_watch_shadow_admission_formal_count": int(shadow_summary.get("admission_formal_count") or 0),
                "strong_watch_shadow_admission_observe_count": int(shadow_summary.get("admission_observe_count") or 0),
                "strong_watch_shadow_admission_reject_count": int(shadow_summary.get("admission_reject_count") or 0),
                "strong_watch_shadow_admission_pass_4of3_fail_count": int(
                    shadow_summary.get("admission_pass_4of3_fail_count") or 0
                ),
                "strong_watch_shadow_admission_hard_reject_count": int(
                    shadow_summary.get("admission_hard_reject_count") or 0
                ),
                "layer_c_input_mode": layer_c_input_mode,
                "legacy_watch_input_count": legacy_watch_input_count,
                "candidate_count": len(candidates),
                "candidate_count_formal": len(formal_candidates),
                "candidate_count_observe": len(observe_candidates),
                "observe_candidates_count": len(candidate_service_observe_candidates),
            },
            published_events=["snapshot_built"],
            cache_writes=3 if self._cache_port is not None else 0,
        )

    @staticmethod
    def _build_input_fingerprint(
        *,
        trade_date: date,
        bars: list[Any],
        pool_rows: list[Any],
        prior_rows: list[Any],
        history_bars: list[Any],
        subject_keys: list[str],
        stock_ids: list[str],
    ) -> dict[str, Any]:
        payload = {
            "trade_date": trade_date.isoformat(),
            "bars_count": len(bars),
            "pool_rows_count": len(pool_rows),
            "prior_rows_count": len(prior_rows),
            "history_bars_count": len(history_bars),
            "subject_key_count": len(subject_keys),
            "stock_id_count": len(stock_ids),
            "subject_keys_sample": subject_keys[:50],
            "stock_ids_sample": stock_ids[:100],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["fingerprint_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return payload

    async def _upsert_strong_watch_history(self, strong_watch_history: list[Any]) -> int:
        fn = getattr(self._write_port, "upsert_strong_watch_history_rows", None)
        if not callable(fn):
            return 0
        rows = [
            {
                "trade_date": row.trade_date.isoformat() if hasattr(row.trade_date, "isoformat") else row.trade_date,
                "stock_id": row.stock_id,
                "stock_name": row.stock_name,
                "subject_key": row.subject_key,
                "theme_name": row.theme_name,
                "watch_status": row.watch_status,
                "pool_entry_type": row.pool_entry_type,
                "relay_role": row.relay_role,
                "strong_grade": row.strong_grade,
                "watch_score": str(row.watch_score),
                "watch_priority": str(row.watch_priority),
                "cycle_state": row.cycle_state,
                "mainline_strength_score": str(row.mainline_strength_score),
                "fade_watch": bool(row.fade_watch),
                "fade_confirmed": bool(row.fade_confirmed),
                "promoted_to_candidate": bool(row.promoted_to_candidate),
                "support_score": str(row.support_score),
                "support_type": row.support_type,
                "support_level": str(row.support_level),
                "prune_mode": row.prune_mode,
                "prune_reason_code": row.prune_reason_code,
                "removed_reason": row.removed_reason,
                "kept_because": row.kept_because,
                "labels_json": dict(row.labels_json or {}),
                "evidence_json": dict(row.evidence_json or {}),
            }
            for row in strong_watch_history
        ]
        return int(await fn(rows) or 0)

    @staticmethod
    def _build_candidate_input_rows(
        *,
        trade_date: date,
        strong_watch_rows: list[Any],
        promoted_pool_rows: list[Any],
        prior_watch_rows: list[Any],
    ) -> list[Any]:
        from stock_processing_service.contracts.dto import SubjectStockPoolDTO

        by_stock: dict[str, SubjectStockPoolDTO] = {}

        def _is_valid_prior_watch_row(row: Any) -> bool:
            md = getattr(row, "metadata", {}) or {}
            source = str(md.get("candidate_source") or "")
            watch_status = str(md.get("watch_status") or "")
            pool_entry_type = str(md.get("pool_entry_type") or "")
            eligible_for_candidate = md.get("eligible_for_candidate")
            subject_key = str(getattr(row, "subject_key", "") or "")
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id or not subject_key:
                return False
            if eligible_for_candidate is not None:
                return bool(eligible_for_candidate)
            return StrongWatchService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source=source,
            )

        for row in strong_watch_rows:
            watch_status = str(getattr(row, "watch_status", ""))
            pool_entry_type = str(getattr(row, "admission_status", "") or getattr(row, "pool_entry_type", ""))
            if not StrongWatchService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source="strong_watch_pool",
            ):
                continue
            stock_id = str(getattr(row, "stock_id", "") or "")
            subject_key = str(getattr(row, "subject_key", "") or "")
            if not stock_id:
                continue
            if not subject_key:
                continue
            watch_score = BuildPostMarketRecapJob._d(getattr(row, "watch_score", "0"))
            strong_grade = str(getattr(row, "strong_grade", "") or BuildPostMarketRecapJob._grade_from_watch_score(watch_score))
            by_stock[stock_id] = SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key=subject_key,
                subject_name=getattr(row, "subject_name", ""),
                stock_id=stock_id,
                stock_name=getattr(row, "stock_name", ""),
                pool_rank=getattr(row, "pool_rank", None),
                metadata={
                    # D1 入参统一标记为 strong_watch_pool，避免被 source=seed_proxy 等过滤掉。
                    "candidate_source": "strong_watch_pool",
                    "watch_score": str(watch_score),
                    "strong_grade": strong_grade,
                    "support_type": getattr(row, "support_type", ""),
                    "support_level": str(getattr(row, "support_level", "0")),
                    "support_score": str(getattr(row, "support_score", "0")),
                    "support_refs": list(getattr(row, "support_refs", []) or []),
                    "support_count": int(getattr(row, "support_count", 0) or 0),
                    "support_combined_strength": str(getattr(row, "support_combined_strength", "0")),
                    "gap_hit": bool(getattr(row, "gap_hit", False)),
                    "gap_hit_mode": getattr(row, "gap_hit_mode", "miss"),
                    "gap_source": getattr(row, "gap_source", ""),
                    "gap_level": str(getattr(row, "gap_level", "0")),
                    "gap_distance_pct": str(getattr(row, "gap_distance_pct", "999")),
                    "role_tags": dict(getattr(row, "role_tags", {}) or {}),
                    "mainline_context_score": str(getattr(row, "mainline_context_score", "0")),
                    "strong_gene_score": str(getattr(row, "strong_gene_score", "0")),
                    "weakness_tolerance_score": str(getattr(row, "weakness_tolerance_score", "0")),
                    "prior7_limitup_days": int(getattr(row, "prior7_limitup_days", 0) or 0),
                    "prior7_strong_days": int(getattr(row, "prior7_strong_days", 0) or 0),
                    "prior7_best_watch_score": str(getattr(row, "prior7_best_watch_score", "0")),
                    "prior7_peak_rank": int(getattr(row, "prior7_peak_rank", 99) or 99),
                    "watch_status": getattr(row, "watch_status", ""),
                    "pool_entry_type": pool_entry_type,
                    "eligible_for_candidate": True,
                    "final_cycle_state": str((getattr(row, "role_tags", {}) or {}).get("final_cycle_state", "")),
                    "transition_type": str((getattr(row, "role_tags", {}) or {}).get("transition_type", "")),
                    "transition_confidence": str((getattr(row, "role_tags", {}) or {}).get("transition_confidence", "0")),
                    "trigger_flags": list((getattr(row, "role_tags", {}) or {}).get("trigger_flags", []) or []),
                    "kept_because": getattr(row, "kept_because", ""),
                },
            )
        for row in promoted_pool_rows:
            stock_id = str(getattr(row, "stock_id", "") or "")
            subject_key = str(getattr(row, "subject_key", "") or "")
            if not stock_id or not subject_key or stock_id in by_stock:
                continue
            md = dict(getattr(row, "metadata", {}) or {})
            strong_grade = str(md.get("strong_grade") or "")
            if not strong_grade:
                watch_score = BuildPostMarketRecapJob._d(md.get("watch_score"))
                strong_grade = BuildPostMarketRecapJob._grade_from_watch_score(watch_score)
                md["strong_grade"] = strong_grade
            md.setdefault("candidate_source", "strong_watch_pool")
            md.setdefault("watch_status", "active")
            md.setdefault("pool_entry_type", "formal")
            md.setdefault("eligible_for_candidate", True)
            by_stock[stock_id] = SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key=subject_key,
                subject_name=str(getattr(row, "subject_name", "") or ""),
                stock_id=stock_id,
                stock_name=getattr(row, "stock_name", ""),
                pool_rank=getattr(row, "pool_rank", None),
                metadata=md,
            )
        # 再装入近7日历史跟踪池，仅补充当日 refresh/promote 未覆盖的对象。
        for row in prior_watch_rows:
            if not _is_valid_prior_watch_row(row):
                continue
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id or stock_id in by_stock:
                continue
            by_stock[stock_id] = row
        rows: list[SubjectStockPoolDTO] = []
        rows.extend(by_stock.values())
        return rows

    async def _get_prior_strong_watch_rows(self, *, trade_date: date, lookback_days: int) -> list[Any]:
        fn = getattr(self._read_port, "get_prior_strong_watch_pool_rows", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
        filtered: list[Any] = []
        for row in list(rows or []):
            row_date = getattr(row, "trade_date", None)
            if row_date is None and isinstance(row, dict):
                row_date = row.get("trade_date")
            # Time-travel guard: candidate window must only consume strictly prior rows.
            if row_date is not None and row_date >= trade_date:
                continue
            filtered.append(row)
        return filtered
