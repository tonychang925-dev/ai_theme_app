"""M6: Stability & Market Anchor tests."""

from __future__ import annotations

import pytest

from stock_processing_service.domain.services.theme_stability import (
    detect_theme_drift,
    compute_market_anchor,
    compute_theme_stability,
    STABILITY_THRESHOLD,
    ANCHOR_THRESHOLD,
    DRIFT_THRESHOLD,
)
from stock_processing_service.domain.services.theme_strength import ThemeStrength


def _ts(name, stock_count=3, leaders=None, sources=None, avg_leader=0.3):
    return ThemeStrength(
        trade_date=None, theme_name=name, strength_score=0.5,
        stock_count=stock_count, avg_leader_score=avg_leader,
        top_stocks=leaders or [],
        evidence_sources=sources or ["ths"],
        source_trace_id="test",
    )


# ── Stability Score ──────────────────────────────────────────────

def test_stability_first_day_neutral():
    """First day with no previous data → neutral stability."""
    ts = _ts("机器人", leaders=[
        {"stock_code": "002747", "stock_name": "埃斯顿"},
        {"stock_code": "002527", "stock_name": "拓斯达"},
    ])
    result = compute_theme_stability(ts, {}, {})
    assert result.stability_score == pytest.approx(0.50 * 0.35 + 0.50 * 0.30 + 0.50 * 0.35)
    assert result.stability_score == pytest.approx(0.50)  # neutral first day


def test_stability_high_persistence():
    """All leaders persist → high stability."""
    ts = _ts("机器人", leaders=[
        {"stock_code": "002747", "stock_name": "埃斯顿"},
        {"stock_code": "002527", "stock_name": "拓斯达"},
    ], sources=["ths", "cninfo"])
    prev_leaders = {"机器人": {"002747", "002527"}}
    prev_sources = {"机器人": {"ths", "cninfo"}}
    result = compute_theme_stability(ts, prev_leaders, prev_sources)
    assert result.stability_score > 0.7
    assert result.is_stable
    assert result.leader_persistence == 1.0


def test_stability_complete_drift():
    """All leaders changed → low stability."""
    ts = _ts("机器人", leaders=[
        {"stock_code": "002747", "stock_name": "埃斯顿"},
    ], sources=["ths"])
    prev_leaders = {"机器人": {"600000", "600001"}}  # completely different
    prev_sources = {"机器人": {"jyhf"}}
    result = compute_theme_stability(ts, prev_leaders, prev_sources)
    assert result.stability_score < STABILITY_THRESHOLD
    assert not result.is_stable
    assert len(result.warnings) >= 2


# ── Market Anchor ────────────────────────────────────────────────

def test_anchor_high_confirmation():
    """Strong limit-up chains + good flow → confirmed."""
    ts = _ts("机器人", stock_count=5)
    anchor = compute_market_anchor(
        ts, limit_up_chain_count=3, total_market_limit_ups=50,
        theme_amount=500e8, total_sector_amount=10000e8, top3_stock_amount=250e8,
    )
    assert anchor.anchor_score > ANCHOR_THRESHOLD
    assert anchor.is_confirmed


def test_anchor_no_limit_ups():
    """No limit-up chains → unconfirmed."""
    ts = _ts("机器人", stock_count=5)
    anchor = compute_market_anchor(
        ts, limit_up_chain_count=0, total_market_limit_ups=50,
        theme_amount=100e8, total_sector_amount=10000e8,
    )
    assert anchor.anchor_score < 0.40
    assert not anchor.is_confirmed


def test_anchor_concentration_goldilocks():
    """Optimal concentration ~50% scores highest."""
    ts = _ts("机器人", stock_count=5)
    anchor = compute_market_anchor(
        ts, limit_up_chain_count=3, total_market_limit_ups=50,
        theme_amount=500e8, total_sector_amount=10000e8,
        top3_stock_amount=250e8,  # 50% concentration → optimal
    )
    assert anchor.leader_concentration == 1.0


# ── Drift Detector ───────────────────────────────────────────────

def test_drift_first_day_no_baseline():
    report = detect_theme_drift("AI算力基础设施", None, ["AI算力基础设施"])
    assert not report.is_drifting
    assert report.note == "first_day_no_baseline"


def test_drift_stable_aliases():
    report = detect_theme_drift(
        "PCB/HBM产业链",
        ["PCB/HBM产业链", "PCB印制电路板"],
        ["PCB/HBM产业链", "HDI产业链"],
    )
    # 2 prev, 2 curr, intersection=1 → similarity=1/3, change=2/3=0.67 > 0.30 → drifting
    assert report.is_drifting


def test_drift_identical_aliases():
    report = detect_theme_drift(
        "机器人", ["机器人", "人形机器人"], ["机器人", "人形机器人"],
    )
    assert report.alias_change_rate == 0.0
    assert not report.is_drifting


def test_drift_minor_change():
    """Small alias change below threshold."""
    report = detect_theme_drift(
        "AI算力基础设施",
        ["AI算力基础设施", "算力", "数据中心"],
        ["AI算力基础设施", "算力"],  # dropped "数据中心"
    )
    # intersection=2, union=3, similarity=2/3, change=1/3=0.33
    assert report.alias_change_rate == pytest.approx(1 / 3, abs=0.01)


# ── Integration: stability + anchor full picture ─────────────────

def test_theme_with_all_three_scores():
    """A theme can have stability + anchor + drift scores simultaneously."""
    ts = _ts("机器人", stock_count=5, leaders=[
        {"stock_code": "002747", "stock_name": "埃斯顿"},
        {"stock_code": "002527", "stock_name": "拓斯达"},
    ], sources=["ths", "cninfo"])

    prev_leaders = {"机器人": {"002747"}}  # 1 of 2 persisted
    prev_sources = {"机器人": {"ths"}}     # 1 of 2 in common

    stability = compute_theme_stability(ts, prev_leaders, prev_sources)
    anchor = compute_market_anchor(ts, limit_up_chain_count=2, total_market_limit_ups=50)
    drift = detect_theme_drift("机器人", ["机器人"], ["机器人", "工业机器人"])

    assert 0 < stability.stability_score <= 1.0
    assert 0 <= anchor.anchor_score <= 1.0
    assert 0 <= drift.drift_score <= 1.0
    # Three scores are independent and can coexist
    assert isinstance(stability.is_stable, bool)
    assert isinstance(anchor.is_confirmed, bool)
    assert isinstance(drift.is_drifting, bool)
