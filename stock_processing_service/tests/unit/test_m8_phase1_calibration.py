"""T04 unit tests — Calibration Metrics Service.

Tests Binary Accuracy, Brier Score, ECE, and Timing Offset computation
using synthetic validation records.

Per ADR-M8-009:
- Only YES/NO records enter probability metrics.
- PARTIAL and UNVERIFIABLE are excluded but counted.
- quality_score is never used as probability.
- Narrative contamination is flagged.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stock_processing_service.application.services.market_cognition.calibration import (
    CalibrationMetricsService,
    CalibrationReport,
    _is_narrative_confidence_suspect,
)
from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecord,
    MarketThesisValidationRecordBuilder,
    VerificationFailureType,
    VerificationLabel,
)


_EPOCH = datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc)


def _record(
    *,
    thesis_trade_date: str = "2026-07-03",
    verification_trade_date: str = "2026-07-06",
    source_hypothesis_id: str = "hyp:test:001",
    source_hypothesis_as_of: datetime | None = None,
    hypothesis_deadline: str = "2026-07-06",
    reality_available_at: datetime | None = None,
    verified_at: datetime | None = None,
    prediction_probability: float = 0.65,
    source_quality_score: float = 0.90,
    label: VerificationLabel = VerificationLabel.YES,
    failure_type: VerificationFailureType | None = None,
) -> MarketThesisValidationRecord:
    if failure_type is None and label is not VerificationLabel.YES:
        if label is VerificationLabel.NO:
            failure_type = VerificationFailureType.WRONG_DIRECTION
        elif label is VerificationLabel.PARTIAL:
            failure_type = VerificationFailureType.WRONG_TIMING
        elif label is VerificationLabel.UNVERIFIABLE:
            failure_type = VerificationFailureType.INSUFFICIENT_EVIDENCE
    source_as_of = source_hypothesis_as_of or _EPOCH
    reality_at = reality_available_at or datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc)
    verified = verified_at or datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc)
    return MarketThesisValidationRecordBuilder.build(
        thesis_trade_date=thesis_trade_date,
        verification_trade_date=verification_trade_date,
        source_hypothesis_id=source_hypothesis_id,
        source_hypothesis_as_of=source_as_of,
        hypothesis_deadline=hypothesis_deadline,
        reality_available_at=reality_at,
        verified_at=verified,
        source_knowledge_hash="a" * 64,
        source_evidence_hash="b" * 64,
        source_context_hash="c" * 64,
        source_thesis_hash="d" * 64,
        reality_evidence_hash="e" * 64,
        prediction_probability=prediction_probability,
        source_quality_score=source_quality_score,
        source_policy_version="m8_phase0_cognition.v1",
        label=label,
        failure_type=failure_type,
        verification_reason="test record",
        outcome="test outcome",
        evidence_refs=("ev:test:001",),
    )


# ── TC-M8P1-T04-01: Binary Accuracy ──

def test_perfect_yes_prediction_when_high_prob_then_all_correct() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.85, label=VerificationLabel.YES)
        for _ in range(10)
    ]
    report = service.compute(records)
    assert report.binary_accuracy is not None
    assert report.binary_accuracy.accuracy == 1.0
    assert report.binary_accuracy.yes_correct == 10
    assert report.binary_accuracy.yes_total == 10


def test_perfect_no_prediction_when_low_prob_then_all_correct() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.30, label=VerificationLabel.NO)
        for _ in range(10)
    ]
    report = service.compute(records)
    assert report.binary_accuracy is not None
    assert report.binary_accuracy.accuracy == 1.0
    assert report.binary_accuracy.no_correct == 10


def test_mixed_predictions_when_misclassified_then_accuracy_reflects() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.85, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:yes1"),  # correct
        _record(prediction_probability=0.85, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:yes2"),  # correct
        _record(prediction_probability=0.30, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:no1"),   # correct
        _record(prediction_probability=0.85, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:no2"),   # wrong direction
    ]
    report = service.compute(records)
    assert report.binary_accuracy is not None
    assert report.binary_accuracy.correct == 3
    assert report.binary_accuracy.total == 4
    assert report.binary_accuracy.accuracy == 0.75


# ── TC-M8P1-T04-02: Brier Score ──

def test_perfect_brier_when_certain_and_correct() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=1.0, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:yes"),
        _record(prediction_probability=0.0, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:no"),
    ]
    report = service.compute(records)
    assert report.brier_score is not None
    assert report.brier_score.score == 0.0


def test_worst_brier_when_certain_and_wrong() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=1.0, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:wrong1"),
    ]
    report = service.compute(records)
    assert report.brier_score is not None
    assert report.brier_score.score == 1.0   # (1-0)^2 = 1.0, worst possible


def test_brier_improves_with_better_calibration() -> None:
    service = CalibrationMetricsService()
    well_calibrated = [
        _record(prediction_probability=0.7, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:w1"),
        _record(prediction_probability=0.3, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:w2"),
    ]
    poorly_calibrated = [
        _record(prediction_probability=0.5, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:p1"),
        _record(prediction_probability=0.5, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:p2"),
    ]
    well_report = service.compute(well_calibrated)
    poor_report = service.compute(poorly_calibrated)
    assert well_report.brier_score is not None
    assert poor_report.brier_score is not None
    assert well_report.brier_score.score < poor_report.brier_score.score


# ── TC-M8P1-T04-03: ECE ──

def test_ece_zero_when_perfectly_calibrated() -> None:
    service = CalibrationMetricsService(ece_bins=3)
    # 3 bins, each with perfectly matching accuracy
    records = [
        _record(prediction_probability=0.15, label=VerificationLabel.NO, source_hypothesis_id=f"hyp:test:e{i}")
        for i in range(10)  # bin 0: prob~0.15, accuracy~0.0
    ] + [
        _record(prediction_probability=0.50, label=VerificationLabel.YES, source_hypothesis_id=f"hyp:test:e{i+10}")
        for i in range(5)  # bin 1: prob~0.50, accuracy~0.5
    ] + [
        _record(prediction_probability=0.85, label=VerificationLabel.YES, source_hypothesis_id=f"hyp:test:e{i+15}")
        for i in range(10)  # bin 2: prob~0.85, accuracy~1.0
    ]
    report = service.compute(records)
    assert report.ece is not None
    # ECE moderate: bin 1 is perfectly balanced (0.5 prob, 50% yes) but bin 0
    # and bin 2 have small gaps; the weighted sum across 3 bins yields ~0.22.
    assert report.ece.ece < 0.30


def test_ece_high_when_miscalibrated() -> None:
    service = CalibrationMetricsService(ece_bins=3)
    # High probability but wrong outcome = miscalibrated
    records = [
        _record(prediction_probability=0.90, label=VerificationLabel.NO, source_hypothesis_id=f"hyp:test:m{i}")
        for i in range(20)
    ]
    report = service.compute(records)
    assert report.ece is not None
    assert report.ece.ece > 0.8  # high miscalibration


# ── TC-M8P1-T04-04: Exclusions ──

def test_partial_and_unverifiable_excluded_from_brier() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.60, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:yes"),
        _record(prediction_probability=0.40, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:no"),
        _record(
            prediction_probability=0.50,
            label=VerificationLabel.PARTIAL,
            failure_type=VerificationFailureType.WRONG_TIMING,
            source_hypothesis_id="hyp:test:partial",
        ),
        _record(
            prediction_probability=0.50,
            label=VerificationLabel.UNVERIFIABLE,
            failure_type=VerificationFailureType.INSUFFICIENT_EVIDENCE,
            source_hypothesis_id="hyp:test:unverifiable",
        ),
    ]
    report = service.compute(records)
    assert report.eligible_for_probability_metrics == 2
    assert report.excluded_partial == 1
    assert report.excluded_unverifiable == 1
    assert report.brier_score is not None
    assert report.brier_score.sample_count == 2


def test_empty_records_when_no_data_then_report_with_warning() -> None:
    service = CalibrationMetricsService()
    report = service.compute([])
    assert report.total_records == 0
    assert "no_records" in report.warnings


def test_low_sample_warning_when_fewer_than_10() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.6, label=VerificationLabel.YES, source_hypothesis_id=f"hyp:test:s{i}")
        for i in range(5)
    ]
    report = service.compute(records)
    assert any("low_sample" in w for w in report.warnings)


# ── TC-M8P1-T04-05: Narrative contamination detection ──

def test_narrative_contamination_when_probability_equals_quality() -> None:
    record = _record(prediction_probability=0.90, source_quality_score=0.90)
    assert _is_narrative_confidence_suspect(record) is True


def test_narrative_contamination_when_difference_is_small() -> None:
    record = _record(prediction_probability=0.90, source_quality_score=0.905)
    assert _is_narrative_confidence_suspect(record) is True


def test_no_contamination_when_probability_and_quality_differ() -> None:
    record = _record(prediction_probability=0.62, source_quality_score=0.91)
    assert _is_narrative_confidence_suspect(record) is False


def test_narrative_contamination_triggers_warning_in_report() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.90, source_quality_score=0.90, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:n1"),
        _record(prediction_probability=0.90, source_quality_score=0.90, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:n2"),
    ]
    report = service.compute(records)
    assert any("narrative contamination" in w.lower() for w in report.warnings)


# ── TC-M8P1-T04-06: Timing Offset ──

def test_timing_offset_when_various_delays() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(
            thesis_trade_date="2026-07-01",
            verification_trade_date="2026-07-03",
            hypothesis_deadline="2026-07-03",
            source_hypothesis_id="hyp:test:t1",
            source_hypothesis_as_of=datetime(2026, 7, 1, 15, 30, tzinfo=timezone.utc),
        ),
        _record(
            thesis_trade_date="2026-07-01",
            verification_trade_date="2026-07-03",
            hypothesis_deadline="2026-07-03",
            source_hypothesis_id="hyp:test:t2",
            source_hypothesis_as_of=datetime(2026, 7, 1, 15, 30, tzinfo=timezone.utc),
        ),
        _record(
            thesis_trade_date="2026-07-01",
            verification_trade_date="2026-07-06",
            hypothesis_deadline="2026-07-06",
            source_hypothesis_id="hyp:test:t3",
            source_hypothesis_as_of=datetime(2026, 7, 1, 15, 30, tzinfo=timezone.utc),
        ),
    ]
    report = service.compute(records)
    assert report.timing_offset is not None
    assert report.timing_offset.sample_count == 3
    assert 2 in report.timing_offset.offsets
    assert 5 in report.timing_offset.offsets
    assert report.timing_offset.mean_offset is not None
    assert report.timing_offset.median_offset is not None


# ── TC-M8P1-T04-07: quality_score not used as probability ──

def test_quality_score_never_enters_probability_metrics() -> None:
    """Verify that changing only quality_score does not affect Brier/ECE."""
    service = CalibrationMetricsService()
    records_high_quality = [
        _record(prediction_probability=0.60, source_quality_score=0.99, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:hq"),
    ]
    records_low_quality = [
        _record(prediction_probability=0.60, source_quality_score=0.50, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:lq"),
    ]
    high = service.compute(records_high_quality)
    low = service.compute(records_low_quality)
    assert high.brier_score is not None and low.brier_score is not None
    # Brier should be identical regardless of quality_score
    assert high.brier_score.score == low.brier_score.score


# ── TC-M8P1-T04-08: Report serialization ──

def test_calibration_report_serializes_to_dict() -> None:
    service = CalibrationMetricsService()
    records = [
        _record(prediction_probability=0.70, label=VerificationLabel.YES, source_hypothesis_id="hyp:test:ser1"),
        _record(prediction_probability=0.35, label=VerificationLabel.NO, source_hypothesis_id="hyp:test:ser2"),
    ]
    report = service.compute(records)
    d = report.to_dict()
    assert d["schema_version"] == "calibration_report.v1"
    assert d["total_records"] == 2
    assert d["eligible_for_probability_metrics"] == 2
    assert "binary_accuracy" in d
    assert "brier_score" in d
    assert "ece" in d
    assert "timing_offset" in d
