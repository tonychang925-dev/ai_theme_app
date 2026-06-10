from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from typing import Any
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.application.services.new_chain_post_market_report_builder import (
    NewChainPostMarketReportBuilder,
)
from stock_processing_service.application.services.post_market_market_summary_llm import (
    PostMarketMarketSummaryLlmService,
)
from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
    LAYER_C_INPUT_MODE,
    BuildStrongStockTrackingUseCase,
)

from stock_processing_service.domain.services.post_market_decision.post_market_decision_engine import (
    PostMarketDecisionEngine,
)

from stock_processing_service.application.services.mainline_discovery_fact_context_builder import (
    MainlineDiscoveryFactContextBuilder,
)
from stock_processing_service.domain.services.mainline_discovery.mainline_logic_chain_builder import (
    MainlineLogicChainBuilder,
)
from stock_processing_service.domain.services.mainline_discovery.mainline_market_acceptance_builder import (
    MainlineMarketAcceptanceBuilder,
)
from stock_processing_service.domain.services.mainline_discovery.major_event_classifier import (
    MajorEventClassifier,
)
from stock_processing_service.domain.services.mainline_discovery.mainline_narrative_judge import (
    MainlineNarrativeJudge,
)
from stock_processing_service.domain.services.mainline_discovery.models import (
    NarrativeJudgeResult,
)
from stock_processing_service.domain.services.mainline_discovery.mainline_discovery_engine import (
    MainlineDiscoveryEngine,
)
from stock_processing_service.domain.services.mainline_discovery.analyst_review_queue_builder import (
    AnalystReviewQueueBuilder,
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


logger = logging.getLogger(__name__)


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
        abnormal_signal_job: Any | None = None,  # BuildStockAbnormalSignalJob — turnover_rate 真源
        report_builder: NewChainPostMarketReportBuilder | None = None,
        market_summary_llm_service: Any | None = None,
        post_market_decision_engine: Any | None = None,
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
        self._weak_to_strong_candidate_use_case = weak_to_strong_candidate_use_case
        self._identity_job = identity_job
        self._mainline_state_job = mainline_state_job
        self._cycle_judgement_job = cycle_judgement_job
        self._evidence_job = evidence_job
        self._abnormal_signal_job = abnormal_signal_job
        self._report_builder = report_builder or NewChainPostMarketReportBuilder()
        self._market_summary_llm_service = market_summary_llm_service or PostMarketMarketSummaryLlmService()
        self._decision_engine = post_market_decision_engine or PostMarketDecisionEngine()
        self._llm_budget_sec = max(int(os.getenv("POST_MARKET_RECAP_LLM_BUDGET_SEC", "90") or 90), 30)
        self._market_summary_llm_timeout_sec = max(
            int(os.getenv("POST_MARKET_RECAP_MARKET_SUMMARY_LLM_TIMEOUT_SEC", "25") or 25),
            10,
        )
        self._narrative_llm_timeout_sec = max(
            int(os.getenv("POST_MARKET_RECAP_NARRATIVE_LLM_TIMEOUT_SEC", "25") or 25),
            10,
        )

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

    @staticmethod
    def _build_one_to_two_persist_rows(
        plan: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        watchlists = plan.to_dict().get("watchlists", {}).get("one_to_two", {}) if hasattr(plan, "to_dict") else {}
        summary = dict(watchlists.get("summary") or {})
        diagnostics = dict(watchlists.get("diagnostics") or {})
        items = [dict(item) for item in watchlists.get("items") or []]
        candidate_features = [dict(item) for item in getattr(plan, "candidate_features", []) or []]

        watch_date = str(summary.get("watch_date") or (items[0].get("watch_date") if items else "") or "")
        trade_date = str(summary.get("trade_date") or (items[0].get("trade_date") if items else "") or "")

        setup_plan_rows: list[dict[str, Any]] = [
            {
                "trade_date": trade_date,
                "watch_date": watch_date,
                "setup_type": "one_to_two",
                "setup_version": "v1",
                "mainline_id": "__SUMMARY__",
                "mainline_name": "OneToTwo Setup Plan",
                "subject_key": "__SUMMARY__",
                "subject_name": "OneToTwo Setup Plan",
                "stock_id": "__SUMMARY__",
                "stock_name": "OneToTwo Setup Plan",
                "lifecycle_state": "summary",
                "market_trade_mode": str(summary.get("market_trade_mode") or ""),
                "allow_trade": False,
                "position_limit": None,
                "decision": "pending_review_only",
                "plan_status": "planned",
                "watch_level": "",
                "final_score": None,
                "summary": json.dumps(summary, ensure_ascii=False, default=str),
                "evidence_rules": [],
                "feature_json": {
                    "summary": summary,
                    "items_count": len(items),
                },
                "risk_flags": [],
                "trigger_plan": {},
                "invalidation_plan": {},
                "exit_plan": {},
                "diagnostics": diagnostics,
                "source_trace_json": {"row_type": "summary"},
            }
        ]

        for item in items:
            setup_plan_rows.append(
                {
                    "trade_date": str(item.get("trade_date") or trade_date),
                    "watch_date": str(item.get("watch_date") or watch_date),
                    "setup_type": str(item.get("setup_type") or "one_to_two"),
                    "setup_version": "v1",
                    "mainline_id": item.get("mainline_id"),
                    "mainline_name": item.get("mainline_name"),
                    "subject_key": str(item.get("subject_key") or ""),
                    "subject_name": str(item.get("subject_name") or ""),
                    "stock_id": str(item.get("stock_id") or ""),
                    "stock_name": str(item.get("stock_name") or ""),
                    "lifecycle_state": str(item.get("lifecycle_state") or ""),
                    "market_trade_mode": str(item.get("market_trade_mode") or ""),
                    "allow_trade": bool(item.get("allow_trade") or False),
                    "position_limit": item.get("position_limit"),
                    "decision": str(item.get("decision") or "reject"),
                    "plan_status": str(item.get("plan_status") or "planned"),
                    "watch_level": str(item.get("watch_level") or ""),
                    "final_score": item.get("final_score"),
                    "summary": str(item.get("summary") or ""),
                    "evidence_rules": item.get("evidence_rules") or [],
                    "feature_json": item.get("feature_json") or {},
                    "risk_flags": item.get("risk_flags") or [],
                    "trigger_plan": item.get("trigger_plan") or {},
                    "invalidation_plan": item.get("invalidation_plan") or [],
                    "exit_plan": item.get("exit_plan") or [],
                    "diagnostics": diagnostics,
                    "source_trace_json": item.get("source_trace_json") or {},
                }
            )

        return setup_plan_rows, candidate_features

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 8,
        skip_prereqs: bool = False,
        skip_layer_c: bool = False,
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

        # P1-3: mark running
        await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
            diagnostics={"snapshot_version": snapshot_version, "batch_id": batch_id, "trace_id": trace_id})
        try:

            # ── Layer A/B 前置（新链自闭环）──
            # 当 collection 任务已通过 Step2 (recap.prerequisites) 完成时，跳过重复执行。
            if not skip_prereqs:
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
                if self._cycle_judgement_job is not None:
                    await self._cycle_judgement_job.execute(
                        trade_date=trade_date,
                        batch_id=batch_id,
                        trace_id=trace_id,
                    )
                if self._mainline_state_job is not None:
                    await self._mainline_state_job.execute(
                        trade_date=trade_date,
                        batch_id=batch_id,
                        trace_id=trace_id,
                    )

            # heartbeat: prerequisites complete
            await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
                diagnostics={"snapshot_version": snapshot_version, "batch_id": batch_id, "trace_id": trace_id, "stage": "prerequisites_done"})

            # ── Build stock_abnormal_signal (required for turnover_rate in OneToTwo) ──
            if not skip_prereqs and self._abnormal_signal_job is not None:
                abnormal_result = await self._abnormal_signal_job.execute(
                    trade_date=trade_date,
                    min_turnover_rate=0.0,  # TushareJoin raw_json lacks turnover_rate; don't filter
                )
                abnormal_status = str(getattr(abnormal_result, "status", "") or "")
                abnormal_rows = int(getattr(abnormal_result, "affected_rows", 0) or 0)
                if not abnormal_status.startswith("ok"):
                    await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
                        diagnostics={
                            "snapshot_version": snapshot_version, "batch_id": batch_id,
                            "trace_id": trace_id, "stage": "abnormal_signal_failed",
                            "abnormal_status": abnormal_status,
                            "abnormal_rows": abnormal_rows,
                        })
                    raise RuntimeError(
                        f"build_stock_abnormal_signal failed: {abnormal_status}"
                    )
                await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
                    diagnostics={
                        "snapshot_version": snapshot_version, "batch_id": batch_id,
                        "trace_id": trace_id, "stage": "abnormal_signal_done",
                        "abnormal_status": abnormal_status,
                        "abnormal_rows": abnormal_rows,
                    })

            # ── Layer C: 强势股观察池由独立 use case 负责，recap 只消费其对象输出 ──
            if skip_layer_c:
                layer_c_metrics = {"skip_layer_c": True, "stock_ids": []}
            else:
                layer_c_result = await self._strong_stock_tracking_use_case.execute(
                    trade_date=trade_date,
                    window_days=7,
                    lookback_days=lookback_days,
                )
                layer_c_metrics = dict(layer_c_result.metrics or {})

            # ── Layer D1: recap 只读取既有候选池，不执行选股逻辑 ──
            read_existing_w2s = getattr(self._read_port, "get_w2s_candidates_by_trade_date", None)
            existing_w2s_rows: list[Any] = []
            if callable(read_existing_w2s):
                try:
                    existing_w2s_rows = list(await read_existing_w2s(trade_date, limit=20))
                except Exception:
                    logger.warning("D1 candidate read failed, continuing without D1 rows")
            _d1_total_in = len(existing_w2s_rows)
            _d1_pass = len(existing_w2s_rows)
            _d1_fail_pct = 0
            _d1_fail_history = 0
            _d1_fail_gene = 0
            _d1_fail_strong = 0
            _d1_fail_support = 0
            d1_written = 0

            # 构建 recap_doc 所需元数据
            pool_rows: list[Any] = []  # 保留兼容性
            stock_ids = list(layer_c_metrics.get("stock_ids") or [])
            subject_keys = list(layer_c_metrics.get("subject_keys") or [])
            strong_watch_rows: list[Any] = []
            history_written = int(layer_c_metrics.get("history_written") or 0)
            strong_watch_history: list[Any] = list(layer_c_metrics.get("history_rows") or [])
            existing_d1_candidate_rows: list[Any] = existing_w2s_rows
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
            layer_a_identity_hit_count = int(layer_c_metrics.get("identity_hit_count") or 0)
            layer_b_cycle_hit_count = int(layer_c_metrics.get("cycle_hit_count") or 0)

            # P1: skip_layer_c 仅标记跳过，不补读任何历史数据。
            if skip_layer_c:
                layer_a_identity_hit_count = max(layer_a_identity_hit_count, 1)
                layer_b_cycle_hit_count = max(layer_b_cycle_hit_count, 1)
            input_fingerprint = LAYER_C_INPUT_MODE
            # 构建兼容 recap_doc 的 D1 只读候选列表（来自既有 weak_to_strong_candidate_pool，不在 recap 内生成）
            candidates = [
                {
                    "stock_id": str(c.get("stock_id", "")),
                    "stock_name": str(c.get("stock_name", "")),
                    "subject_key": str(c.get("subject_key", "")),
                    "subject_name": str(c.get("theme_name", "")),
                    "candidate_score": float(c.get("candidate_score") or 0),
                    "candidate_level": str(c.get("pool_entry_type") or "observe_only"),
                    "candidate_type": str(c.get("candidate_type") or ""),
                    "transition_type": str(c.get("weak_type") or ""),
                    "transition_confidence": "50",
                    "trigger_flags": [],
                    "evidence_rules": [],
                    "support_type": str(c.get("support_type") or ""),
                    "support_score": float(c.get("support_strength") or 0),
                    "gap_hit": False,
                    "gap_hit_mode": "miss",
                }
                for c in existing_w2s_rows
            ]
            formal_candidates = [
                c for c in candidates if str(c.get("candidate_level", "")).lower() in {"formal", "s", "a", "b"}
            ]
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
                "strong_watch_input_count": len(strong_watch_history),
                "strong_watch_input_7d_count": len(strong_watch_history),
                "d1_total_in": _d1_total_in,
                "d1_pass": _d1_pass,
                "d1_fail_pct_gate": _d1_fail_pct,
                "d1_fail_history": _d1_fail_history,
                "d1_fail_gene": _d1_fail_gene,
                "d1_fail_strong": _d1_fail_strong,
                "d1_fail_support": _d1_fail_support,
                "strong_watch_promoted_count": len(existing_d1_candidate_rows),
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
                    for row in strong_watch_history  # full Layer C 7-day pool — no truncation
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
                    for r in strong_watch_history[:100]
                ],
                "strong_watch_input_7d_stock_ids": sorted(
                    {str(r.get("stock_id", "")) for r in strong_watch_history if str(r.get("stock_id", "") or "")}
                ),
                "strong_watch_input_7d_source": (
                    "legacy_strong_watch_pool_or_history"
                    if layer_c_input_mode == "legacy_watch_pool"
                    else "strong_watch_pool_history_single_source"
                ),
                "promoted_pool_stock_ids": sorted(
                    {str(r.get("stock_id", "")) for r in existing_d1_candidate_rows if str(r.get("stock_id", "") or "")}
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
                    for r in existing_d1_candidate_rows[:200]
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

            report_context_fn = getattr(self._read_port, "get_post_market_report_context", None)
            if callable(report_context_fn):
                try:
                    recap_doc["report_context"] = await report_context_fn(trade_date=trade_date)
                except TypeError:
                    recap_doc["report_context"] = await report_context_fn(trade_date, None, None)

            # Convert Decimal values to float for JSON serialization
            def _serialize(obj):
                if isinstance(obj, dict): return {k: _serialize(v) for k, v in obj.items()}
                if isinstance(obj, list): return [_serialize(i) for i in obj]
                from decimal import Decimal
                if isinstance(obj, Decimal): return float(obj)
                return obj

            # ── P0-2: readiness guard — 核心表为空时拒绝写快照 ──
            readiness = await self._check_post_market_readiness(trade_date)
            recap_doc.setdefault("diagnostics", {})["readiness"] = readiness
            if readiness["status"] != "ready":
                await self._mark_job_status(trade_date, "post_market_recap_generate", "failed_precondition",
                    error_code="POST_MARKET_DERIVED_DATA_NOT_READY",
                    diagnostics={"readiness": readiness, "snapshot_version": snapshot_version})
                await self._idempotency_port.mark_job_completed(
                    job_key,
                    {
                        "trade_date": trade_date.isoformat(),
                        "snapshot_version": snapshot_version,
                        "status": "failed_precondition",
                        "readiness": readiness,
                    },
                )
                return BuildResult(
                    name="build_post_market_recap",
                    trade_date=trade_date.isoformat(),
                    affected_rows=0,
                    status="failed_precondition",
                    batch_id=batch_id,
                    trace_id=trace_id,
                    warnings=[f"POST_MARKET_DERIVED_DATA_NOT_READY: status={readiness['status']} missing={readiness.get('missing_tables', [])}"],
                    metrics={"readiness": readiness},
                )

            # ── P2: 结构化 theme_reviews 生成 ──
            report_context = recap_doc.get("report_context") or {}
            llm_deadline = time.monotonic() + self._llm_budget_sec
            diag = recap_doc.setdefault("diagnostics", {})
            llm_diag = diag.setdefault("llm", {})
            llm_diag.update(
                {
                    "budget_sec": self._llm_budget_sec,
                    "market_summary_timeout_sec": self._market_summary_llm_timeout_sec,
                    "narrative_timeout_sec": self._narrative_llm_timeout_sec,
                }
            )
            recap_doc["market_summary"] = await self._build_market_summary_llm(
                trade_date,
                report_context,
                llm_deadline=llm_deadline,
            )
            theme_context_map = await self._build_theme_context_map(trade_date, report_context)
            recap_doc["theme_reviews"] = self._build_theme_reviews(theme_context_map)
            recap_doc["diagnostics"]["coverage"] = self._build_theme_review_coverage(theme_context_map)
            _coverage = recap_doc["diagnostics"]["coverage"]

            recap_doc["capital_reviews"] = self._build_capital_reviews(report_context.get("dragon_tiger") or [])
            recap_doc["strong_stock_reviews"] = await self._build_strong_stock_reviews(trade_date)
            strong_stock_reviews_count = len(recap_doc["strong_stock_reviews"] or [])
            recap_doc["strong_stock_reviews_count"] = strong_stock_reviews_count
            strong_hotspot_subjects = self._build_strong_hotspot_subjects(recap_doc["strong_stock_reviews"] or [])
            recap_doc["strong_hotspot_subjects"] = strong_hotspot_subjects
            recap_doc["hotspot_subjects"] = strong_hotspot_subjects
            recap_doc["mainline_hotspots"] = strong_hotspot_subjects
            recap_doc.setdefault("diagnostics", {})["strong_hotspot_subjects_count"] = len(strong_hotspot_subjects)
            strong_watch_history_count = len(strong_watch_history)

            # ── PR-7: Mainline Discovery parallel output ──
            await self._run_mainline_discovery(
                trade_date,
                snapshot_version,
                report_context,
                theme_context_map,
                recap_doc,
                batch_id,
                trace_id,
                llm_deadline=llm_deadline,
            )

            # ── P0: 交易体系决策输出 ──
            decision_payload = self._decision_engine.execute(
                trade_date=trade_date,
                report_context=report_context,
                theme_context_map=theme_context_map,
                market_summary=recap_doc.get("market_summary") or {},
                strong_stock_reviews=recap_doc.get("strong_stock_reviews") or [],
            )
            recap_doc.update(decision_payload)

            confirmed_mainline_hotspots = self._build_confirmed_mainline_hotspots(recap_doc.get("active_mainline_universe") or {})
            if confirmed_mainline_hotspots:
                merged_hotspots = self._merge_hotspot_subjects(
                    recap_doc.get("strong_hotspot_subjects") or [],
                    confirmed_mainline_hotspots,
                )
                recap_doc["strong_hotspot_subjects"] = merged_hotspots
                recap_doc["hotspot_subjects"] = merged_hotspots
                recap_doc["mainline_hotspots"] = merged_hotspots

            # heartbeat: building one_to_two
            await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
                diagnostics={"snapshot_version": snapshot_version, "batch_id": batch_id, "trace_id": trace_id, "stage": "building_one_to_two"})

            # Inject turnover_rate into source_doc.
            # Tushare 'daily' API does NOT include turnover_rate (it's in 'daily_basic'
            # which is a separate API). subject_stock_daily_snapshot also lacks this
            # column. Without this injection, all candidates get turnover_rate=None →
            # "低换手，筹码交换不足" reject in RuleEngine v1.2 tiered filtering.
            #
            # The backtest path does the same injection from stock_abnormal_signal
            # in OneToTwoBacktestFeatureSnapshotService._get_report_context.
            if not recap_doc.get("stock_facts"):
                try:
                    pool = getattr(self._read_port, "_pool", None)
                    if pool is None:
                        facade = getattr(self._read_port, "_db", None)
                        db_client = getattr(facade, "_db", None) if facade else None
                        pool = getattr(db_client, "pool", None) if db_client else None
                    if pool is not None:
                        async with pool.acquire() as conn:
                            rows = await conn.fetch(
                                "SELECT stock_id, turnover_rate FROM stock_abnormal_signal "
                                "WHERE trade_date = $1::date",
                                trade_date,
                            )
                            stock_facts: list[dict[str, Any]] = []
                            for r in rows:
                                sid = str(r.get("stock_id") or "").strip()
                                tr = r.get("turnover_rate")
                                if sid and tr is not None:
                                    # stock_abnormal_signal stores percentage (e.g. 9.2 = 9.2%);
                                    # OneToTwo rule config uses fraction (0.092 = 9.2%)
                                    stock_facts.append({"stock_id": sid, "turnover_rate": float(tr) / 100})
                            if stock_facts:
                                recap_doc["stock_facts"] = stock_facts
                except Exception:
                    pass

            from stock_processing_service.application.services.one_to_two_setup_plan_engine import (
                OneToTwoSetupPlanEngine,
            )
            one_to_two_plan = await OneToTwoSetupPlanEngine().build(
                trade_date=trade_date,
                read_port=self._read_port,
                source_doc=recap_doc,
            )
            one_to_two_payload = one_to_two_plan.to_dict().get("watchlists", {}).get("one_to_two", {})
            setup_plan_rows, candidate_feature_rows = self._build_one_to_two_persist_rows(one_to_two_plan)
            setup_plan_written = await self._write_port.upsert_post_market_setup_plan_rows(setup_plan_rows)
            if setup_plan_written <= 0:
                raise RuntimeError("failed to persist post_market_setup_plan rows")
            if candidate_feature_rows:
                feature_written = await self._write_port.upsert_one_to_two_candidate_feature_rows(candidate_feature_rows)
                if feature_written <= 0:
                    raise RuntimeError("failed to persist one_to_two_candidate_feature rows")
            recap_doc["post_market_setup_plan"] = one_to_two_payload
            recap_doc["watchlists"] = {"one_to_two": one_to_two_payload}

            recap_report = self._report_builder.build(recap_doc)
            recap_doc["report"] = recap_report
            if isinstance(recap_report, dict):
                market_overview_review = recap_report.get("market_overview_review")
                if isinstance(market_overview_review, dict):
                    recap_doc["market_overview_review"] = market_overview_review

            snapshot = PostMarketRecapSnapshot(
                trade_date=trade_date,
                snapshot_version=snapshot_version,
                batch_id=batch_id,
                trace_id=trace_id,
                source_trace_id=trace_id,
                recap_doc=_serialize(recap_doc),
            )

            # heartbeat: writing snapshot
            await self._mark_job_status(trade_date, "post_market_recap_generate", "running",
                diagnostics={"snapshot_version": snapshot_version, "batch_id": batch_id, "trace_id": trace_id, "stage": "writing_snapshot"})

            affected = await self._write_port.upsert_post_market_recap_snapshot(snapshot)
            await self._mark_job_status(trade_date, "post_market_recap_generate", "success",
                diagnostics={"affected_rows": affected, "snapshot_version": snapshot_version})
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
                    "strong_watch_input_count": len(strong_watch_history),
                    "strong_watch_promoted_count": len(existing_d1_candidate_rows),
                    "strong_watch_history_count": strong_watch_history_count,
                    "strong_stock_reviews_count": strong_stock_reviews_count,
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
                    "theme_review_count": len(recap_doc.get("theme_reviews") or []),
                    "theme_review_snapshot_status": _coverage.get("snapshot_status"),
                    "theme_review_cycle_joined_count": _coverage.get("cycle_joined_count"),
                    "layer_c_input_mode": layer_c_input_mode,
                    "legacy_watch_input_count": legacy_watch_input_count,
                    "candidate_count": len(candidates),
                    "candidate_count_formal": len(formal_candidates),
                    "candidate_count_observe": len(observe_candidates),
                    "observe_candidates_count": len(candidate_service_observe_candidates),
                    "skip_prereqs": bool(skip_prereqs),
                },
                published_events=["snapshot_built"],
                cache_writes=3 if self._cache_port is not None else 0,
            )
        except Exception as exc:
            diagnostics = {
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            await self._mark_job_status(
                trade_date,
                "post_market_recap_generate",
                "failed",
                error_code=type(exc).__name__,
                diagnostics=diagnostics,
            )
            mark_failed = getattr(self._idempotency_port, "mark_job_failed", None)
            if callable(mark_failed):
                try:
                    await mark_failed(job_key, diagnostics)
                except Exception:
                    pass
            release = getattr(self._idempotency_port, "release_job_idempotency", None)
            if callable(release):
                try:
                    await release(job_key)
                except Exception:
                    pass
            logger.exception(
                "build_post_market_recap failed",
                extra={
                    "trade_date": trade_date.isoformat(),
                    "snapshot_version": snapshot_version,
                    "batch_id": batch_id,
                    "trace_id": trace_id,
                },
            )
            raise

    @staticmethod
    def _build_d1_input_rows(
        *,
        trade_date: date,
        strong_watch_rows: list[Any],
        existing_d1_candidate_rows: list[Any],
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
        for row in existing_d1_candidate_rows:
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

    # ── P2: theme_reviews 结构化生成 ──

    MAX_THEME_REVIEWS = 20

    async def _build_market_summary_llm(
        self,
        trade_date: date,
        report_context: dict[str, Any],
        *,
        llm_deadline: float | None = None,
    ) -> dict[str, Any] | None:
        service = self._market_summary_llm_service
        if service is None:
            return None
        try:
            timeout_sec = self._market_summary_llm_timeout_sec
            if llm_deadline is not None:
                remaining = llm_deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("post-market market_summary LLM skipped: llm budget exhausted")
                    return None
                timeout_sec = min(timeout_sec, remaining)
            return await asyncio.wait_for(
                service.build(trade_date=trade_date, report_context=report_context),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning("post-market market_summary LLM timeout after %.1fs, fallback to deterministic summary", timeout_sec)
            return None
        except Exception as exc:
            logger.warning("post-market market_summary LLM failed, fallback to deterministic summary: %s", exc)
            return None

    async def _mark_job_status(
        self,
        trade_date_val: date,
        job_key: str,
        status: str,
        error_code: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        """P1-3: 写入 post_market_job_status 状态。不影响主链路。"""
        try:
            from stock_processing_service.application.services.post_market_job_status_service import (
                PostMarketJobStatusService,
            )
            pool = getattr(self._read_port, "_pool", None)
            if pool is None:
                facade = getattr(self._read_port, "_db", None)
                db_client = getattr(facade, "_db", None) if facade else None
                pool = getattr(db_client, "pool", None) if db_client else None
            if pool is None:
                return
            jss = PostMarketJobStatusService(pool=pool)
            await jss.mark_finished(
                trade_date_val=trade_date_val,
                job_key=job_key,
                status=status,
                error_code=error_code,
                diagnostics=diagnostics,
            )
        except Exception:
            pass

    async def _run_mainline_discovery(
        self,
        trade_date: date,
        snapshot_version: str,
        report_context: dict[str, Any],
        theme_context_map: dict[str, dict[str, Any]],
        recap_doc: dict[str, Any],
        batch_id: str = "",
        trace_id: str = "",
        llm_deadline: float | None = None,
    ) -> None:
        """PR-7: Run mainline discovery pipeline and write results to recap_doc.

        Best-effort. Any exception is caught and recorded in diagnostics.
        Never blocks the main recap generation.
        """
        from stock_processing_service.application.services.mainline_discovery_fact_context_builder import (
            MainlineDiscoveryFactContext, MainlineDiscoveryFactContextBuilder,
        )
        try:
            # ── PR-13A: build active mainline universe early (registry read, no other deps) ──
            from stock_processing_service.application.services.active_mainline_universe_builder import (
                ActiveMainlineUniverseBuilder,
            )
            active_universe = await ActiveMainlineUniverseBuilder(self._read_port).build(
                trade_date=trade_date,
            )

            # ── build fact context ──
            fact_builder = MainlineDiscoveryFactContextBuilder(self._read_port)
            fact_ctx = await fact_builder.build(
                trade_date=trade_date,
                theme_context_map=theme_context_map,
                lookback_days=7,
            )
            fc = fact_ctx.to_dict()

            # ── run logic chain ──
            logic_builder = MainlineLogicChainBuilder()
            logic_result = await logic_builder.build(
                trade_date=trade_date,
                candidate_subjects=[s["subject_key"] for s in fc["candidate_subjects"]],
                report_context=report_context,
                event_rows_by_subject=fc.get("event_rows_by_subject"),
            )
            logic_by_sk = {
                sk: ev.to_dict() for sk, ev in logic_result.items()
            } if isinstance(logic_result, dict) else {}

            # ── run market acceptance ──
            market_builder = MainlineMarketAcceptanceBuilder()
            market_result = market_builder.build(
                trade_date=trade_date,
                candidate_subjects=fc["candidate_subjects"],
                event_rows_by_subject=fc["event_rows_by_subject"],
                cycle_evidence_by_subject=fc["cycle_evidence_by_subject"],
                cycle_judgement_by_subject=fc["cycle_judgement_by_subject"],
                capital_by_subject=fc["capital_by_subject"],
                stock_facts_by_subject=fc["stock_facts_by_subject"],
            )
            market_by_sk = {sk: r.to_dict() for sk, r in market_result.items()}

            # ── run major event classifier ──
            major_classifier = MajorEventClassifier()
            major_by_sk: dict[str, dict] = {}
            for sk, lev in logic_by_sk.items():
                ec = lev.get("event_chain", [])
                es = lev.get("event_series", [])
                if ec:
                    result = major_classifier.classify(event_chain=ec, event_series=es)
                    major_by_sk[sk] = result.to_dict()

            # ── run narrative judge (best-effort, LLM may fail) ──
            def _llm_factory():
                from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
                import os
                return ReliableDeepSeekParser(
                    model_name=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                    config={"max_retries": 1, "timeout": 25, "temperature": 0.1,
                            "enable_cache": True, "cache_ttl": 3600})
            narrative_builder = MainlineNarrativeJudge(
                parser_factory=_llm_factory,
                timeout_sec=self._narrative_llm_timeout_sec,
            )
            narrative_by_sk: dict[str, dict] = {}
            llm_diag = recap_doc.setdefault("diagnostics", {}).setdefault("llm", {})
            llm_diag.setdefault("narrative_timeouts", 0)
            llm_diag.setdefault("narrative_errors", 0)
            llm_diag.setdefault("narrative_budget_exhausted", False)
            llm_diag.setdefault("narrative_skipped_subjects", [])
            for sk, lev in logic_by_sk.items():
                if not lev.get("event_chain"):
                    narrative_by_sk[sk] = NarrativeJudgeResult().to_dict()
                    continue
                if llm_deadline is not None:
                    remaining = llm_deadline - time.monotonic()
                    if remaining <= 0:
                        llm_diag["narrative_budget_exhausted"] = True
                        llm_diag["narrative_skipped_subjects"].extend(
                            [subject_key for subject_key in logic_by_sk.keys() if subject_key not in narrative_by_sk]
                        )
                        break
                timeout_sec = self._narrative_llm_timeout_sec
                if llm_deadline is not None:
                    timeout_sec = min(timeout_sec, max(0.0, llm_deadline - time.monotonic()))
                if timeout_sec <= 0:
                    llm_diag["narrative_budget_exhausted"] = True
                    narrative_by_sk[sk] = NarrativeJudgeResult(
                        is_mainline_logic=False,
                        narrative_score=None,
                        narrative_level="unavailable",
                        supporting_event_ids=[],
                        negative_reasons=["LLM 总预算已耗尽，跳过叙事裁判"],
                        confidence=0.0,
                        diagnostics={"skip_reason": "llm_budget_exhausted"},
                    ).to_dict()
                    continue
                try:
                    nj = await asyncio.wait_for(narrative_builder.judge(
                        subject_key=sk,
                        theme_name=_theme_name_for_sk(fc["candidate_subjects"], sk),
                        event_chain=lev.get("event_chain", []),
                        event_series=lev.get("event_series", []),
                        event_stats=fc.get("event_stats_by_subject", {}).get(sk),
                        major_event_classification=major_by_sk.get(sk),
                    ), timeout=timeout_sec)
                except asyncio.TimeoutError:
                    llm_diag["narrative_timeouts"] += 1
                    llm_diag["narrative_skipped_subjects"].append(sk)
                    nj = NarrativeJudgeResult(
                        is_mainline_logic=False,
                        narrative_score=None,
                        narrative_level="unavailable",
                        supporting_event_ids=[],
                        negative_reasons=["LLM 调用超时，无法生成叙事判断"],
                        confidence=0.0,
                        diagnostics={"skip_reason": "llm_timeout", "timeout_sec": timeout_sec},
                    )
                except Exception as exc:
                    llm_diag["narrative_errors"] += 1
                    llm_diag["narrative_skipped_subjects"].append(sk)
                    logger.warning("post-market narrative judge failed for %s, fallback to unavailable: %s", sk, exc)
                    nj = NarrativeJudgeResult(
                        is_mainline_logic=False,
                        narrative_score=None,
                        narrative_level="unavailable",
                        supporting_event_ids=[],
                        negative_reasons=["LLM 调用失败，无法生成叙事判断"],
                        confidence=0.0,
                        diagnostics={"skip_reason": "llm_error", "error": str(exc)},
                    )
                narrative_by_sk[sk] = nj.to_dict()

            # ── run discovery engine ──
            engine = MainlineDiscoveryEngine()
            decisions = engine.evaluate_all(
                candidate_subjects=fc["candidate_subjects"],
                logic_evidence_by_subject=logic_by_sk,
                market_acceptance_by_subject=market_by_sk,
                major_event_by_subject=major_by_sk,
                narrative_by_subject=narrative_by_sk,
                active_mainline_universe=active_universe,
            )
            # Extract existing_mainline_updates from decisions for diagnostics
            existing_updates = [
                d.to_dict() for d in decisions
                if d.machine_state in ("existing_mainline_strengthening", "existing_mainline_branch_event")
            ]

            # ── run analyst review queue ──
            queue_builder = AnalystReviewQueueBuilder()
            review_items, review_diag = queue_builder.build(
                decisions=decisions,
                trade_date=trade_date.isoformat(),
                event_evidence_by_subject=logic_by_sk,
                narrative_by_subject=narrative_by_sk,
                market_by_subject=market_by_sk,
            )
            # Sanitize theme_name: cap at 40 chars, fallback to subject_key
            for it in review_items:
                tn = (it.theme_name or "").strip()
                if len(tn) > 40 or tn.startswith("【"):
                    # Try candidate_subjects first
                    short = _theme_name_for_sk(fc.get("candidate_subjects", []), it.subject_key)
                    it.theme_name = (short or it.subject_key)[:40] if short and len(short) < 40 else it.subject_key[:40]
                elif not tn:
                    it.theme_name = it.subject_key[:40]

            # ── write to recap_doc ──
            sd = fc.get("diagnostics", {})
            recap_doc["mainline_discovery_reviews"] = [d.to_dict() for d in decisions]
            recap_doc["mainline_discovery_diagnostics"] = {
                "candidate_subject_count": sd.get("candidate_subject_count", 0),
                "event_chain_subject_count": sd.get("event_chain_subject_count", 0),
                "logic_score_non_null_count": _count_non_null_scores(logic_by_sk),
                "market_acceptance_non_null_count": _count_non_null_market(market_by_sk),
                "machine_fast_candidate_count": sum(1 for d in decisions if d.machine_state == "machine_fast_candidate"),
                "machine_slow_candidate_count": sum(1 for d in decisions if d.machine_state == "machine_slow_candidate"),
                "logic_only_count": sum(1 for d in decisions if d.machine_state == "logic_only"),
                "market_noise_count": sum(1 for d in decisions if d.machine_state == "market_noise"),
                "rotation_hotspot_count": sum(1 for d in decisions if d.machine_state == "rotation_hotspot"),
                "rejected_count": sum(1 for d in decisions if d.machine_state == "rejected"),
            }
            recap_doc["analyst_review_items"] = [it.to_dict() for it in review_items]
            recap_doc["analyst_review_diagnostics"] = review_diag.to_dict()
            recap_doc["existing_mainline_updates"] = existing_updates

            # PR-9B: persist to mainline_review_queue (best-effort)
            await self._persist_review_queue(trade_date, review_items)

        except Exception:
            logger.exception("Mainline discovery pipeline failed, continuing without it")
            recap_doc["mainline_discovery_reviews"] = []
            recap_doc["mainline_discovery_reviews_error"] = "pipeline_failed"
            recap_doc["mainline_discovery_diagnostics"] = {"error": "pipeline_failed"}

        # ── PR-10: Mainline Lifecycle pipeline ──
        await self._run_mainline_lifecycle(trade_date, recap_doc, snapshot_version, batch_id, trace_id)

    async def _run_mainline_lifecycle(
        self, trade_date: date, recap_doc: dict[str, Any], snapshot_version: str,
        batch_id: str = "", trace_id: str = "",
    ) -> None:
        """PR-10: Run lifecycle pipeline for confirmed mainlines."""
        def _serialize(obj):
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        from stock_processing_service.application.services.mainline_lifecycle.mainline_lifecycle_fact_context_builder import (
            MainlineLifecycleFactContextBuilder,
        )
        from stock_processing_service.domain.services.mainline_lifecycle.layer_b_lifecycle_adapter import (
            MainlineLifecycleLayerBAdapter,
        )

        report_context = recap_doc.get("report_context") or {}
        reviews: list[Any] = []
        regime: dict[str, Any] = {}

        try:
            fc_builder = MainlineLifecycleFactContextBuilder(self._read_port)
            fact_ctx = await fc_builder.build(trade_date=trade_date)

            adapter = MainlineLifecycleLayerBAdapter()
            reviews, lifecycle_diag = adapter.build(trade_date=trade_date.isoformat(), fact_ctx=fact_ctx)

            recap_doc["mainline_lifecycle_reviews"] = [r.to_dict() for r in reviews]
            recap_doc["mainline_lifecycle_diagnostics"] = {**fact_ctx.diagnostics, **lifecycle_diag}

            # ── PR-11: Market Regime ──
            from stock_processing_service.application.services.market_regime.market_regime_fact_context_builder import (
                MarketRegimeFactContextBuilder,
            )
            from stock_processing_service.domain.services.market_regime.market_regime_engine import MarketRegimeEngine

            regime_ctx = await MarketRegimeFactContextBuilder().build(
                trade_date=trade_date,
                report_context=report_context,
                lifecycle_reviews=[r.to_dict() for r in reviews],
            )
            regime_engine = MarketRegimeEngine()
            regime = regime_engine.evaluate(
                trade_date=trade_date.isoformat(),
                index_kline=regime_ctx.index_kline,
                market_snapshot=regime_ctx.market_snapshot,
                lifecycle_reviews=regime_ctx.lifecycle_reviews,
            )
            regime_dict = regime.to_dict()
            regime_dict["index_technical_reviews"] = regime_ctx.index_technical_reviews
            recap_doc["market_regime_review"] = regime_dict
            recap_doc["market_regime_diagnostics"] = {
                **regime_ctx.diagnostics,
                "index_technical_reviews": regime_ctx.index_technical_reviews,
            }
        except Exception:
            logger.exception("Mainline discovery pipeline failed, continuing without it")
            recap_doc["mainline_lifecycle_reviews"] = []
            recap_doc["mainline_lifecycle_diagnostics"] = {"error": "pipeline_failed"}
            recap_doc["market_regime_review"] = {}
            recap_doc["market_regime_diagnostics"] = {"error": "pipeline_failed"}

        # ── PR-12.5: ActiveMainlineUniverse ──
        from stock_processing_service.application.services.active_mainline_universe_builder import (
            ActiveMainlineUniverseBuilder,
        )
        active_universe = await ActiveMainlineUniverseBuilder(self._read_port).build(trade_date=trade_date)
        recap_doc["active_mainline_universe"] = active_universe.to_dict()
        confirmed_mainlines = active_universe.active_mainlines
        cml_error = None
        if not confirmed_mainlines:
            cml_error = "no_active_mainlines_in_registry"

        # ── PR-12: PostMarketDecisionV2 ──
        from stock_processing_service.domain.services.post_market_decision_v2.post_market_decision_engine_v2 import (
            PostMarketDecisionEngineV2,
        )
        layer_c_source: str = "strong_stock_watch_view_rows"
        read_layer_c_view_rows = getattr(self._read_port, "get_strong_stock_watch_view_rows", None)
        if not callable(read_layer_c_view_rows):
            raise RuntimeError(
                "BuildPostMarketRecapJob requires get_strong_stock_watch_view_rows; "
                "Layer C read-model is unavailable"
            )
        layer_c_rows: list[dict[str, Any]] = [
            dict(row or {})
            for row in await read_layer_c_view_rows(
                end_date=trade_date,
                window_days=7,
                include_removed=False,
                latest_per_stock=False,
                stock_id=None,
                limit=5000,
            )
        ]

        # Build strong_pool + trading_permission via PDV2 (Layer C display only in recap)
        pdv2_engine = PostMarketDecisionEngineV2()
        pdv2 = pdv2_engine.evaluate(
            trade_date=trade_date.isoformat(),
            confirmed_mainlines=confirmed_mainlines,
            mainline_lifecycle=[r.to_dict() for r in reviews],
            market_regime=regime.to_dict() if hasattr(regime, "to_dict") else dict(regime or {}),
            stock_pool_rows=layer_c_rows,
        )
        pdv2.diagnostics["layer_c_rows"] = len(layer_c_rows)
        pdv2.diagnostics["layer_c_source"] = layer_c_source
        if cml_error:
            pdv2.diagnostics["confirmed_mainline_error"] = cml_error
        recap_doc["post_market_decision_v2"] = pdv2.to_dict()

        # ── PR-13A: persist mainline daily state ──
        await self._persist_mainline_daily_state(trade_date, recap_doc, batch_id or "", trace_id or "")

        # Re-write snapshot with PDV2 D1 data (written before PDV2 section at line 632)
        updated_snapshot = PostMarketRecapSnapshot(
            trade_date=trade_date, snapshot_version=snapshot_version,
            batch_id=batch_id, trace_id=trace_id, source_trace_id=trace_id,
            recap_doc=_serialize(recap_doc),
        )
        await self._write_port.upsert_post_market_recap_snapshot(updated_snapshot)

    async def _persist_review_queue(self, trade_date: date, review_items: list) -> None:
        """PR-9B: Persist analyst_review_items to mainline_review_queue."""
        try:
            rows_to_upsert = []
            for item in review_items:
                d = item.to_dict()
                rows_to_upsert.append({
                    "review_id": d.get("review_id", ""),
                    "trade_date": trade_date,
                    "subject_key": d.get("subject_key", ""),
                    "theme_name": d.get("theme_name", ""),
                    "mainline_id": d.get("mainline_id", ""),
                    "mainline_name": d.get("mainline_name", ""),
                    "machine_state": d.get("machine_state", ""),
                    "final_mainline_state": d.get("final_mainline_state", "pending_review"),
                    "mainline_type": d.get("mainline_type", ""),
                    "confirmation_path": d.get("confirmation_path", ""),
                    "trigger_mode": d.get("trigger_mode", ""),
                    "review_reason": d.get("review_reason", ""),
                    "review_priority": d.get("review_priority", 0),
                    "review_status": d.get("review_status", "pending"),
                    "suggested_human_decision": d.get("suggested_human_decision", ""),
                    "scores": d.get("scores", {}),
                    "evidence": d.get("evidence", {}),
                    "risk_flags": d.get("risk_flags", {}),
                    "diagnostics": d.get("diagnostics", {}),
                })
            if rows_to_upsert:
                fn = getattr(self._write_port, "upsert_mainline_review_queue_rows", None)
                if callable(fn):
                    affected = await fn(rows_to_upsert)
                    logger.info("Persisted %s review items to mainline_review_queue", affected)
        except Exception:
            logger.exception("Failed to persist review queue items")

    async def _persist_mainline_daily_state(
        self, trade_date: date, recap_doc: dict[str, Any], batch_id: str, trace_id: str,
    ) -> None:
        """PR-13A: 将每日主线状态快照写入 mainline_daily_state 表。"""
        try:
            from stock_processing_service.contracts.dto.mainline_daily_state import (
                MainlineDailyStateDTO,
            )

            amu = recap_doc.get("active_mainline_universe", {})
            regime = recap_doc.get("market_regime_review", {})
            pdv2 = recap_doc.get("post_market_decision_v2", {})
            lifecycles = {r.get("mainline_id", ""): r for r in recap_doc.get("mainline_lifecycle_reviews", [])}
            mainlines = amu.get("active_mainlines", [])

            # Per-mainline counts from PDV2
            strong_by_ml: dict[str, int] = {}
            d1_by_ml: dict[str, int] = {}
            focus_by_ml: dict[str, int] = {}
            for r in pdv2.get("strong_stock_pool_reviews", []):
                mid = r.get("mainline_id", "")
                strong_by_ml[mid] = strong_by_ml.get(mid, 0) + 1
            for r in pdv2.get("weak_to_strong_d1_reviews", []):
                mid = r.get("mainline_id", "")
                d1_by_ml[mid] = d1_by_ml.get(mid, 0) + 1
            for r in pdv2.get("next_day_focus_stocks", []):
                mid = r.get("mainline_id", "")
                focus_by_ml[mid] = focus_by_ml.get(mid, 0) + 1

            # Extract no_trade_blocking_rule from regime
            no_trade_reasons = regime.get("no_trade_reasons", [])
            blocking_rule = ""
            if no_trade_reasons and isinstance(no_trade_reasons, list):
                blocking_rule = str(no_trade_reasons[0]) if no_trade_reasons else ""

            rows = []
            for ml in mainlines:
                mid = str(ml.get("mainline_id") or "")
                lr = lifecycles.get(mid, {})
                lr_diag = lr.get("diagnostics", {}) if isinstance(lr.get("diagnostics"), dict) else {}

                dto = MainlineDailyStateDTO(
                    trade_date=trade_date,
                    mainline_id=mid,
                    canonical_subject_key=str(ml.get("canonical_subject_key") or ""),
                    mainline_name=str(ml.get("mainline_name") or ""),
                    run_id=f"{batch_id}/{trace_id}",
                    active_subject_keys_json=amu.get("active_subject_keys", []),
                    active_subject_count=int(amu.get("active_subject_count", 0)),
                    event_count_1d=int(lr_diag.get("event_count_1d") or lr_diag.get("event_1d") or 0),
                    event_count_3d=int(lr_diag.get("event_count_3d") or 0),
                    event_count_7d=int(lr_diag.get("event_count_7d") or 0),
                    lifecycle_state=str(lr.get("lifecycle_state") or "unknown"),
                    mainline_alive=bool(lr.get("mainline_alive", False)),
                    mainline_trade_alive=bool(lr.get("mainline_trade_alive", False)),
                    fade_risk_score=float(lr.get("fade_risk_score")) if lr.get("fade_risk_score") is not None else None,
                    broad_market_regime=str(regime.get("broad_market_regime") or ""),
                    short_term_sentiment=str(regime.get("short_term_sentiment") or ""),
                    mainline_environment=str(regime.get("mainline_environment") or ""),
                    market_structure=str(regime.get("market_structure") or ""),
                    trade_mode=str(regime.get("trade_mode") or "no_trade"),
                    allow_trade=bool(regime.get("allow_trade", False)),
                    position_limit=float(regime.get("position_limit") or 0),
                    strong_pool_count=strong_by_ml.get(mid, 0),
                    d1_count=d1_by_ml.get(mid, 0),
                    focus_count=focus_by_ml.get(mid, 0),
                    layer_c_subject_keys_json=pdv2.get("diagnostics", {}).get("layer_c_subject_keys", []),
                    mainline_filtered_subject_keys_json=pdv2.get("diagnostics", {}).get("mainline_filtered_subject_keys", []),
                    missing_registry_subject_keys_json=pdv2.get("diagnostics", {}).get("missing_registry_subject_keys", []),
                    no_trade_blocking_rule=blocking_rule,
                    diagnostics_json={
                        "event_count_source": "lifecycle_diagnostics",
                        "event_count_missing": (
                            lr_diag.get("event_count_1d") is None
                            and lr_diag.get("event_1d") is None
                        ),
                        "global_strong_pool_count": pdv2.get("diagnostics", {}).get("strong_pool_count", 0),
                        "global_d1_count": pdv2.get("diagnostics", {}).get("d1_count", 0),
                        "global_focus_count": pdv2.get("diagnostics", {}).get("focus_count", 0),
                        "no_trade_reasons": no_trade_reasons,
                        "layer_c_source": pdv2.get("diagnostics", {}).get("layer_c_source", ""),
                    },
                )
                rows.append(dto.to_upsert_dict())

            if rows:
                fn = getattr(self._write_port, "upsert_mainline_daily_state_rows", None)
                if callable(fn):
                    affected = await fn(rows)
                    logger.info("Persisted %d mainline_daily_state rows for %s", affected, trade_date)
        except Exception:
            logger.exception("Failed to persist mainline_daily_state")

    async def _check_post_market_readiness(self, trade_date: date) -> dict[str, Any]:
        """P1: 委托 PostMarketReadinessService 检查 5 张核心表。"""
        from stock_processing_service.application.services.post_market_readiness_service import (
            PostMarketReadinessService,
        )

        # Try to resolve pool from read_port
        pool = getattr(self._read_port, "_pool", None)
        if pool is None:
            facade = getattr(self._read_port, "_db", None)
            if facade is not None:
                pool = getattr(facade, "pool", None)
                if pool is None:
                    db_client = getattr(facade, "_db", None)
                    if db_client is not None:
                        pool = getattr(db_client, "pool", None)
                if pool is None:
                    gateway_client = getattr(facade, "_client", None)
                    pool = getattr(gateway_client, "pool", None) if gateway_client is not None else None

        service = PostMarketReadinessService(pool=pool)
        result = await service.check(trade_date)
        return result.to_dict()

    @staticmethod
    async def _build_theme_context_map(
        trade_date: date,
        report_context: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """按 subject_key 统一 JOIN cycles + capital_flow + stock_facts。

        主题宇宙 = cycles.keys() + capital 中匹配的 key。
        stock_facts 只能 enrich，不能反向扩张主题宇宙。
        """
        cycles = (
            report_context.get("cycles")
            or report_context.get("cycle_rows")
            or []
        )
        capital_rows = (
            report_context.get("capital_flow")
            or report_context.get("theme_capital_flow")
            or []
        )
        stock_facts = (
            report_context.get("stock_facts")
            or report_context.get("leader_stocks")
            or []
        )

        # 索引
        cycle_by_sk: dict[str, dict[str, Any]] = {}
        for c in cycles:
            sk = str((c or {}).get("subject_key") or "").strip()
            if sk:
                cycle_by_sk[sk] = dict(c or {})

        capital_by_sk: dict[str, dict[str, Any]] = {}
        for cap in capital_rows:
            sk = str((cap or {}).get("subject_key") or "").strip()
            if sk:
                capital_by_sk[sk] = dict(cap or {})

        stock_facts_by_sk: dict[str, list[dict[str, Any]]] = {}
        for sf in stock_facts:
            sk = str((sf or {}).get("subject_key") or "").strip()
            if sk:
                stock_facts_by_sk.setdefault(sk, []).append(dict(sf or {}))

        # 主题宇宙：只从 cycles + capital 确定，禁止 stock_facts 扩张
        base_sks: set[str] = set()
        base_sks.update(cycle_by_sk.keys())
        base_sks.update(capital_by_sk.keys())
        if not base_sks:
            # 兜底：取 theme_rows / themes / main_themes
            theme_rows = (
                report_context.get("theme_rows")
                or report_context.get("themes")
                or report_context.get("main_themes")
                or report_context.get("theme_summary")
                or []
            )
            for row in theme_rows:
                sk = str((row or {}).get("subject_key") or "").strip()
                if sk:
                    base_sks.add(sk)

        result: dict[str, dict[str, Any]] = {}
        for sk in base_sks:
            cycle = cycle_by_sk.get(sk, {})
            sf_list = stock_facts_by_sk.get(sk, [])
            sf_list.sort(
                key=lambda x: float(x.get("leader_composite_score") or 0),
                reverse=True,
            )
            result[sk] = {
                "subject_key": sk,
                "cycle": cycle,
                "capital": capital_by_sk.get(sk, {}),
                "stock_facts": sf_list,
            }

        return result

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """安全 bool 转换：处理数据库返回的字符串 'false'、'False'、'0' 等。"""
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "是"}

    @staticmethod
    def _build_theme_reviews(
        theme_context_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """从 theme_context_map 生成结构化 theme_reviews[]，不复用字符串拼接。"""
        reviews: list[dict[str, Any]] = []
        for sk, ctx in theme_context_map.items():
            cycle = ctx.get("cycle") or {}
            capital = ctx.get("capital") or {}
            sf_list = ctx.get("stock_facts") or []

            theme_name = (
                str(cycle.get("theme_name") or "").strip()
                or str((sf_list[0] or {}).get("theme_name") or "").strip()
                or sk
            )

            leader_stocks = []
            for sf in sf_list[:5]:
                leader_stocks.append({
                    "stock_id": str(sf.get("stock_id") or ""),
                    "stock_name": str(sf.get("stock_name") or ""),
                    "leader_composite_score": float(sf.get("leader_composite_score") or 0),
                    "leader_capital_score": float(sf.get("leader_capital_score") or 0),
                    "pct_chg": float(sf.get("pct_chg") or 0),
                })

            mainline_strength_score = float(
                cycle.get("mainline_strength_score")
                or cycle.get("state_strength_score")
                or 0
            )
            fade_risk_score = float(cycle.get("fade_risk_score") or 0)
            final_cycle_state = str(cycle.get("final_cycle_state") or "")

            if mainline_strength_score >= 70:
                strength_label = "STRONG"
            elif mainline_strength_score >= 40:
                strength_label = "MEDIUM"
            else:
                strength_label = "WEAK"

            cycle_joined = bool(cycle)

            # P3-5: 从 capital 提取资金流字段
            total_inflow = float(
                capital.get("main_net_inflow_sum")
                or capital.get("total_inflow")
                or 0
            )
            leader_inflow = float(
                capital.get("leader_main_net_inflow")
                or capital.get("leader_inflow")
                or 0
            )
            theme_kline = (
                str(capital.get("capital_focus_score") or "")
                or str(capital.get("final_cycle_state") or "")
                or str(cycle.get("final_cycle_state") or "")
            )

            reviews.append({
                "subject_key": sk,
                "theme_name": theme_name,
                "theme_stage": final_cycle_state,
                "theme_strength": strength_label,
                "mainline_strength_score": mainline_strength_score,
                "fade_risk_score": fade_risk_score,
                "final_cycle_state": final_cycle_state,
                "final_mainline_alive": BuildPostMarketRecapJob._to_bool(
                    cycle.get("final_mainline_alive")
                ),
                "capital_validation": "NEUTRAL",
                "total_inflow": total_inflow,
                "leader_inflow": leader_inflow,
                "theme_kline": theme_kline,
                "leader_stocks": leader_stocks,
                "event_chain": [],
                "action_advice": "",
                "conclusion": "",
                "diagnostics": {
                    "cycle_joined": cycle_joined,
                    "capital_joined": bool(capital),
                    "capital_keys": sorted(list(capital.keys())) if capital else [],
                    "leader_count": len(leader_stocks),
                },
            })

        # 排序：有 cycle > 无 cycle，再按主线强度降序
        reviews.sort(
            key=lambda x: (
                not x["diagnostics"]["cycle_joined"],
                -float(x.get("mainline_strength_score") or 0),
                -len(x.get("leader_stocks") or []),
                x.get("subject_key") or "",
            )
        )

        # 硬限制
        return reviews[: BuildPostMarketRecapJob.MAX_THEME_REVIEWS]

    @staticmethod
    def _build_theme_review_coverage(
        theme_context_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """生成 diagnostics.coverage 统计。"""
        total = len(theme_context_map)
        cycle_joined = sum(1 for ctx in theme_context_map.values() if ctx.get("cycle"))
        missing_sks = [
            sk for sk, ctx in theme_context_map.items()
            if not ctx.get("cycle")
        ]
        return {
            "theme_count": total,
            "cycle_joined_count": cycle_joined,
            "missing_cycle_subject_keys": missing_sks,
            "snapshot_status": "partial" if missing_sks else "complete",
        }

    async def _build_strong_stock_reviews(self, trade_date: date) -> list[dict]:
        """P3-5: 从 strong_stock_watch_history 生成结构化强势股分层。"""
        rows: list[Any] = []
        pool = None
        # Resolve pool from read_port
        pool_direct = getattr(self._read_port, "_pool", None)
        if pool_direct:
            pool = pool_direct
        else:
            facade = getattr(self._read_port, "_db", None)
            db_client = getattr(facade, "_db", None) if facade else None
            pool = getattr(db_client, "pool", None) if db_client else None
        if pool is None:
            rows = []
        if not rows:
            view_rows_fn = getattr(self._read_port, "get_strong_stock_watch_view_rows", None)
            if not callable(view_rows_fn):
                return []
            try:
                rows = await view_rows_fn(
                    end_date=trade_date,
                    window_days=0,
                    include_removed=True,
                    latest_per_stock=False,
                    limit=120,
                )
            except TypeError:
                rows = await view_rows_fn(trade_date)
            return self._normalize_strong_stock_reviews(rows)

        sql = """
        SELECT
            h.stock_id,
            h.stock_name,
            h.subject_key,
            h.theme_name,
            h.watch_status,
            COALESCE(h.watch_score, 0) AS watch_score,
            h.support_type,
            COALESCE(h.support_score, 0) AS support_score,
            h.pool_entry_type,
            h.cycle_state,
            COALESCE(m.money_flow_tier, '') AS money_flow_tier,
            COALESCE(m.role_enhanced, '') AS role_enhanced,
            COALESCE(m.main_net_inflow, 0) AS main_net_inflow,
            COALESCE(p.position_label, '') AS position_label,
            COALESCE(x.pattern_labels, '[]'::jsonb) AS pattern_labels,
            COALESCE(s.pct_chg, 0) AS pct_chg,
            CASE
                WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 18
                THEN NULLIF(s.raw_json->>18, '')::numeric
                ELSE 0
            END AS turnover_rate,
            CASE
                WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 17
                THEN NULLIF(s.raw_json->>17, '')::numeric
                ELSE 0
            END AS volume_ratio
        FROM strong_stock_watch_history h
        LEFT JOIN money_flow_enhanced m
          ON m.trade_date = h.trade_date
         AND m.subject_key = h.subject_key
         AND split_part(m.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        LEFT JOIN stock_position_judgement p
          ON p.trade_date = h.trade_date
         AND split_part(p.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        LEFT JOIN stock_pattern_judgement x
          ON x.trade_date = h.trade_date
         AND split_part(x.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        LEFT JOIN subject_stock_daily_snapshot s
          ON s.trade_date = h.trade_date
         AND s.subject_key = h.subject_key
         AND split_part(s.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        WHERE h.trade_date = $1::date
        ORDER BY h.watch_score DESC NULLS LAST
        LIMIT 120
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return self._normalize_strong_stock_reviews(rows)

    @staticmethod
    def _normalize_strong_stock_reviews(rows: list[Any]) -> list[dict]:
        results: list[dict] = []
        for raw in rows or []:
            r = dict(raw or {})
            pl = r.get("pattern_labels")
            if isinstance(pl, str):
                try:
                    import json as _json
                    pl = _json.loads(pl)
                except Exception:
                    pl = []
            if isinstance(pl, dict):
                pl = list(pl.values())
            results.append({
                "stock_code": r.get("stock_id") or r.get("stock_code") or "",
                "stock_name": r.get("stock_name") or "",
                "subject_key": r.get("subject_key") or "",
                "theme_name": r.get("theme_name") or r.get("subject_name") or r.get("subject_key") or "",
                "role": r.get("pool_entry_type") or r.get("cycle_state") or r.get("role") or "",
                "watch_status": r.get("watch_status") or "",
                "watch_score": float(r.get("watch_score") or 0),
                "strong_grade": r.get("strong_grade") or "",
                "support_type": r.get("support_type") or "",
                "support_score": float(r.get("support_score") or 0),
                "money_flow_tier": r.get("money_flow_tier") or "",
                "role_enhanced": r.get("role_enhanced") or "",
                "main_net_inflow": float(r.get("main_net_inflow") or 0),
                "pct_chg": float(r.get("pct_chg") or 0),
                "turnover_rate": float(r.get("turnover_rate") or 0),
                "volume_ratio": float(r.get("volume_ratio") or 0),
                "position_label": r.get("position_label") or "",
                "pattern_labels": pl if isinstance(pl, list) else [],
                "rationale": r.get("rationale") or "",
            })
        return results

    @staticmethod
    def _build_strong_hotspot_subjects(strong_stock_reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hotspots: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in strong_stock_reviews or []:
            subject_key = str(row.get("subject_key") or "").strip()
            if not subject_key or subject_key in seen:
                continue
            seen.add(subject_key)
            hotspots.append({
                "subject_key": subject_key,
                "theme_name": str(row.get("theme_name") or subject_key),
                "stock_id": str(row.get("stock_code") or row.get("stock_id") or ""),
                "stock_name": str(row.get("stock_name") or ""),
                "watch_score": row.get("watch_score"),
                "support_score": row.get("support_score"),
                "watch_status": row.get("watch_status"),
                "pool_entry_type": row.get("role") or "",
                "cycle_state": row.get("cycle_state") or "",
                "source": "strong_stock_reviews",
            })
        return hotspots

    @staticmethod
    def _build_confirmed_mainline_hotspots(active_mainline_universe: dict[str, Any]) -> list[dict[str, Any]]:
        hotspots: list[dict[str, Any]] = []
        for row in active_mainline_universe.get("active_mainlines") or []:
            if not isinstance(row, dict):
                continue
            subject_key = str(row.get("canonical_subject_key") or row.get("subject_key") or "").strip()
            if not subject_key:
                continue
            hotspots.append({
                "subject_key": subject_key,
                "theme_name": str(row.get("mainline_name") or row.get("theme_name") or subject_key),
                "stock_id": str(row.get("stock_id") or ""),
                "stock_name": str(row.get("stock_name") or ""),
                "watch_score": row.get("mainline_strength_score"),
                "support_score": row.get("mainline_strength_score"),
                "watch_status": "confirmed_mainline",
                "pool_entry_type": "formal",
                "cycle_state": str(row.get("state") or row.get("final_cycle_state") or "confirmed"),
                "source": "confirmed_mainline",
            })
        return hotspots

    @staticmethod
    def _merge_hotspot_subjects(
        existing_hotspots: list[dict[str, Any]],
        confirmed_hotspots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in list(confirmed_hotspots) + list(existing_hotspots):
            if not isinstance(row, dict):
                continue
            subject_key = str(row.get("subject_key") or "").strip()
            if not subject_key or subject_key in seen:
                continue
            seen.add(subject_key)
            merged.append(dict(row))
        return merged

    @staticmethod
    def _build_capital_reviews(dragon_tiger_rows: list[dict]) -> list[dict]:
        """P2-B-0: 从 report_context dragon_tiger 映射为 capital_reviews。"""
        results: list[dict] = []
        for row in dragon_tiger_rows:
            try:
                results.append({
                    "stock_code": str(row.get("stock_id") or ""),
                    "stock_name": str(row.get("stock_name") or ""),
                    "net_buy_amount": float(row.get("net_amount") or 0),
                    "seat_type": "INSTITUTION" if (float(row.get("institution_net_buy") or 0) > 0) else "HOT_MONEY",
                    "related_theme": str(row.get("theme_name") or ""),
                    "ai_comment": str(row.get("reason") or "")[:200],
                })
            except Exception:
                continue
        return results


# ── Mainline Discovery helpers (PR-7) ──

def _theme_name_for_sk(candidates: list, sk: str) -> str:
    for c in candidates:
        if isinstance(c, dict) and str(c.get("subject_key", "")) == sk:
            return str(c.get("theme_name", sk))
    return sk


def _count_non_null_scores(logic_by_sk: dict) -> int:
    count = 0
    for ev in logic_by_sk.values():
        if isinstance(ev, dict) and ev.get("logic_score") is not None:
            count += 1
    return count


def _count_non_null_market(market_by_sk: dict) -> int:
    count = 0
    for ma in market_by_sk.values():
        if isinstance(ma, dict) and ma.get("market_acceptance_score") is not None:
            count += 1
    return count
