"""Phase 2.1: RelayMetrics v2 — feedback score correctness tests.

Self-contained formula tests (no DB dependency).
Validates the LimitUp Feedback Score formula replicated from
MarketMetricsService._build_relay.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


# ── Replicated formula from MarketMetricsService._build_relay ──

def compute_feedback_score(yesterday_count: int, today_continue: int,
                            big_loss_count: int, avg_return: float = 0.0) -> float:
    """Replicate the LimitUp Feedback Score formula.

    Formula from MarketMetricsService._build_relay v2:
      continue_score = (today_continue / yesterday) * 100
      loss_penalty   = (big_loss_count / yesterday) * 100
      feedback_raw   = continue_score - loss_penalty + avg_return * 2
    """
    if yesterday_count == 0:
        return 0.0
    continue_score = (today_continue / yesterday_count) * 100
    loss_penalty = (big_loss_count / yesterday_count) * 100
    return round(continue_score - loss_penalty + avg_return * 2, 1)


def feedback_label(score: float) -> str:
    if score >= 60:       return "强正反馈"
    elif score >= 20:     return "正反馈"
    elif score >= -20:    return "中性"
    elif score >= -60:    return "负反馈"
    else:                 return "强负反馈"


class TestRelayFeedbackScore:
    """Validate feedback score formula with known analyst scenarios."""

    def test_promotion_33_percent(self):
        """3 yesterday stocks, 1 continued → feedback ≈ 33.3"""
        fb = compute_feedback_score(3, 1, 0)
        assert fb == pytest.approx(33.3, 0.1), f"Expected ~33.3, got {fb}"

    def test_full_continuation_strong_positive(self):
        """48/50 continued, 1 loss → 强正反馈"""
        fb = compute_feedback_score(50, 48, 1)
        assert fb >= 60, f"Expected >=60 (强正反馈), got {fb}"
        assert feedback_label(fb) == "强正反馈"

    def test_collapse_scenario(self):
        """100 yesterday, only 10 continued, 20 big loss → moderately negative"""
        fb = compute_feedback_score(100, 10, 20)
        # continue_bonus=10, loss_penalty=20, feedback=10-20=-10
        assert fb == pytest.approx(-10.0, 0.1), f"Expected ~-10, got {fb}"
        assert feedback_label(fb) == "中性"  # borderline, not yet 负反馈

    def test_neutral_scenario(self):
        """50 stocks: 15 continue, 10 big loss → near neutral"""
        fb = compute_feedback_score(50, 15, 10)
        assert -40 <= fb <= 20, f"Expected near neutral, got {fb}"

    def test_zero_yesterday(self):
        """No yesterday data → feedback = 0 (undefined)"""
        assert compute_feedback_score(0, 0, 0) == 0.0

    def test_avg_return_boost(self):
        """+3% avg return boosts feedback by 6 points (avg_return * 2)."""
        base = compute_feedback_score(50, 15, 0, avg_return=0)
        boosted = compute_feedback_score(50, 15, 0, avg_return=3.0)
        assert boosted > base, f"Boosted {boosted} should be > base {base}"
        assert boosted == pytest.approx(base + 6.0, 0.1)

    def test_negative_return_drags(self):
        """-3% avg return drags feedback down."""
        base = compute_feedback_score(50, 15, 0, avg_return=0)
        dragged = compute_feedback_score(50, 15, 0, avg_return=-3.0)
        assert dragged < base

    def test_extreme_positive(self):
        """100 continue, 0 loss → max positive ~100"""
        fb = compute_feedback_score(100, 100, 0)
        assert fb == pytest.approx(100.0, 0.1)

    def test_extreme_negative(self):
        """0 continue, 100 big loss → max negative ~-100"""
        fb = compute_feedback_score(100, 0, 100)
        assert fb == pytest.approx(-100.0, 0.1)

    def test_label_boundaries(self):
        """Feedback label thresholds match spec."""
        assert feedback_label(80) == "强正反馈"
        assert feedback_label(60) == "强正反馈"
        assert feedback_label(40) == "正反馈"
        assert feedback_label(20) == "正反馈"
        assert feedback_label(0) == "中性"
        assert feedback_label(-19) == "中性"
        assert feedback_label(-21) == "负反馈"
        assert feedback_label(-59) == "负反馈"
        assert feedback_label(-61) == "强负反馈"
        assert feedback_label(-100) == "强负反馈"


# ── Provider contract validation ──

@dataclass
class YesterdayLimitUpStock:
    """Minimal replica for contract validation."""
    stock_code: str
    trade_date: str
    board_count: int
    sealed: bool


class MockYesterdayProvider:
    """Minimal mock with filtering capability."""
    def __init__(self, stocks: list):
        self._stocks = stocks

    def get(self, trade_date: str) -> list:
        return [s for s in self._stocks if s.trade_date == trade_date]


class TestProviderContract:
    """Validate provider contract patterns (no DB)."""

    def test_mock_filtering(self):
        """Provider returns only matching date stocks."""
        stocks = [
            YesterdayLimitUpStock("000001", "2026-07-07", 1, True),
            YesterdayLimitUpStock("000002", "2026-07-07", 1, True),
            YesterdayLimitUpStock("300001", "2026-07-08", 2, False),
        ]
        provider = MockYesterdayProvider(stocks)
        day7 = provider.get("2026-07-07")
        assert len(day7) == 2
        assert all(s.sealed for s in day7)

    def test_continue_detection(self):
        """Yesterday stocks ∩ today = continued."""
        yesterday = {"000001", "000002", "000003"}
        today = {"000001", "000004", "000005"}
        continued = yesterday & today
        assert continued == {"000001"}
        assert len(continued) == 1

    def test_failed_detection(self):
        """Yesterday - today = failed (need to check today's return)."""
        yesterday = {"000001", "000002", "000003"}
        today = {"000001"}
        failed = yesterday - today
        assert failed == {"000002", "000003"}

    def test_big_loss_simulation(self):
        """Simulate: 5 failed stocks, 2 with pct_chg <= -5."""
        failed_codes = {"000001", "000002", "000003", "000004", "000005"}
        today_pct = {"000001": -8.0, "000002": -3.0, "000003": -10.0, "000004": 2.0}
        # 000005 not in today_pct (no data)
        big_loss = sum(1 for c in failed_codes if today_pct.get(c, 0) <= -5.0)
        assert big_loss == 2  # 000001 (-8.0) and 000003 (-10.0)
