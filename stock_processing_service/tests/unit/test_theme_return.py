"""M7a-lite: Theme Return Attribution tests."""

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.domain.services.theme_return import (
    ThemeReturnAttributionEngine,
    MarketTruth,
)
from stock_processing_service.domain.services.leader_scoring import LeaderScore

TD = date(2026, 6, 18)


def _ls(code, name, theme, leader=0.5, rank=1):
    return LeaderScore(TD, code, name, theme, leader_score=leader,
                       event_score=0.3, expectation_score=0.1, resonance_score=0.1,
                       board_strength_score=0.2, rank_in_theme=rank,
                       source_trace_id=f"test:{code}:{theme}")


def _mt(code, name, pct_chg=0.0, limit_up=False, boards=0, amount=1e8):
    return MarketTruth(code, name, pct_chg, limit_up, boards, amount, close_price=10.0)


# ── Theme Return computation ─────────────────────────────────────

def test_theme_return_from_leaders():
    engine = ThemeReturnAttributionEngine()
    leaders = [
        _ls("002747", "埃斯顿", "机器人", 0.8, 1),
        _ls("002527", "拓斯达", "机器人", 0.6, 2),
        _ls("002896", "中大力德", "机器人", 0.4, 3),
    ]
    truths = {
        "002747": _mt("002747", "埃斯顿", 10.0, True, 2),
        "002527": _mt("002527", "拓斯达", 8.5, True, 0),
        "002896": _mt("002896", "中大力德", 5.0),
    }
    results = engine.compute(TD, leaders, truths)
    assert len(results) == 1
    assert results[0].theme_name == "机器人"
    assert results[0].return_1d == pytest.approx(7.8333, abs=0.001)
    assert results[0].leader_return_1d == pytest.approx(10.0)


def test_theme_return_missing_truth():
    """When a leader has no market truth, it's excluded from avg."""
    engine = ThemeReturnAttributionEngine()
    leaders = [
        _ls("002747", "埃斯顿", "机器人", 0.8, 1),
        _ls("002527", "拓斯达", "机器人", 0.6, 2),
    ]
    truths = {"002747": _mt("002747", "埃斯顿", 10.0)}
    results = engine.compute(TD, leaders, truths)
    assert results[0].return_1d == pytest.approx(10.0)  # only 1 stock
    assert results[0].leader_count == 1


def test_multi_theme_returns():
    engine = ThemeReturnAttributionEngine()
    leaders = [
        _ls("002747", "埃斯顿", "机器人", 0.8, 1),
        _ls("002579", "中京电子", "PCB", 0.7, 1),
    ]
    truths = {
        "002747": _mt("002747", "埃斯顿", 10.0, True),
        "002579": _mt("002579", "中京电子", 9.5, True),
    }
    results = engine.compute(TD, leaders, truths)
    assert len(results) == 2
    # Higher return should rank first
    assert results[0].theme_name == "机器人"


def test_build_actual_strength_map():
    from stock_processing_service.domain.services.theme_return import ThemeReturn

    engine = ThemeReturnAttributionEngine()
    returns = [
        ThemeReturn(TD, "机器人", 8.0, None, None, 10.0, None, None, 3),
        ThemeReturn(TD, "PCB", 5.0, None, None, 7.0, None, None, 2),
    ]
    actual_map = engine.build_actual_strength_map(returns)
    assert actual_map["机器人"]["rank"] == 1
    assert actual_map["机器人"]["strength"] > actual_map["PCB"]["strength"]


def test_strength_normalization_range():
    """Normalized strength should be in [0, 1]."""
    from stock_processing_service.domain.services.theme_return import ThemeReturn

    engine = ThemeReturnAttributionEngine()
    returns = [
        ThemeReturn(TD, "涨停主题", 10.0, None, None, 10.0, None, None, 5),
        ThemeReturn(TD, "跌停主题", -10.0, None, None, -10.0, None, None, 3),
        ThemeReturn(TD, "横盘主题", 0.0, None, None, 0.0, None, None, 2),
    ]
    actual_map = engine.build_actual_strength_map(returns)
    for theme, data in actual_map.items():
        assert 0.0 <= data["strength"] <= 1.0, f"{theme}: strength={data['strength']}"


# ── Integration: M7a truth → M7b error ──────────────────────────

def test_truth_feeds_error_engine():
    """Market truth from M7a should feed directly into M7b error engine."""
    from stock_processing_service.domain.services.market_feedback import PredictionVsRealityEngine
    from stock_processing_service.domain.services.theme_return import ThemeReturn

    # M6 predictions
    predicted = {
        "机器人": {"strength": 0.75, "rank": 1, "stability": 0.6, "sources": ["ths"]},
        "PCB": {"strength": 0.60, "rank": 2, "stability": 0.5, "sources": ["ths"]},
    }

    # M7a truth (from theme returns)
    engine = ThemeReturnAttributionEngine()
    returns = [
        ThemeReturn(TD, "机器人", 8.5, None, None, 10.0, None, None, 3),
        ThemeReturn(TD, "PCB", 3.0, None, None, 5.0, None, None, 2),
    ]
    actual = engine.build_actual_strength_map(returns)

    # M7b error
    error_engine = PredictionVsRealityEngine()
    report = error_engine.compute(TD, predicted, actual)

    assert report.summary["total_themes"] == 2
    # PCB actual < predicted → error > 0
    pcb_err = next(e for e in report.errors if e.theme_name == "PCB")
    assert pcb_err.strength_error > 0  # overestimated
