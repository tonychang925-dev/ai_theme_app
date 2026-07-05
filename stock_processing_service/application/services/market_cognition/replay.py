from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stock_processing_service.application.services.market_cognition.cognition import (
    Phase0CognitionPipeline,
)
from stock_processing_service.application.services.market_cognition.knowledge_evidence import (
    MarketEvidenceAdapter,
    MarketKnowledgeBundleBuilder,
)
from stock_processing_service.contracts.market_cognition import (
    ReplayResult,
    canonical_hash,
)

_CHINA_TZ = timezone(__import__("datetime").timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class BacktestPendingRecord:
    """Historical backtest entry awaiting human Reviewer Verdict.

    Created by MarketCognitionReplay.run_pair().
    Consumed by MarketThesisVerificationService.verify().
    """
    record_id: str
    validation_mode: str
    thesis_trade_date: str
    verification_trade_date: str
    hypothesis_id: str
    hypothesis_statement: str
    prediction_probability: float
    source_quality_score: float
    source_policy_version: str
    source_knowledge_hash: str
    source_evidence_hash: str
    source_context_hash: str
    source_thesis_hash: str
    reality_evidence_hash: str
    hypothesis_deadline: str
    frozen_at: str


def _document(payload: dict[str, Any]) -> dict[str, Any]:
    recap_doc = payload.get("recap_doc")
    return recap_doc if isinstance(recap_doc, dict) else payload


def _decision_hash(payload: dict[str, Any]) -> str:
    document = _document(payload)
    decision_view = {
        "engine_summary": document.get("engine_summary"),
        "decision": document.get("decision"),
        "trade_conclusion": document.get("trade_conclusion"),
    }
    return canonical_hash(decision_view)


def build_pairs(
    snapshots: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Build consecutive trading day pairs from sorted snapshots."""
    sorted_s = sorted(snapshots, key=lambda s: str(s["trade_date"]))
    return [
        (sorted_s[i], sorted_s[i + 1])
        for i in range(len(sorted_s) - 1)
        if str(sorted_s[i]["trade_date"]) != str(sorted_s[i + 1]["trade_date"])
    ]


class MarketCognitionReplay:
    """Side-effect-free Phase 0 replay orchestrator.

    Also provides run_pair() for historical cognitive backtest:
    Hypothesis from day D, Reality from day D+1 (Time Travel Rule).
    """

    # ── single-day replay ──

    @classmethod
    def run(
        cls,
        payload: dict[str, Any],
        trade_date: str,
        *,
        as_of: datetime | None = None,
    ) -> ReplayResult:
        input_copy = deepcopy(payload)
        decision_before = _decision_hash(input_copy)

        try:
            bundle = MarketKnowledgeBundleBuilder.build(
                input_copy,
                trade_date,
                as_of=as_of,
            )
        except (TypeError, ValueError) as exc:
            return ReplayResult(
                status="failed",
                failed_stage="knowledge",
                layer_hashes={},
                thesis=None,
                decision_unchanged=True,
                diagnostics=(f"knowledge_error:{exc}",),
            )

        try:
            evidence = MarketEvidenceAdapter.build(bundle)
        except (TypeError, ValueError) as exc:
            return ReplayResult(
                status="failed",
                failed_stage="evidence",
                layer_hashes={"knowledge": bundle.content_hash},
                thesis=None,
                decision_unchanged=_decision_hash(input_copy) == decision_before,
                diagnostics=(f"evidence_error:{exc}",),
            )

        try:
            cognition = Phase0CognitionPipeline.build(evidence)
        except (TypeError, ValueError) as exc:
            return ReplayResult(
                status="failed",
                failed_stage="cognition",
                layer_hashes={
                    "knowledge": bundle.content_hash,
                    "evidence": evidence.content_hash,
                },
                thesis=None,
                decision_unchanged=_decision_hash(input_copy) == decision_before,
                diagnostics=(f"cognition_error:{exc}",),
            )

        thesis = cognition.thesis
        ready = thesis.status == "ready"
        diagnostics = list(cognition.diagnostics)
        if evidence.evidence_ref_coverage < 1.0:
            diagnostics.append("incomplete_evidence_refs")
        if thesis.unsupported_claim_count:
            diagnostics.append("unsupported_claims")

        return ReplayResult(
            status="ready" if ready else "unavailable",
            failed_stage=None if ready else "thesis",
            layer_hashes={
                "knowledge": bundle.content_hash,
                "evidence": evidence.content_hash,
                "context": cognition.context.content_hash,
                "cognition": cognition.cognition.content_hash,
                "thesis": thesis.content_hash,
            },
            thesis=thesis if ready else None,
            decision_unchanged=(
                input_copy == payload
                and _decision_hash(input_copy) == decision_before
            ),
            diagnostics=tuple(diagnostics),
        )

    # ── pair replay (historical cognitive backtest) ──

    @classmethod
    def run_pair(
        cls,
        day_d: dict[str, Any],
        day_d_next: dict[str, Any],
    ) -> BacktestPendingRecord | None:
        """Process one (D, D+1) pair for historical cognitive backtest.

        Time Travel Rule: Hypothesis from day D ONLY, Reality from D+1 ONLY.
        Reuses existing MarketKnowledgeBundleBuilder, MarketEvidenceAdapter,
        and Phase0CognitionPipeline — same infrastructure as run().
        """
        trade_date_d = str(day_d["trade_date"])
        trade_date_next = str(day_d_next["trade_date"])

        # Day D: full cognition pipeline (same as run() but also captures CognitionState)
        try:
            bundle_d = MarketKnowledgeBundleBuilder.build(day_d["payload"], trade_date_d)
            evidence_d = MarketEvidenceAdapter.build(bundle_d)
            cognition_result = Phase0CognitionPipeline.build(evidence_d)
        except (TypeError, ValueError):
            return None

        hypotheses = cognition_result.cognition.hypotheses
        if not hypotheses:
            return None
        primary = hypotheses[0]

        # Day D+1: evidence only (reuses existing MarketKnowledgeBundleBuilder)
        try:
            bundle_next = MarketKnowledgeBundleBuilder.build(day_d_next["payload"], trade_date_next)
            evidence_next = MarketEvidenceAdapter.build(bundle_next)
            reality_hash = getattr(evidence_next, "content_hash", "") or canonical_hash({"reality": trade_date_next})
        except (TypeError, ValueError):
            reality_hash = ""

        return BacktestPendingRecord(
            record_id=f"hbt:{trade_date_d}:{trade_date_next}:{primary.hypothesis_id}",
            validation_mode="historical",
            thesis_trade_date=trade_date_d,
            verification_trade_date=trade_date_next,
            hypothesis_id=primary.hypothesis_id,
            hypothesis_statement=primary.statement,
            prediction_probability=primary.probability,
            source_quality_score=0.90,
            source_policy_version="m8_phase0_cognition.v1",
            source_knowledge_hash=getattr(bundle_d, "content_hash", ""),
            source_evidence_hash=getattr(evidence_d, "content_hash", ""),
            source_context_hash=getattr(cognition_result.context, "content_hash", ""),
            source_thesis_hash=getattr(cognition_result.thesis, "content_hash", ""),
            reality_evidence_hash=reality_hash,
            hypothesis_deadline=primary.deadline,
            frozen_at=datetime.now(_CHINA_TZ).isoformat(),
        )
