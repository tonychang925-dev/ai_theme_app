from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from stock_processing_service.contracts.market_cognition import (
    EvidenceRef,
    HypothesisState,
    ThesisStatement,
)
from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecordBuilder,
    VerificationFailureType,
    VerificationLabel,
)

try:
    from stock_processing_service.application.services.market_cognition.verification import (
        FrozenHypothesisSource,
        HypothesisEligibilityError,
        MarketThesisVerificationService,
        ReviewerVerdict,
        TodayReality,
    )
except ModuleNotFoundError:
    FrozenHypothesisSource = None
    HypothesisEligibilityError = ValueError
    MarketThesisVerificationService = None
    ReviewerVerdict = None
    TodayReality = None

try:
    from stock_processing_service.application.services.market_cognition.hypothesis_source_store import (
        FrozenHypothesisSourceStore,
        HypothesisSourceConflictError,
    )
except ModuleNotFoundError:
    FrozenHypothesisSourceStore = None
    HypothesisSourceConflictError = RuntimeError


def _kwargs() -> dict:
    return {
        "thesis_trade_date": "2026-07-03",
        "verification_trade_date": "2026-07-06",
        "source_hypothesis_id": "hyp:2026-07-03:robot-repair",
        "source_hypothesis_as_of": datetime(
            2026, 7, 3, 15, 30, tzinfo=timezone.utc
        ),
        "hypothesis_deadline": "2026-07-06",
        "reality_available_at": datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc),
        "verified_at": datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
        "source_knowledge_hash": "a" * 64,
        "source_evidence_hash": "b" * 64,
        "source_context_hash": "c" * 64,
        "source_thesis_hash": "d" * 64,
        "reality_evidence_hash": "e" * 64,
        "prediction_probability": 0.72,
        "source_quality_score": 0.91,
        "source_policy_version": "m8_phase0_cognition.v1",
        "verification_reason": "机器人未出现预期修复，核心载体继续走弱。",
        "outcome": "修复失败",
        "evidence_refs": ("ev:today:robot:cycle",),
    }


# TC-M8P1-T01-01
def test_same_validation_input_when_built_twice_then_record_hash_is_stable() -> None:
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
    assert first.prediction_probability == 0.72
    assert first.source_quality_score == 0.91
    assert not hasattr(first, "confidence")
    assert not hasattr(first, "belief")
    assert not hasattr(first, "learning")


# TC-M8P1-T01-02
def test_no_label_without_failure_type_when_built_then_validation_fails() -> None:
    with pytest.raises(ValueError, match="failure_type"):
        MarketThesisValidationRecordBuilder.build(
            **_kwargs(),
            label=VerificationLabel.NO,
            failure_type=None,
        )


# TC-M8P1-T01-02
def test_unverifiable_with_insufficient_evidence_when_built_then_record_is_valid() -> None:
    record = MarketThesisValidationRecordBuilder.build(
        **_kwargs(),
        label=VerificationLabel.UNVERIFIABLE,
        failure_type=VerificationFailureType.INSUFFICIENT_EVIDENCE,
    )

    assert record.label is VerificationLabel.UNVERIFIABLE
    assert record.failure_type is VerificationFailureType.INSUFFICIENT_EVIDENCE


# TC-M8P1-T01-02
def test_future_reality_not_after_thesis_when_built_then_future_leak_is_rejected() -> None:
    kwargs = _kwargs()
    kwargs["reality_available_at"] = kwargs["source_hypothesis_as_of"]

    with pytest.raises(ValueError, match="future|available_at|as_of"):
        MarketThesisValidationRecordBuilder.build(
            **kwargs,
            label=VerificationLabel.NO,
            failure_type=VerificationFailureType.MARKET_REGIME_SHIFT,
        )


def _ref(ref_id: str) -> EvidenceRef:
    return EvidenceRef(
        ref_id=ref_id,
        source_module="engine_summary",
        source_path="allow_trade",
        source_snapshot_id="mkb:2026-07-03:abc",
    )


def _source():
    assert FrozenHypothesisSource is not None, "verification workflow missing"
    return FrozenHypothesisSource(
        thesis_trade_date="2026-07-03",
        source_snapshot_id="thesis:2026-07-03:abc",
        source_as_of=datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc),
        source_knowledge_hash="a" * 64,
        source_evidence_hash="b" * 64,
        source_context_hash="c" * 64,
        source_thesis_hash="d" * 64,
        source_quality_status="ready",
        source_quality_score=0.91,
        source_policy_version="m8_phase0_cognition.v1",
        hypothesis=HypothesisState(
            hypothesis_id="hyp:2026-07-03:robot-repair",
            statement="未来一个交易日内，机器人主线将获得资金确认并修复。",
            status="VALIDATING",
            probability=0.62,
            deadline="2026-07-06",
            expected_observations=("主线资金转正", "核心载体强度修复"),
            falsifiers=("资金继续流出", "核心载体继续走弱"),
            evidence_refs=(_ref("ev:yesterday:robot"),),
        ),
    )


