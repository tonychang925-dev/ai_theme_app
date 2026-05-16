from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from typing import Any
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
    LAYER_C_INPUT_MODE,
    BuildStrongStockTrackingUseCase,
)
from stock_processing_service.application.use_cases.build_weak_to_strong_candidate import (
    BuildWeakToStrongCandidateUseCase,
)
from stock_processing_service.contracts.dto import (
    BuildResult,
    SubjectStockPoolDTO,
)
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PostMarketRecapSnapshot
from stock_processing_service.domain.services.strong_stock_tracking_service import (
    StrongStockTrackingService,
)
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    StockWritePort,
)


class BuildPostMarketRecapJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: StockWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        candidate_service: W2SCandidateService | None = None,
        tracking_service: StrongStockTrackingService | None = None,
        strong_stock_tracking_use_case: Any | None = None,
        weak_to_strong_candidate_use_case: Any | None = None,
        identity_job: Any | None = None,  # BuildIdentityJob — Layer A 前置
        mainline_state_job: Any | None = None,  # BuildMainlineStateJob — Layer B 前置
        cycle_judgement_job: Any | None = None,  # BuildCycleJudgementJob — Layer B 前置
        evidence_job: Any | None = None,  # BuildThemeCycleEvidenceDailyJob — Layer B 证据
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._cache_writer = SnapshotCacheWriter(cache_port)
        self._candidate_service = candidate_service or W2SCandidateService()
        self._tracking_service = tracking_service or StrongStockTrackingService()
        self._strong_stock_tracking_use_case = strong_stock_tracking_use_case or BuildStrongStockTrackingUseCase(
            read_ports=read_port,
            write_ports=write_port,
            cache_ports=cache_port,
            tracking_service=self._tracking_service,
        )
        self._weak_to_strong_candidate_use_case = weak_to_strong_candidate_use_case or BuildWeakToStrongCandidateUseCase(
            read_ports=read_port,
            write_ports=write_port,
        )
        self._identity_job = identity_job
        self._mainline_state_job = mainline_state_job
        self._cycle_judgement_job = cycle_judgement_job
        self._evidence_job = evidence_job

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
            if not StrongStockTrackingService.is_candidate_eligible(
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
        lookback_days: int = 8,
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

        # ── Layer A/B 前置（新链自闭环）──
        # 执行顺序: Evidence → Cycle → Identity → MainlineState
        if self._evidence_job is not None:
            await self._evidence_job.execute(
                trade_date=trade_date,
                snapshot_version=f"recap_evidence.{snapshot_version}",
                batch_id=batch_id,
                trace_id=trace_id,
            )
        if self._cycle_judgement_job is not None:
            await self._cycle_judgement_job.execute(
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
            )
        if self._identity_job is not None:
            await self._identity_job.execute(
                trade_date=trade_date,
                snapshot_version="recap_identity.v1",
                batch_id=batch_id,
                trace_id=trace_id,
            )
        if self._mainline_state_job is not None:
            await self._mainline_state_job.execute(
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # ── Layer C: 强势股观察池由独立 use case 负责，recap 只消费其对象输出 ──
        layer_c_result = await self._strong_stock_tracking_use_case.execute(
            trade_date=trade_date,
            window_days=7,
            lookback_days=lookback_days,
        )
        layer_c_metrics = dict(layer_c_result.metrics or {})

        # ── Layer D1: 弱转强候选由独立 use case 负责，recap 只消费其结果 ──
        d1_result = await self._weak_to_strong_candidate_use_case.execute(trade_date=trade_date)
        d1_metrics = dict(d1_result.metrics or {})
        d1_input_rows = list(d1_metrics.get("d1_input_rows") or [])
        d1_candidates_for_pool = list(d1_metrics.get("d1_candidates_for_pool") or [])
        _d1_total_in = int(d1_metrics.get("d1_total_in") or 0)
        _d1_pass = int(d1_metrics.get("d1_pass") or 0)
        _d1_fail_pct = int(d1_metrics.get("d1_fail_pct_gate") or 0)
        _d1_fail_history = int(d1_metrics.get("d1_fail_history") or 0)
        _d1_fail_gene = int(d1_metrics.get("d1_fail_gene") or 0)
        _d1_fail_strong = int(d1_metrics.get("d1_fail_strong") or 0)
        _d1_fail_support = int(d1_metrics.get("d1_fail_support") or 0)
        d1_written = int(d1_metrics.get("d1_written") or 0)

        # 构建 recap_doc 所需元数据
        pool_rows: list[Any] = []  # 保留兼容性
        stock_ids = list(layer_c_metrics.get("stock_ids") or [])
        subject_keys = list(layer_c_metrics.get("subject_keys") or [])
        strong_watch_rows: list[Any] = []
        history_written = int(layer_c_metrics.get("history_written") or 0)
        strong_watch_history: list[Any] = list(layer_c_metrics.get("history_rows") or [])
        promoted_pool_rows: list[Any] = d1_input_rows
        shadow_summary: dict[str, Any] = {}
        legacy_watch_input_count = 0
        strong_watch_pool_written = int(layer_c_metrics.get("pool_written") or 0)
        strong_watch_promote_count = int(layer_c_metrics.get("promote_count") or 0)
        strong_watch_prune_count = int(layer_c_metrics.get("prune_count") or 0)
        strong_watch_history_written = history_written
        layer_c_input_mode = LAYER_C_INPUT_MODE
        layer_c_shadow_enabled = False
        layer_a_identity_source = "theme_mainline_identity_registry"
        layer_b_cycle_source = "theme_cycle_judgement_v2"
        layer_a_identity_hit_count = int(layer_c_metrics.get("subject_key_count") or 0)
        layer_b_cycle_hit_count = int(layer_c_metrics.get("subject_key_count") or 0)
        input_fingerprint = LAYER_C_INPUT_MODE
        # 构建兼容 recap_doc 的 candidates 列表
        candidates = [
            {
                "stock_id": c["stock_id"],
                "stock_name": c["stock_name"],
                "subject_key": c["subject_key"],
                "subject_name": c["theme_name"],
                "candidate_score": c["candidate_score"],
                "candidate_level": c["pool_entry_type"],
                "candidate_type": c["candidate_type"],
                "transition_type": c["weak_type"],
                "transition_confidence": "50",
                "trigger_flags": [],
                "evidence_rules": [],
                "support_type": c["support_type"],
            }
            for c in d1_candidates_for_pool
        ]
        formal_candidates = [c for c in candidates if str(c.get("candidate_level", "")).lower() in {"formal", "s", "a", "b"}]
        observe_candidates = [c for c in candidates if str(c.get("candidate_level", "")).lower() == "observe_only"]
        candidate_service_observe_candidates = observe_candidates

        recap_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "identity_gate_mode": str(os.getenv("SPS_IDENTITY_GATE_MODE", "asof")).strip().lower(),
            "candidate_source": "strong_watch_pool",
            "layer_c_input_mode": layer_c_input_mode,
            "layer_c_shadow_enabled": layer_c_shadow_enabled,
            "legacy_watch_input_count": legacy_watch_input_count,
            "strong_watch_input_count": len(d1_input_rows),
            "strong_watch_input_7d_count": len(d1_input_rows),
            "d1_total_in": _d1_total_in,
            "d1_pass": _d1_pass,
            "d1_fail_pct_gate": _d1_fail_pct,
            "d1_fail_history": _d1_fail_history,
            "d1_fail_gene": _d1_fail_gene,
            "d1_fail_strong": _d1_fail_strong,
            "d1_fail_support": _d1_fail_support,
            "strong_watch_promoted_count": len(promoted_pool_rows),
            "strong_watch_history_count": len(strong_watch_history),
            "strong_watch_pool_written": strong_watch_pool_written,
            "strong_watch_promote_count": strong_watch_promote_count,
            "strong_watch_prune_count": strong_watch_prune_count,
            "strong_watch_history_written": strong_watch_history_written,
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
                    "stock_id": (row.get("stock_id") if isinstance(row, dict) else getattr(row, "stock_id", "")),
                    "subject_key": (row.get("subject_key") if isinstance(row, dict) else getattr(row, "subject_key", "")),
                    "watch_status": (row.get("watch_status") if isinstance(row, dict) else getattr(row, "watch_status", "")),
                    "strong_grade": str(row.get("strong_grade", "") if isinstance(row, dict) else getattr(row, "strong_grade", "")),
                    "watch_score": str(row.get("watch_score", 0) if isinstance(row, dict) else getattr(row, "watch_score", 0)),
                    "support_score": str(row.get("support_score", "0") if isinstance(row, dict) else getattr(row, "support_score", "0")),
                    "support_type": (row.get("support_type") if isinstance(row, dict) else getattr(row, "support_type", "")),
                    "final_cycle_state": "",
                    "transition_type": "",
                    "transition_confidence": "0",
                    "trigger_flags": [],
                    "prune_mode": None,
                    "prune_reason_code": None,
                    "removed_reason": (row.get("removed_reason") if isinstance(row, dict) else getattr(row, "removed_reason", None)),
                    "kept_because": None,
                }
                for row in strong_watch_history[:100]
            ],
            # Primary count follows the actual candidate list, with formal/observe split preserved separately.
            "candidate_count": len(candidates),
            "candidate_count_total": len(candidates),
            "candidate_count_all": len(candidates),
            "candidate_count_formal": len(formal_candidates),
            "candidate_count_observe": len(observe_candidates),
            "observe_candidates_count": len(candidate_service_observe_candidates),
            "top_candidates_scope": "formal_plus_observe_ranked",
            "formal_top_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "candidate_score": str(c["candidate_score"]),
                    "support_type": c.get("support_type", ""),
                }
                for c in formal_candidates[:15]
            ],
            "observe_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "support_type": c.get("support_type", ""),
                    "support_score": str(c.get("support_score", "0")),
                    "gap_hit": c.get("gap_hit", False),
                    "gap_hit_mode": c.get("gap_hit_mode", "miss"),
                    "evidence_rules": c.get("evidence_rules", [])[:30],
                }
                for c in candidate_service_observe_candidates[:20]
            ],
            "candidate_diagnostics": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "support_type": c.get("support_type", ""),
                    "support_score": str(c.get("support_score", "0")),
                    "weakness_valid_score": str(c.get("weakness_valid_score", "0")),
                    "repair_or_takeover_score": str(c.get("repair_or_takeover_score", "0")),
                    "gap_hit": c.get("gap_hit", False),
                    "gap_hit_mode": c.get("gap_hit_mode", "miss"),
                    "candidate_rank": idx,
                }
                for idx, c in enumerate(candidates, start=1)
            ],
            "strong_watch_input_7d_preview": [
                {
                    "stock_id": str(r.get("stock_id", "")),
                    "stock_name": str(r.get("stock_name", "")),
                    "subject_key": str(r.get("subject_key", "")),
                    "subject_name": str(r.get("theme_name", "")),
                    "watch_score": str(r.get("watch_score", "")),
                    "watch_status": str(r.get("watch_status", "")),
                    "pool_entry_type": str(r.get("watch_pool_entry_type", "")),
                    "support_type": "",
                }
                for r in d1_input_rows[:100]
            ],
            "strong_watch_input_7d_stock_ids": sorted(
                {str(r.get("stock_id", "")) for r in d1_input_rows if str(r.get("stock_id", "") or "")}
            ),
            "strong_watch_input_7d_source": (
                "legacy_strong_watch_pool_or_history"
                if layer_c_input_mode == "legacy_watch_pool"
                else "strong_watch_pool_history_single_source"
            ),
            "promoted_pool_stock_ids": sorted(
                {str(r.get("stock_id", "")) for r in promoted_pool_rows if str(r.get("stock_id", "") or "")}
            ),
            "promoted_pool_preview": [
                {
                    "stock_id": str(r.get("stock_id", "")),
                    "stock_name": str(r.get("stock_name", "")),
                    "subject_key": str(r.get("subject_key", "")),
                    "subject_name": str(r.get("theme_name", "")),
                    "pool_rank": None,
                    "watch_status": str(r.get("watch_status", "")),
                    "watch_score": str(r.get("watch_score", "")),
                    "support_type": "",
                    "prior7_limitup_days": int(r.get("prior7_limitup_days") or 0),
                    "recent_limit_up_count": int(r.get("recent_limit_up_count") or 0),
                    "final_cycle_state": str(r.get("final_cycle_state") or ""),
                }
                for r in promoted_pool_rows[:200]
            ],
            "top_candidates": [
                {
                    "stock_id": c["stock_id"],
                    "stock_name": c["stock_name"],
                    "subject_key": c["subject_key"],
                    "subject_name": c["subject_name"],
                    "candidate_score": str(c["candidate_score"]),
                    "candidate_level": c["candidate_level"],
                    "transition_type": str(getattr(c, "transition_type", "") or ""),
                    "transition_confidence": str(getattr(c, "transition_confidence", "0")),
                    "trigger_flags": list(getattr(c, "trigger_flags", []) or []),
                    "evidence_rules": c.get("evidence_rules", []),
                }
                for c in candidates[:30]
            ],
        }

        # Convert Decimal values to float for JSON serialization
        def _serialize(obj):
            if isinstance(obj, dict): return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list): return [_serialize(i) for i in obj]
            from decimal import Decimal
            if isinstance(obj, Decimal): return float(obj)
            return obj

        # ── 生成结构化 report（缺依赖必须失败，禁止写入半空 report）──
        from stock_service.repositories.report_repository import ReportRepository
        from stock_service.config import StockServiceConfig
        from stock_service.services.recap_service import RecapService

        report_cfg = StockServiceConfig()
        report_repo = ReportRepository(report_cfg)
        await report_repo.initialize()
        try:
            report_service = RecapService(report_repo)
            report = await report_service.build_post_market_report(trade_date.isoformat())
            recap_doc["report"] = {
                "report_type": report.report_type,
                "trade_date": report.trade_date,
                "title": report.title,
                "summary": report.summary,
                "highlights": list(report.highlights or []),
                "sections": [{"heading": h, "items": list(i or [])} for h, i in list(report.sections or [])],
                "metadata": dict(getattr(report, "metadata", {}) or {}),
            }
        finally:
            await report_repo.close()

        snapshot = PostMarketRecapSnapshot(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            source_trace_id=trace_id,
            recap_doc=_serialize(recap_doc),
        )

        affected = await self._write_port.upsert_post_market_recap_snapshot(snapshot)
        # history already written in Step 7e above; strong_watch_history_written tracks the count

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
                        "stock_id": row["stock_id"] if isinstance(row, dict) else row.stock_id,
                        "subject_key": row["subject_key"] if isinstance(row, dict) else row.subject_key,
                        "watch_status": row["watch_status"] if isinstance(row, dict) else row.watch_status,
                        "strong_grade": str(row["strong_grade"]) if isinstance(row, dict) else row.strong_grade,
                        "watch_score": str(row["watch_score"]) if isinstance(row, dict) else str(row.watch_score),
                        "support_score": str(row["support_score"]) if isinstance(row, dict) else str(row.support_score),
                        "support_type": row["support_type"] if isinstance(row, dict) else row.support_type,
                        "prune_mode": row.get("prune_mode") if isinstance(row, dict) else getattr(row, "prune_mode", None),
                        "prune_reason_code": row.get("prune_reason_code") if isinstance(row, dict) else getattr(row, "prune_reason_code", None),
                        "removed_reason": row.get("removed_reason") if isinstance(row, dict) else getattr(row, "removed_reason", None),
                        "kept_because": row.get("kept_because") if isinstance(row, dict) else getattr(row, "kept_because", None),
                    }
                    for row in strong_watch_history[:100]
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
                "strong_watch_input_count": len(d1_input_rows),
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
    def _build_d1_input_rows(
        *,
        trade_date: date,
        strong_watch_rows: list[Any],
        promoted_pool_rows: list[Any],
        prior_watch_rows: list[Any],
    ) -> list[Any]:
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
            return StrongStockTrackingService.is_candidate_eligible(
                watch_status=watch_status,
                pool_entry_type=pool_entry_type,
                candidate_source=source,
            )

        for row in strong_watch_rows:
            watch_status = str(getattr(row, "watch_status", ""))
            pool_entry_type = str(getattr(row, "admission_status", "") or getattr(row, "pool_entry_type", ""))
            if not StrongStockTrackingService.is_candidate_eligible(
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
