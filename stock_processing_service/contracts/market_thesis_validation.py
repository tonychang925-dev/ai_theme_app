from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from stock_processing_service.contracts.market_cognition import canonical_hash


class VerificationLabel(str, Enum):
    YES = "YES"
    NO = "NO"
    PARTIAL = "PARTIAL"
    UNVERIFIABLE = "UNVERIFIABLE"


class VerificationFailureType(str, Enum):
    WRONG_DIRECTION = "WRONG_DIRECTION"
    WRONG_TIMING = "WRONG_TIMING"
    WRONG_THEME = "WRONG_THEME"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNEXPECTED_EVENT = "UNEXPECTED_EVENT"
    MARKET_REGIME_SHIFT = "MARKET_REGIME_SHIFT"


@dataclass(frozen=True, slots=True)
class MarketThesisValidationRecord:
    record_id: str
    schema_version: str
    thesis_trade_date: str
    verification_trade_date: str
    source_hypothesis_id: str
    source_hypothesis_as_of: datetime
    hypothesis_deadline: str
    reality_available_at: datetime
    verified_at: datetime
    source_knowledge_hash: str
    source_evidence_hash: str
    source_context_hash: str
    source_thesis_hash: str
    reality_evidence_hash: str
    prediction_probability: float
    source_quality_score: float
    source_policy_version: str
    label: VerificationLabel
    failure_type: VerificationFailureType | None
    verification_reason: str
    outcome: str
    evidence_refs: tuple[str, ...]
    record_hash: str


class MarketThesisValidationRecordBuilder:
    SCHEMA_VERSION = "market_thesis_validation.v1"
    _HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def build(
        cls,
        *,
        thesis_trade_date: str,
        verification_trade_date: str,
        source_hypothesis_id: str,
        source_hypothesis_as_of: datetime,
        hypothesis_deadline: str,
        reality_available_at: datetime,
        verified_at: datetime,
        source_knowledge_hash: str,
        source_evidence_hash: str,
        source_context_hash: str,
        source_thesis_hash: str,
        reality_evidence_hash: str,
        prediction_probability: float,
        source_quality_score: float,
        source_policy_version: str,
        label: VerificationLabel,
        failure_type: VerificationFailureType | None,
        verification_reason: str,
        outcome: str,
        evidence_refs: tuple[str, ...],
    ) -> MarketThesisValidationRecord:
        if not isinstance(label, VerificationLabel):
            raise ValueError("label must be VerificationLabel")
        if failure_type is not None and not isinstance(
            failure_type, VerificationFailureType
        ):
            raise ValueError("failure_type must be VerificationFailureType")
        if label is VerificationLabel.YES and failure_type is not None:
            raise ValueError("YES verification must not have failure_type")
        if label in {
            VerificationLabel.NO,
            VerificationLabel.PARTIAL,
            VerificationLabel.UNVERIFIABLE,
        } and failure_type is None:
            raise ValueError(f"{label.value} verification requires failure_type")
        if (
            label is VerificationLabel.UNVERIFIABLE
            and failure_type is not VerificationFailureType.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError(
                "UNVERIFIABLE requires failure_type=INSUFFICIENT_EVIDENCE"
            )
        if not source_hypothesis_id.strip():
            raise ValueError("source_hypothesis_id is required")
        try:
            deadline = date.fromisoformat(hypothesis_deadline)
        except ValueError as exc:
            raise ValueError("hypothesis_deadline must be valid YYYY-MM-DD") from exc
        if deadline <= source_hypothesis_as_of.date():
            raise ValueError(
                "hypothesis_deadline must be after source hypothesis as_of"
            )
        if source_hypothesis_as_of >= reality_available_at:
            raise ValueError(
                "future data leak: source hypothesis as_of must be before reality available_at"
            )
        if verified_at < reality_available_at:
            raise ValueError("verified_at must not precede reality available_at")
        if not 0.0 <= float(prediction_probability) <= 1.0:
            raise ValueError("prediction_probability must be between 0 and 1")
        if not 0.0 <= float(source_quality_score) <= 1.0:
            raise ValueError("source_quality_score must be between 0 and 1")
        if not source_policy_version.strip():
            raise ValueError("source_policy_version is required")
        if not verification_reason.strip():
            raise ValueError("verification_reason is required")
        if not outcome.strip():
            raise ValueError("outcome is required")
        normalized_refs = tuple(
            dict.fromkeys(ref.strip() for ref in evidence_refs if ref.strip())
        )
        if not normalized_refs:
            raise ValueError("evidence_refs are required")
        hashes = {
            "source_knowledge_hash": source_knowledge_hash,
            "source_evidence_hash": source_evidence_hash,
            "source_context_hash": source_context_hash,
            "source_thesis_hash": source_thesis_hash,
            "reality_evidence_hash": reality_evidence_hash,
        }
        for name, value in hashes.items():
            if not cls._HASH_PATTERN.fullmatch(value):
                raise ValueError(f"{name} must be a sha256 hex digest")

        canonical = {
            "schema_version": cls.SCHEMA_VERSION,
            "thesis_trade_date": thesis_trade_date,
            "verification_trade_date": verification_trade_date,
            "source_hypothesis_id": source_hypothesis_id.strip(),
            "source_hypothesis_as_of": source_hypothesis_as_of,
            "hypothesis_deadline": deadline.isoformat(),
            "reality_available_at": reality_available_at,
            "verified_at": verified_at,
            **hashes,
            "prediction_probability": float(prediction_probability),
            "source_quality_score": float(source_quality_score),
            "source_policy_version": source_policy_version.strip(),
            "label": label.value,
            "failure_type": failure_type.value if failure_type else None,
            "verification_reason": verification_reason.strip(),
            "outcome": outcome.strip(),
            "evidence_refs": normalized_refs,
        }
        record_hash = canonical_hash(canonical)
        return MarketThesisValidationRecord(
            record_id=(
                f"mtv:{thesis_trade_date}:{verification_trade_date}:"
                f"{record_hash[:16]}"
            ),
            schema_version=cls.SCHEMA_VERSION,
            thesis_trade_date=thesis_trade_date,
            verification_trade_date=verification_trade_date,
            source_hypothesis_id=source_hypothesis_id.strip(),
            source_hypothesis_as_of=source_hypothesis_as_of,
            hypothesis_deadline=deadline.isoformat(),
            reality_available_at=reality_available_at,
            verified_at=verified_at,
            source_knowledge_hash=source_knowledge_hash,
            source_evidence_hash=source_evidence_hash,
            source_context_hash=source_context_hash,
            source_thesis_hash=source_thesis_hash,
            reality_evidence_hash=reality_evidence_hash,
            prediction_probability=float(prediction_probability),
            source_quality_score=float(source_quality_score),
            source_policy_version=source_policy_version.strip(),
            label=label,
            failure_type=failure_type,
            verification_reason=verification_reason.strip(),
            outcome=outcome.strip(),
            evidence_refs=normalized_refs,
            record_hash=record_hash,
        )
