from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from stock_processing_service.contracts.market_cognition import (
    EvidenceRef,
    HypothesisState,
)
from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecord,
    MarketThesisValidationRecordBuilder,
    VerificationFailureType,
    VerificationLabel,
)


class HypothesisEligibilityError(ValueError):
    """Raised before Dataset write when a claim is not validation eligible."""


@dataclass(frozen=True, slots=True)
class FrozenHypothesisSource:
    thesis_trade_date: str
    source_snapshot_id: str
    source_as_of: datetime
    source_knowledge_hash: str
    source_evidence_hash: str
    source_context_hash: str
    source_thesis_hash: str
    source_quality_status: str
    source_quality_score: float
    source_policy_version: str
    hypothesis: HypothesisState


@dataclass(frozen=True, slots=True)
class TodayReality:
    trade_date: str
    available_at: datetime
    evidence_hash: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ReviewerVerdict:
    reviewer_id: str
    label: VerificationLabel
    failure_type: VerificationFailureType | None
    reason: str
    outcome: str
    reviewed_at: datetime


class MarketThesisVerificationService:
    """Turns an eligible frozen hypothesis and human verdict into Ground Truth."""

    def __init__(self, *, approved_reviewer_ids: set[str]) -> None:
        self._approved_reviewer_ids = frozenset(
            reviewer_id.strip()
            for reviewer_id in approved_reviewer_ids
            if reviewer_id.strip()
        )
        if not self._approved_reviewer_ids:
            raise ValueError("approved_reviewer_ids must not be empty")

    @staticmethod
    def check_eligibility(source: FrozenHypothesisSource) -> None:
        hypothesis = source.hypothesis
        if not isinstance(hypothesis, HypothesisState):
            raise HypothesisEligibilityError(
                "only HypothesisState is validation eligible; "
                "Observation and Assessment are report-only"
            )
        if hypothesis.status != "VALIDATING":
            raise HypothesisEligibilityError(
                "eligible hypothesis status must be VALIDATING"
            )
        if not hypothesis.statement.strip():
            raise HypothesisEligibilityError(
                "eligible hypothesis statement is required"
            )
        if not hypothesis.hypothesis_id.strip():
            raise HypothesisEligibilityError(
                "eligible hypothesis id is required"
            )
        try:
            source_date = date.fromisoformat(source.thesis_trade_date)
            deadline = date.fromisoformat(hypothesis.deadline)
        except ValueError as exc:
            raise HypothesisEligibilityError(
                "eligible hypothesis dates must use YYYY-MM-DD"
            ) from exc
        if deadline <= source_date:
            raise HypothesisEligibilityError(
                "eligible hypothesis deadline must be after source trade date"
            )
        if not 0.0 <= float(hypothesis.probability) <= 1.0:
            raise HypothesisEligibilityError(
                "eligible hypothesis prediction_probability must be between 0 and 1"
            )
        if not any(item.strip() for item in hypothesis.expected_observations):
            raise HypothesisEligibilityError(
                "eligible hypothesis expected observations are required"
            )
        if not any(item.strip() for item in hypothesis.falsifiers):
            raise HypothesisEligibilityError(
                "eligible hypothesis falsifiers are required"
            )
        if not hypothesis.evidence_refs or any(
            not (
                ref.ref_id.strip()
                and ref.source_module.strip()
                and ref.source_path.strip()
                and ref.source_snapshot_id.strip()
            )
            for ref in hypothesis.evidence_refs
        ):
            raise HypothesisEligibilityError(
                "eligible hypothesis EvidenceRefs are required"
            )
        if not source.source_snapshot_id.strip():
            raise HypothesisEligibilityError(
                "eligible hypothesis source snapshot is required"
            )
        if not source.source_policy_version.strip():
            raise HypothesisEligibilityError(
                "eligible hypothesis policy version is required"
            )
        if not source.source_quality_status.strip():
            raise HypothesisEligibilityError(
                "eligible hypothesis source quality status is required"
            )
        if source.source_quality_status.strip().upper() == "BLOCKED":
            raise HypothesisEligibilityError(
                "eligible hypothesis source quality must not be BLOCKED"
            )
        if not 0.0 <= float(source.source_quality_score) <= 1.0:
            raise HypothesisEligibilityError(
                "eligible hypothesis source quality score must be between 0 and 1"
            )
        source_hashes = (
            source.source_knowledge_hash,
            source.source_evidence_hash,
            source.source_context_hash,
            source.source_thesis_hash,
        )
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in source_hashes
        ):
            raise HypothesisEligibilityError(
                "eligible hypothesis source hashes must be sha256 digests"
            )

    def verify(
        self,
        source: FrozenHypothesisSource,
        reality: TodayReality,
        verdict: ReviewerVerdict | None,
    ) -> MarketThesisValidationRecord:
        self.check_eligibility(source)
        if verdict is None or not isinstance(verdict, ReviewerVerdict):
            raise ValueError("explicit ReviewerVerdict is required")
        if verdict.reviewer_id not in self._approved_reviewer_ids:
            raise ValueError(
                f"approved reviewer is required: {verdict.reviewer_id}"
            )
        try:
            reality_date = date.fromisoformat(reality.trade_date)
            deadline = date.fromisoformat(source.hypothesis.deadline)
        except ValueError as exc:
            raise ValueError("reality and deadline dates must use YYYY-MM-DD") from exc
        if reality_date < deadline:
            raise ValueError("reality cannot be verified before hypothesis deadline")
        if not reality.evidence_refs or any(
            not ref.ref_id.strip() for ref in reality.evidence_refs
        ):
            raise ValueError("Today Reality EvidenceRefs are required")

        refs = tuple(
            dict.fromkeys(
                ref.ref_id
                for ref in (*source.hypothesis.evidence_refs, *reality.evidence_refs)
            )
        )
        return MarketThesisValidationRecordBuilder.build(
            thesis_trade_date=source.thesis_trade_date,
            verification_trade_date=reality.trade_date,
            source_hypothesis_id=source.hypothesis.hypothesis_id,
            source_hypothesis_as_of=source.source_as_of,
            hypothesis_deadline=source.hypothesis.deadline,
            reality_available_at=reality.available_at,
            verified_at=verdict.reviewed_at,
            source_knowledge_hash=source.source_knowledge_hash,
            source_evidence_hash=source.source_evidence_hash,
            source_context_hash=source.source_context_hash,
            source_thesis_hash=source.source_thesis_hash,
            reality_evidence_hash=reality.evidence_hash,
            prediction_probability=source.hypothesis.probability,
            source_quality_score=source.source_quality_score,
            source_policy_version=source.source_policy_version,
            label=verdict.label,
            failure_type=verdict.failure_type,
            verification_reason=verdict.reason,
            outcome=verdict.outcome,
            evidence_refs=refs,
        )
        if source.source_as_of.date() != source_date:
            raise HypothesisEligibilityError(
                "eligible hypothesis source_as_of must match source trade date"
            )
