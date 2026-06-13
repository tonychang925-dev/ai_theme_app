"""Unit tests for OneToTwoTechnicalGate (Stage 2 Commit 5)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures
from stock_processing_service.domain.services.one_to_two_technical_gate import (
    TECHNICAL_FOCUS_SCORE_THRESHOLD,
    TECHNICAL_GOLDEN_SCORE_THRESHOLD,
    OneToTwoTechnicalGate,
    TechnicalGateResult,
)


def _features(**overrides) -> OneToTwoFeatures:
    defaults = {
        "trade_date": "2026-05-06",
        "watch_date": "2026-05-07",
        "stock_id": "603278.SH",
        "stock_name": "大业股份",
        "subject_key": "test",
        "subject_name": "测试题材",
        "is_confirmed_mainline": True,
        "is_strong_hotspot": False,
        "mainline_or_hotspot_state": "confirmed_mainline",
        "lifecycle_state": "divergence",
        "market_trade_mode": "mainline_core_only",
        "allow_trade": True,
        "is_first_limit_up": True,
        "is_one_word_board": False,
        "is_late_seal": False,
        "first_limit_time": "10:30:00",
        "open_board_count": 1,
        "turnover_rate": Decimal("0.092"),
        "amount": Decimal("500000000"),
        "close_seal_amount": None,
        "seal_ratio": None,
        "float_mcap": None,
        "position_120": Decimal("0.35"),
        "is_downtrend": False,
        "near_pressure": False,
        "same_subject_limit_count": 3,
        "same_subject_strong_count": 7,
        "first_board_type": "chain_first_board",
        "kline_pattern_quality": {
            "kline_data_ready": True,
            "has_golden_spider": True,
            "score": 75.0,
            "level": "golden",
            "support_broken": False,
            "is_downtrend": False,
            "kline_near_resistance": False,
            "technical_reason": "golden_spider_confirmed",
            "history_bar_count": 55,
            "above_ma5": True,
            "above_ma10": True,
            "above_ma20": True,
        },
    }
    defaults.update(overrides)
    return OneToTwoFeatures(**defaults)


class TestTechnicalGateResult:
    def test_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            TechnicalGateResult(status="invalid", technical_score=Decimal("0"))


class TestGoldenSpiderAllowsFocus:
    def test_golden_spider_with_high_score_passes(self):
        gate = OneToTwoTechnicalGate()
        f = _features()
        result = gate.evaluate(f)
        assert result.status == "pass"

    def test_score_68_or_above_passes_even_without_golden_spider(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": False,
            "score": 68.0, "support_broken": False, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "pass"


class TestNoGoldenSpiderLowScoreCapsFocus:
    def test_score_below_55_caps_focus(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": False,
            "score": 48.0, "support_broken": False, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "cap_focus"
        assert result.focus_cap_reason == "技术形态未确认，暂不 focus"

    def test_score_55_to_67_without_golden_spider_passes(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": False,
            "score": 60.0, "support_broken": False, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "pass"


class TestDowntrendRejects:
    def test_feature_is_downtrend_rejects(self):
        gate = OneToTwoTechnicalGate()
        f = _features(is_downtrend=True)
        result = gate.evaluate(f)
        assert result.status == "reject"
        assert "下降趋势" in result.veto_reasons

    def test_kline_is_downtrend_rejects(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": True,
            "score": 75.0, "support_broken": False, "is_downtrend": True,
        })
        result = gate.evaluate(f)
        assert result.status == "reject"


class TestNearPressureCapsFocus:
    def test_near_pressure_caps_not_rejects(self):
        gate = OneToTwoTechnicalGate()
        f = _features(near_pressure=True)
        result = gate.evaluate(f)
        assert result.status == "cap_focus"
        assert "重要压力位附近" in result.focus_cap_reason

    def test_near_pressure_with_golden_spider_still_capped(self):
        """near_pressure caps focus even with golden spider — v1 rule."""
        gate = OneToTwoTechnicalGate()
        f = _features(near_pressure=True, kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": True,
            "score": 85.0, "support_broken": False, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "cap_focus"


class TestKlineDataNotReadyCapsFocus:
    def test_kline_data_not_ready_caps(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": False, "has_golden_spider": False,
            "score": 0.0, "support_broken": False, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "cap_focus"
        assert "K线数据不足" in result.focus_cap_reason

    def test_empty_kline_pattern_quality_caps(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={})
        result = gate.evaluate(f)
        assert result.status == "cap_focus"


class TestSupportBrokenRejects:
    def test_support_broken_rejects(self):
        gate = OneToTwoTechnicalGate()
        f = _features(kline_pattern_quality={
            "kline_data_ready": True, "has_golden_spider": True,
            "score": 85.0, "support_broken": True, "is_downtrend": False,
        })
        result = gate.evaluate(f)
        assert result.status == "reject"
        assert "支撑破坏" in result.veto_reasons


class TestTechnicalScore:
    def test_downtrend_gives_zero(self):
        score = OneToTwoTechnicalGate._compute_technical_score(
            kline_data_ready=True, has_golden_spider=True, kline_score=Decimal("85"),
            is_downtrend=True, near_pressure=False, support_broken=False,
        )
        assert score == Decimal("0")

    def test_no_data_gives_25(self):
        score = OneToTwoTechnicalGate._compute_technical_score(
            kline_data_ready=False, has_golden_spider=False, kline_score=None,
            is_downtrend=False, near_pressure=False, support_broken=False,
        )
        assert score == Decimal("25")

    def test_near_pressure_gives_30(self):
        score = OneToTwoTechnicalGate._compute_technical_score(
            kline_data_ready=True, has_golden_spider=False, kline_score=None,
            is_downtrend=False, near_pressure=True, support_broken=False,
        )
        assert score == Decimal("30")


class TestThresholdConstants:
    def test_focus_threshold_is_55(self):
        assert TECHNICAL_FOCUS_SCORE_THRESHOLD == Decimal("55")

    def test_golden_threshold_is_68(self):
        assert TECHNICAL_GOLDEN_SCORE_THRESHOLD == Decimal("68")
