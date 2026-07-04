from __future__ import annotations

from copy import deepcopy
from datetime import datetime
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


class MarketCognitionReplay:
    """Side-effect-free Phase 0 replay orchestrator."""

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
