from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PostMarketRecapSnapshot
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

        bars = await self._read_port.get_stock_daily_bars(trade_date)
        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        prior_rows = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=[row.stock_id for row in pool_rows] if pool_rows else None,
        )
        history_start = trade_date - timedelta(days=90)
        history_bars = await self._read_port.get_stock_daily_bars_range(
            start_date=history_start,
            end_date=trade_date,
            stock_ids=[row.stock_id for row in pool_rows] if pool_rows else None,
        )
        subject_keys = sorted({row.subject_key for row in pool_rows if row.subject_key})
        stock_ids = sorted({row.stock_id for row in pool_rows if row.stock_id})
        identities = await self._read_port.get_mainline_identity_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
        cycles = await self._read_port.get_mainline_cycle_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
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

        shadow_summary: dict[str, Any] = {}
        if hasattr(self._strong_watch_service, "build_promoted_pool_with_history_and_shadow"):
            try:
                promoted_pool_rows, strong_watch_rows, strong_watch_history, shadow = self._strong_watch_service.build_promoted_pool_with_history_and_shadow(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                    identities_by_subject=identities_by_subject,
                    cycles_by_subject=cycles_by_subject,
                )
            except TypeError:
                promoted_pool_rows, strong_watch_rows, strong_watch_history, shadow = self._strong_watch_service.build_promoted_pool_with_history_and_shadow(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                )
            shadow_summary = asdict(shadow)
        else:
            try:
                promoted_pool_rows, strong_watch_rows, strong_watch_history = self._strong_watch_service.build_promoted_pool_with_history(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                    identities_by_subject=identities_by_subject,
                    cycles_by_subject=cycles_by_subject,
                )
            except TypeError:
                promoted_pool_rows, strong_watch_rows, strong_watch_history = self._strong_watch_service.build_promoted_pool_with_history(
                    trade_date=trade_date,
                    pool_rows=pool_rows,
                    bars=bars,
                    prior_rows=prior_rows,
                    history_bars=history_bars,
                )
        prior_watch_rows = await self._get_prior_strong_watch_rows(trade_date=trade_date, lookback_days=lookback_days)
        candidate_input_rows = self._build_candidate_input_rows(
            trade_date=trade_date,
            strong_watch_rows=strong_watch_rows,
            prior_watch_rows=prior_watch_rows,
        )
        candidates = self._candidate_service.build_candidates(
            bars=bars,
            pool_rows=candidate_input_rows,
            prior_rows=prior_rows,
        )

        recap_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "identity_gate_mode": str(os.getenv("SPS_IDENTITY_GATE_MODE", "asof")).strip().lower(),
            "candidate_source": "strong_watch_pool",
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
            "candidate_count": len(candidates),
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
                    "final_cycle_state": str((r.metadata or {}).get("final_cycle_state", "")),
                    "transition_type": str((r.metadata or {}).get("transition_type", "")),
                    "transition_confidence": str((r.metadata or {}).get("transition_confidence", "0")),
                }
                for r in candidate_input_rows[:100]
            ],
            "strong_watch_input_7d_stock_ids": sorted(
                {str(r.stock_id) for r in candidate_input_rows if str(getattr(r, "stock_id", "") or "")}
            ),
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
                "candidate_count": len(candidates),
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

        # 先装入近7日历史跟踪池，确保 D1 输入遵循“跟踪池窗口”口径。
        for row in prior_watch_rows:
            if not _is_valid_prior_watch_row(row):
                continue
            stock_id = str(getattr(row, "stock_id", "") or "")
            if not stock_id:
                continue
            # prior_watch_rows 由近到远返回；去重时保留“最近交易日”版本，避免被旧日 removed 状态覆盖。
            if stock_id in by_stock:
                continue
            by_stock[stock_id] = row

        rows: list[SubjectStockPoolDTO] = []
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
                    "watch_score": str(getattr(row, "watch_score", "0")),
                    "strong_grade": getattr(row, "strong_grade", ""),
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
        rows.extend(by_stock.values())
        return rows

    async def _get_prior_strong_watch_rows(self, *, trade_date: date, lookback_days: int) -> list[Any]:
        fn = getattr(self._read_port, "get_prior_strong_watch_pool_rows", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
        return list(rows or [])