def _reality():
    assert TodayReality is not None, "verification workflow missing"
    return TodayReality(
        trade_date="2026-07-06",
        available_at=datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc),
        evidence_hash="e" * 64,
        evidence_refs=(_ref("ev:today:robot"),),
    )


# TC-M8P1-T03-01
@pytest.mark.parametrize(
    ("label", "failure_type"),
    [
        (VerificationLabel.YES, None),
        (VerificationLabel.NO, VerificationFailureType.WRONG_DIRECTION),
        (VerificationLabel.PARTIAL, VerificationFailureType.WRONG_TIMING),
        (
            VerificationLabel.UNVERIFIABLE,
            VerificationFailureType.INSUFFICIENT_EVIDENCE,
        ),
    ],
)
def test_eligible_hypothesis_with_explicit_reviewer_when_verified_then_record_is_created(
    label,
    failure_type,
) -> None:
    assert MarketThesisVerificationService is not None, "verification workflow missing"
    assert ReviewerVerdict is not None, "reviewer verdict missing"
    service = MarketThesisVerificationService(
        approved_reviewer_ids={"reviewer:alice"}
    )
    verdict = ReviewerVerdict(
        reviewer_id="reviewer:alice",
        label=label,
        failure_type=failure_type,
        reason="按冻结判据完成人工复核。",
        outcome="记录真实市场结果。",
        reviewed_at=datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
    )

    record = service.verify(_source(), _reality(), verdict)

    assert record.source_hypothesis_id == "hyp:2026-07-03:robot-repair"
    assert record.prediction_probability == 0.62
    assert record.source_quality_score == 0.91
    assert record.label is label
    assert record.failure_type is failure_type


# TC-M8P1-T03-02
def test_observation_or_assessment_when_checked_then_eligibility_is_rejected() -> None:
    assert MarketThesisVerificationService is not None, "verification workflow missing"
    service = MarketThesisVerificationService(
        approved_reviewer_ids={"reviewer:alice"}
    )
    narrative = ThesisStatement(
        statement="当前市场处于冰点，不建议主动交易。",
        evidence_refs=(_ref("ev:today:sentiment"),),
        confidence=1.0,
    )
    source = replace(_source(), hypothesis=narrative)

    with pytest.raises(HypothesisEligibilityError, match="HypothesisState") as exc:
        service.check_eligibility(source)

    assert "eligible" in str(exc.value).lower()


# TC-M8P1-T03-02
def test_missing_falsifier_or_unapproved_reviewer_when_verified_then_rejected() -> None:
    assert MarketThesisVerificationService is not None, "verification workflow missing"
    assert ReviewerVerdict is not None, "reviewer verdict missing"
    service = MarketThesisVerificationService(
        approved_reviewer_ids={"reviewer:alice"}
    )
    source = replace(
        _source(),
        hypothesis=replace(_source().hypothesis, falsifiers=()),
    )
    verdict = ReviewerVerdict(
        reviewer_id="model:auto",
        label=VerificationLabel.YES,
        failure_type=None,
        reason="模型自动判断。",
        outcome="自动生成结果。",
        reviewed_at=datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(HypothesisEligibilityError, match="falsifier") as exc:
        service.verify(source, _reality(), verdict)
    assert "required" in str(exc.value).lower()

    with pytest.raises(ValueError, match="approved reviewer") as reviewer_exc:
        service.verify(_source(), _reality(), verdict)
    assert "model:auto" in str(reviewer_exc.value)


# TC-M8P1-T03-01
def test_eligible_hypothesis_when_frozen_twice_then_source_is_append_only(
    tmp_path,
) -> None:
    assert FrozenHypothesisSourceStore is not None, "source freeze store missing"
    store = FrozenHypothesisSourceStore(tmp_path)
    source = _source()

    created = store.append(source)
    duplicate = store.append(source)

    assert created.status == "created"
    assert duplicate.status == "duplicate"
    assert duplicate.source_hash == created.source_hash
    assert store.read(created.path) == source

    changed = replace(
        source,
        hypothesis=replace(
            source.hypothesis,
            statement="事后修改的昨日假设不得覆盖原记录。",
        ),
    )
    with pytest.raises(HypothesisSourceConflictError, match="conflict") as exc:
        store.append(changed)
    assert source.hypothesis.hypothesis_id in str(exc.value)
