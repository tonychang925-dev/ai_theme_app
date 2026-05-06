from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.identity_decider import IdentityDecider
from stock_processing_service.domain.services.identity_llm_review_service import IdentityLLMReviewService
from stock_processing_service.domain.services.identity_rule_engine import IdentityRuleEngine, IdentityRuleInput
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
        llm_review_service: IdentityLLMReviewService | None = None,
        decider: IdentityDecider | None = None,
        rule_engine: IdentityRuleEngine | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._llm_review_service = llm_review_service or IdentityLLMReviewService()
        self._decider = decider or IdentityDecider()
        self._rule_engine = rule_engine or IdentityRuleEngine()

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

    @classmethod
    def _identity_rule_input_from_row(cls, row: dict[str, Any]) -> IdentityRuleInput:
        return IdentityRuleInput(
            subject_key=str(row.get("subject_key") or ""),
            subject_name=str(row.get("theme_name") or row.get("subject_name") or row.get("subject_key") or ""),
            heat_latest=cls._d(row.get("heat_latest")),
            avg_heat_5d=cls._d(row.get("avg_heat_5d")),
            hot_days_5d=int(row.get("hot_days_5d") or 0),
            active_days_10d=int(row.get("active_days_10d") or 0),
            active_days_20d=int(row.get("active_days_20d") or 0),
            his_pct_chg_30d=list(row.get("his_pct_chg_30d") or []),
            his_pct_chg_latest=cls._d(row.get("his_pct_chg_latest")),
            strong_event_count_7d=int(row.get("strong_event_count_7d") or 0),
            event_count_3d=int(row.get("event_count_3d") or 0),
            event_count_7d=int(row.get("event_count_7d") or 0),
            event_recency_days=int(row.get("event_recency_days") or 99),
            event_strength_score=cls._d(row.get("event_strength_score")),
            event_continuity_score=cls._d(row.get("event_continuity_score")),
            board_stock_count=int(row.get("board_stock_count") or 0),
            limit_up_count=int(row.get("limit_up_count") or 0),
            front_row_strength_score=cls._d(row.get("front_row_strength_score")),
            front_row_alive_ratio=cls._d(row.get("front_row_alive_ratio")),
            above_ma10=bool(row.get("above_ma10") or False),
            above_ma20=bool(row.get("above_ma20") or False),
            theme_support_score=cls._d(row.get("theme_support_score")),
            theme_ret_10d=cls._d(row.get("theme_ret_10d")),
            board_boom_days_5d=int(row.get("board_boom_days_5d") or 0),
            net_inflow_sum_5d=cls._d(row.get("net_inflow_sum_5d")),
            net_inflow_days_5d=int(row.get("net_inflow_days_5d") or 0),
        )


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

        # ── Single engine path: IdentityRuleEngine → IdentityLLMReviewService → IdentityDecider ──

        raw_pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        pool_rows = self._normalize_rows(raw_pool_rows)
        subject_keys = sorted({row.subject_key for row in pool_rows})
        raw_rule_inputs = await self._read_port.get_mainline_identity_rule_inputs(
            trade_date=trade_date,
            subject_keys=subject_keys,
        ) if subject_keys else []
        rule_inputs_by_subject = {
            str(row.get("subject_key") or ""): dict(row)
            for row in raw_rule_inputs
            if str(row.get("subject_key") or "").strip()
        }

        identity_registry_rows: list[dict[str, Any]] = []
        review_queue_rows: list[dict[str, Any]] = []

        grouped: dict[str, list[Any]] = {}
        for row in pool_rows:
            grouped.setdefault(row.subject_key, []).append(row)

        for subject_key, rows in grouped.items():
            rule_row = rule_inputs_by_subject.get(subject_key)
            if not rule_row:
                raise RuntimeError(f"Layer A missing rule input from database_service gateway: trade_date={trade_date}, subject_key={subject_key}")
            rule_input = self._identity_rule_input_from_row(rule_row)
            subject_name = rule_input.subject_name
            rule = self._rule_engine.evaluate(rule_input)
            llm_verdict = self._llm_review_service.review_with_rule(
                composite_score=rule.composite_score,
                one_day_tour_flag=rule.one_day_tour_flag,
                logic_ok=rule.logic_ok,
                market_ok=rule.market_ok,
                rule_is_main_theme=rule.rule_is_main_theme,
            )
            decision = self._decider.decide(
                composite_score=rule.composite_score,
                llm_verdict=llm_verdict.verdict,
                one_day_tour_flag=rule.one_day_tour_flag,
                logic_ok=rule.logic_ok,
                rule_is_main_theme=rule.rule_is_main_theme,
                platform_breakout_flag=rule.platform_breakout_flag,
            )

            identity_row = {
                "trade_date": trade_date.isoformat(),
                "subject_key": subject_key,
                "subject_name": subject_name,
                "logic_score": str(rule.logic_score),
                "market_score": str(rule.market_score),
                "composite_score": str(rule.composite_score),
                "one_day_tour_flag": rule.one_day_tour_flag,
                "continuity_signal": "weak_continuity" if rule.one_day_tour_flag else "normal",
                "logic_ok": rule.logic_ok,
                "market_ok": rule.market_ok,
                "rule_is_main_theme": rule.rule_is_main_theme,
                "is_main_theme": decision.identity_status == "confirmed",
                "rule_reasons": rule.reasons,
                # Keep field for backward compatibility, but bind to the
                # same rule-engine composite to avoid dual scoring drift.
                "legacy_composite_score": str(rule.composite_score),
                "llm_verdict": llm_verdict.verdict,
                "llm_reason": llm_verdict.reason,
                "identity_status": decision.identity_status,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "source_trace_id": trace_id,
            }

            identity_registry_rows.append(identity_row)

            if identity_row["identity_status"] == "review_pending":
                review_queue_rows.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "subject_key": subject_key,
                        "subject_name": subject_name,
                        "reason": decision.reason,
                        "llm_confidence": str(llm_verdict.confidence),
                        "llm_verdict": identity_row.get("llm_verdict", ""),
                        "rule_is_main_theme": identity_row["rule_is_main_theme"],
                        "rule_reasons": identity_row["rule_reasons"],
                        "snapshot_version": snapshot_version,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    }
                )

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
                "identity_engine": "identity_rule_engine",
                "dual_run_enabled": False,
            },
            published_events=published_events,
        )
