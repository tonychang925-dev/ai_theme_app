from __future__ import annotations

from datetime import datetime, timezone

import pytest

try:
    from stock_processing_service.contracts.market_thesis_validation import (
        MarketThesisValidationRecordBuilder,
        VerificationFailureType,
        VerificationLabel,
    )
except ModuleNotFoundError:
    MarketThesisValidationRecordBuilder = None
    VerificationFailureType = None
    VerificationLabel = None


def _kwargs() -> dict:
    return {
        "thesis_trade_date": "2026-07-03",
        "verification_trade_date": "2026-07-06",
        "source_thesis_id": "thesis:2026-07-03:abc",
        "source_thesis_as_of": datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc),
        "reality_available_at": datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc),
        "verified_at": datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
        "knowledge_hash": "a" * 64,
        "evidence_hash": "b" * 64,
        "context_hash": "c" * 64,
        "thesis_hash": "d" * 64,
        "confidence": 0.72,
        "verification_reason": "机器人未出现预期修复，核心载体继续走弱。",
        "outcome": "修复失败",
        "evidence_refs": ("ev:today:robot:cycle",),
    }


# TC-M8P1-T01-01
def test_same_validation_input_when_built_twice_then_record_hash_is_stable() -> None:
    assert MarketThesisValidationRecordBuilder is not None, "validation contract missing"
    kwargs = _kwargs()
    first = MarketThesisValidationRecordBuilder.build(
        **kwargs,
        label=VerificationLabel.NO,
        failure_type=VerificationFailureType.WRONG_DIRECTION,
    )
    second = MarketThesisValidationRecordBuilder.build(
        **kwargs,
        label=VerificationLabel.NO,
        failure_type=VerificationFailureType.WRONG_DIRECTION,
    )

    assert first.record_hash == second.record_hash
    assert first.schema_version == "market_thesis_validation.v1"
    assert first.evidence_refs
    assert not hasattr(first, "belief")
    assert not hasattr(first, "learning")


# TC-M8P1-T01-02
def test_no_label_without_failure_type_when_built_then_validation_fails() -> None:
    assert MarketThesisValidationRecordBuilder is not None, "validation contract missing"
    with pytest.raises(ValueError, match="failure_type"):
        MarketThesisValidationRecordBuilder.build(
            **_kwargs(),
            label=VerificationLabel.NO,
            failure_type=None,
        )


# TC-M8P1-T01-02
def test_unverifiable_with_insufficient_evidence_when_built_then_record_is_valid() -> None:
    assert MarketThesisValidationRecordBuilder is not None, "validation contract missing"
    record = MarketThesisValidationRecordBuilder.build(
        **_kwargs(),
        label=VerificationLabel.UNVERIFIABLE,
        failure_type=VerificationFailureType.INSUFFICIENT_EVIDENCE,
    )

    assert record.label is VerificationLabel.UNVERIFIABLE
    assert record.failure_type is VerificationFailureType.INSUFFICIENT_EVIDENCE


# TC-M8P1-T01-02
def test_future_reality_not_after_thesis_when_built_then_future_leak_is_rejected() -> None:
    assert MarketThesisValidationRecordBuilder is not None, "validation contract missing"
    kwargs = _kwargs()
    kwargs["reality_available_at"] = kwargs["source_thesis_as_of"]

    with pytest.raises(ValueError, match="future|available_at|as_of"):
        MarketThesisValidationRecordBuilder.build(
            **kwargs,
            label=VerificationLabel.NO,
            failure_type=VerificationFailureType.MARKET_REGIME_SHIFT,
        )
