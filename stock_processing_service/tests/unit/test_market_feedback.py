"""M7b + M7c: Market Feedback & Calibration tests."""

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.domain.services.market_feedback import (
    PredictionVsRealityEngine,
    WeightCalibrationEngine,
    ERROR_THRESHOLD,
    MAX_DELTA_PER_CYCLE,
    DEFAULT_SOURCE_WEIGHTS,
)

TD = date(2026, 6, 18)


# ── M7b: Error Engine ───────────────────────────────────────────

def test_exact_match_is_correct():
    engine = PredictionVsRealityEngine()
    predicted = {"机器人": {"strength": 0.75, "rank": 1, "stability": 0.6, "anchor": 0.5, "sources": ["ths"]}}
    actual = {"机器人": {"strength": 0.75, "rank": 1}}
    report = engine.compute(TD, predicted, actual)
    assert report.errors[0].error_bucket == "correct"
    assert report.errors[0].strength_error == 0.0


def test_overestimate_detected():
    engine = PredictionVsRealityEngine()
    predicted = {"AI算力": {"strength": 0.80, "rank": 1, "stability": 0.5, "sources": ["research"]}}
    actual = {"AI算力": {"strength": 0.50, "rank": 3}}
    report = engine.compute(TD, predicted, actual)
    assert report.errors[0].error_bucket == "overestimate"
    assert "AI算力" in report.overestimated


def test_underestimate_detected():
    engine = PredictionVsRealityEngine()
    predicted = {"有色资源": {"strength": 0.30, "rank": 5, "stability": 0.4, "sources": ["eastmoney"]}}
    actual = {"有色资源": {"strength": 0.60, "rank": 2}}
    report = engine.compute(TD, predicted, actual)
    assert report.errors[0].error_bucket == "underestimate"
    assert "有色资源" in report.underestimated


def test_source_bias_aggregation():
    engine = PredictionVsRealityEngine()
    predicted = {
        "主题A": {"strength": 0.90, "rank": 1, "sources": ["research"]},
        "主题B": {"strength": 0.85, "rank": 2, "sources": ["research"]},
        "主题C": {"strength": 0.40, "rank": 3, "sources": ["ths"]},
    }
    actual = {
        "主题A": {"strength": 0.60, "rank": 2},
        "主题B": {"strength": 0.55, "rank": 3},
        "主题C": {"strength": 0.50, "rank": 1},
    }
    report = engine.compute(TD, predicted, actual)
    assert "research" in report.source_bias
    assert report.source_bias["research"] > 0  # research consistently overestimates


def test_multi_theme_report():
    engine = PredictionVsRealityEngine()
    predicted = {
        "机器人": {"strength": 0.70, "rank": 1, "sources": ["ths", "cninfo"]},
        "PCB": {"strength": 0.65, "rank": 2, "sources": ["ths"]},
        "AI算力": {"strength": 0.60, "rank": 3, "sources": ["research", "eps"]},
    }
    actual = {
        "机器人": {"strength": 0.72, "rank": 1},
        "PCB": {"strength": 0.40, "rank": 3},
        "AI算力": {"strength": 0.45, "rank": 2},
    }
    report = engine.compute(TD, predicted, actual)
    assert report.summary["total_themes"] == 3
    assert report.summary["overestimated_count"] >= 1
    assert len(report.overestimated) >= 1
    assert report.summary["mean_abs_error"] > 0


# ── M7c: Calibration Engine ─────────────────────────────────────

def test_calibration_reduces_overweight_source():
    engine = WeightCalibrationEngine()
    error_report = _make_report(TD, source_bias={"research": 0.15})
    result = engine.calibrate(TD, error_report)
    assert result.new_weights["research"] < result.old_weights["research"]
    assert "research" in result.deltas


def test_calibration_increases_underweight_source():
    engine = WeightCalibrationEngine()
    error_report = _make_report(TD, source_bias={"eastmoney": -0.15})
    result = engine.calibrate(TD, error_report)
    assert result.new_weights["eastmoney"] > result.old_weights["eastmoney"]


def test_calibration_stable_when_within_threshold():
    engine = WeightCalibrationEngine()
    error_report = _make_report(TD, source_bias={"ths": 0.05})
    result = engine.calibrate(TD, error_report)
    # Bias < 0.10 → no adjustment
    assert "ths" not in result.deltas


def test_delta_capped():
    """Single cycle delta cannot exceed MAX_DELTA_PER_CYCLE."""
    engine = WeightCalibrationEngine()
    error_report = _make_report(TD, source_bias={"research": 0.50})  # huge bias
    result = engine.calibrate(TD, error_report)
    research_delta = abs(result.deltas.get("research", 0))
    assert research_delta <= MAX_DELTA_PER_CYCLE + 0.001


def test_weight_floor_respected():
    """Weights cannot go below MIN_WEIGHT."""
    from stock_processing_service.domain.services.market_feedback import MIN_WEIGHT
    # Start with jyhf at minimum
    engine = WeightCalibrationEngine({**DEFAULT_SOURCE_WEIGHTS, "jyhf": MIN_WEIGHT})
    error_report = _make_report(TD, source_bias={"jyhf": 0.20})
    result = engine.calibrate(TD, error_report)
    assert result.new_weights["jyhf"] >= MIN_WEIGHT


def test_convergence_over_multiple_cycles():
    """Weights should converge, not diverge."""
    engine = WeightCalibrationEngine()
    research_weights = []
    for day_offset in range(5):
        td = date(2026, 6, day_offset + 18)
        bias = max(0.0, 0.20 - day_offset * 0.05)  # decreasing bias
        error_report = _make_report(td, source_bias={"research": bias})
        result = engine.calibrate(td, error_report)
        research_weights.append(result.new_weights["research"])

    # Weights should be generally decreasing (not oscillating wildly)
    assert research_weights[-1] <= research_weights[0] + 0.05


def _make_report(td=TD, over=None, under=None, source_bias=None):
    """Helper to create an ErrorReport."""
    from stock_processing_service.domain.services.market_feedback import ErrorReport, PredictionError
    errors = []
    if over:
        for t in over:
            errors.append(PredictionError(t, 0.8, 0.5, 0.3, 0.3, 1, 3, 2, "overestimate", 0.5, 0.4))
    if under:
        for t in under:
            errors.append(PredictionError(t, 0.3, 0.6, -0.3, 0.3, 5, 2, 3, "underestimate", 0.4, 0.3))
    return ErrorReport(
        trade_date=td.isoformat(),
        errors=errors,
        overestimated=over or [],
        underestimated=under or [],
        correct=["主题X"],
        source_bias=source_bias or {},
        summary={"total_themes": 3, "mean_abs_error": 0.1},
    )
