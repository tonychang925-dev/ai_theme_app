from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecordBuilder,
    VerificationFailureType,
    VerificationLabel,
)

from stock_processing_service.application.services.market_cognition.validation_dataset import (
    MarketThesisValidationDataset,
    ValidationDatasetConflictError,
    ValidationDatasetCorruptionError,
)


def _record(
    *,
    outcome: str = "修复失败",
    source_hypothesis_id: str = "hyp:2026-07-03:robot-repair",
):
    return MarketThesisValidationRecordBuilder.build(
        thesis_trade_date="2026-07-03",
        verification_trade_date="2026-07-06",
        source_hypothesis_id=source_hypothesis_id,
        source_hypothesis_as_of=datetime(
            2026, 7, 3, 7, 30, tzinfo=timezone.utc
        ),
        hypothesis_deadline="2026-07-06",
        reality_available_at=datetime(2026, 7, 6, 7, 30, tzinfo=timezone.utc),
        verified_at=datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc),
        source_knowledge_hash="a" * 64,
        source_evidence_hash="b" * 64,
        source_context_hash="c" * 64,
        source_thesis_hash="d" * 64,
        reality_evidence_hash="e" * 64,
        prediction_probability=0.72,
        source_quality_score=0.91,
        source_policy_version="m8_phase0_cognition.v1",
        label=VerificationLabel.NO,
        failure_type=VerificationFailureType.WRONG_DIRECTION,
        verification_reason="机器人未出现预期修复，核心载体继续走弱。",
        outcome=outcome,
        evidence_refs=("ev:2026-07-06:robot:cycle",),
    )


# TC-M8P1-T02-01
def test_append_same_record_twice_when_persisted_then_duplicate_is_skipped(
    tmp_path,
) -> None:
    dataset = MarketThesisValidationDataset(tmp_path)
    record = _record()

    created = dataset.append(record)
    duplicate = dataset.append(record)

    assert created.status == "created"
    assert duplicate.status == "duplicate"
    assert duplicate.path == created.path
    assert created.path.exists()
    assert dataset.list_records() == [record]


# TC-M8P1-T02-01
def test_same_identity_with_changed_content_when_appended_then_conflict_is_rejected(
    tmp_path,
) -> None:
    dataset = MarketThesisValidationDataset(tmp_path)
    original = _record()
    created = dataset.append(original)

    with pytest.raises(ValidationDatasetConflictError, match="conflict"):
        dataset.append(_record(outcome="错误地覆盖原结果"))

    assert dataset.read(created.path) == original


# TC-M8P1-T02-01
def test_corrupted_record_when_read_then_dataset_fails_fast(tmp_path) -> None:
    dataset = MarketThesisValidationDataset(tmp_path)
    created = dataset.append(_record())
    payload = created.path.read_bytes()
    created.path.write_bytes(
        payload.replace(b'"record_hash": "', b'"record_hash": "corrupted-')
    )

    with pytest.raises(ValidationDatasetCorruptionError, match="hash|corrupt"):
        dataset.read(created.path)


# TC-M8P1-T02-01
def test_invalid_verification_date_when_appended_then_rejected(tmp_path) -> None:
    dataset = MarketThesisValidationDataset(tmp_path)
    invalid = replace(_record(), verification_trade_date="2026-99-99")

    with pytest.raises(ValueError, match="valid YYYY-MM-DD") as exc_info:
        dataset.append(invalid)

    assert "trade dates" in str(exc_info.value)


# TC-M8P1-T02-03
def test_manifest_when_records_change_after_refresh_then_integrity_check_fails(
    tmp_path,
) -> None:
    dataset = MarketThesisValidationDataset(tmp_path)
    first = dataset.append(_record())
    dataset.append(
        _record(source_hypothesis_id="hyp:2026-07-03:pcb-takeover")
    )

    manifest = dataset.refresh_manifest()
    verified = dataset.verify_manifest()

    assert manifest.record_count == 2
    assert verified.dataset_hash == manifest.dataset_hash
    assert verified.manifest_hash == manifest.manifest_hash

    first.path.unlink()
    with pytest.raises(ValidationDatasetCorruptionError, match="manifest"):
        dataset.verify_manifest()


# TC-M8P1-T02-02
def test_today_reality_not_after_yesterday_thesis_when_built_then_rejected() -> None:
    kwargs = {
        field: getattr(_record(), field)
        for field in (
            "thesis_trade_date",
            "verification_trade_date",
            "source_hypothesis_id",
            "source_hypothesis_as_of",
            "hypothesis_deadline",
            "reality_available_at",
            "verified_at",
            "source_knowledge_hash",
            "source_evidence_hash",
            "source_context_hash",
            "source_thesis_hash",
            "reality_evidence_hash",
            "prediction_probability",
            "source_quality_score",
            "source_policy_version",
            "label",
            "failure_type",
            "verification_reason",
            "outcome",
            "evidence_refs",
        )
    }
    kwargs["reality_available_at"] = kwargs["source_hypothesis_as_of"]

    with pytest.raises(ValueError, match="future data leak") as exc_info:
        MarketThesisValidationRecordBuilder.build(**kwargs)

    assert "source hypothesis as_of" in str(exc_info.value)
