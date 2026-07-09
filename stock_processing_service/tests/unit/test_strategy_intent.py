"""Phase 4.2.2a — Strategy Intent Matcher tests."""

from __future__ import annotations

import pytest

from stock_processing_service.application.services.analyst_alignment.strategy_intent import (
    AVOID_HIGH_POSITION,
    CAN_PARTICIPATE,
    CORE_ONLY,
    LIGHT_POSITION,
    NO_CHASING,
    REBOUND_ARBITRAGE,
    RISK_OFF,
    WAIT_CONFIRMATION,
    StrategyIntentMatch,
    StrategyIntentMatcher,
)


@pytest.fixture
def matcher():
    return StrategyIntentMatcher()


# ═══ TC-STI-01: extract WAIT_CONFIRMATION + LIGHT_POSITION ═══

def test_extract_wait_and_light(matcher):
    intents = matcher.extract_intents("等待确认，轻仓观察，控制仓位")
    assert WAIT_CONFIRMATION in intents
    assert LIGHT_POSITION in intents


# ═══ TC-STI-02: extract NO_CHASING + CORE_ONLY ═══

def test_extract_no_chasing_and_core(matcher):
    intents = matcher.extract_intents("不追高，只做核心方向，聚焦主线")
    assert NO_CHASING in intents
    assert CORE_ONLY in intents


# ═══ TC-STI-03: extract REBOUND_ARBITRAGE ═══

def test_extract_rebound_arbitrage(matcher):
    intents = matcher.extract_intents("反弹套利，快进快出，短线参与")
    assert REBOUND_ARBITRAGE in intents


# ═══ TC-STI-04: extract RISK_OFF + AVOID_HIGH_POSITION ═══

def test_extract_risk_off_and_avoid_high(matcher):
    intents = matcher.extract_intents("空仓防守，回避高位，谨慎少动")
    assert RISK_OFF in intents
    assert AVOID_HIGH_POSITION in intents


# ═══ TC-STI-05: analyst vs AI intent — high overlap ═══

def test_compare_high_overlap(matcher):
    """Analyst: wait+light, AI: wait+light → high score."""
    match = matcher.compare(
        "等待确认，轻仓观察",
        "等待量能确认，控制仓位",
    )
    assert match.score >= 0.65
    assert WAIT_CONFIRMATION in match.overlap_intents
    assert LIGHT_POSITION in match.overlap_intents


# ═══ TC-STI-06: analyst vs AI — opposite intents ═══

def test_compare_opposite(matcher):
    """Analyst: no chasing, AI: can participate → low score."""
    match = matcher.compare(
        "不追高，不扩大仓位",
        "可参与，低吸试错",
    )
    # One side says NO_CHASING, other says CAN_PARTICIPATE → no overlap
    assert NO_CHASING not in match.overlap_intents
    assert CAN_PARTICIPATE not in match.overlap_intents
    assert match.score < 0.5


# ═══ TC-STI-07: AI empty text → score=0 ═══

def test_compare_ai_empty(matcher):
    match = matcher.compare("等待确认，轻仓观察", "")
    assert match.score == 0.0
    assert len(match.missing_intents) > 0


# ═══ TC-STI-08: both empty → score=0.7 ═══

def test_compare_both_empty(matcher):
    match = matcher.compare("", "")
    assert match.score == 0.70


# ═══ TC-STI-09: empty text extraction ═══

def test_extract_empty(matcher):
    assert matcher.extract_intents("") == ()
    assert matcher.extract_intents("   ") == ()


# ═══ TC-STI-10: 7/9 real-world case ═══

def test_real_0709_case(matcher):
    """Analyst: 反弹非反转, 轻仓观察, 不追高 — AI: 反弹, 控制仓位, 等待确认."""
    match = matcher.compare(
        "只是反弹不是反转，轻仓观察，不追高，快进快出",
        "反弹阶段，控制仓位，等待确认，低吸参与",
    )
    # Expected overlap: LIGHT_POSITION, REBOUND_ARBITRAGE, WAIT_CONFIRMATION
    assert LIGHT_POSITION in match.overlap_intents
    assert match.score > 0.35, f"Expected >0.35, got {match.score:.3f}"


# ═══ TC-STI-11: StrategyIntentMatch to_dict ═══

def test_match_to_dict(matcher):
    match = matcher.compare("等待确认，轻仓", "等待确认，控制仓位")
    d = match.to_dict()
    assert "score" in d
    assert "analyst_intents" in d
    assert "ai_intents" in d
    assert "overlap_intents" in d
