from __future__ import annotations

from stock_service.models import MarketEnvironmentMetrics
from stock_service.services.market_environment_judgement_service import MarketEnvironmentJudgementService


def _metrics(**overrides):
    base = dict(
        trade_date="2026-04-02",
        up_count=3400,
        down_count=1200,
        flat_count=200,
        advance_decline_ratio=2.8333,
        limit_up_count=82,
        limit_down_count=4,
        limit_up_down_ratio=20.5,
        yesterday_limit_up_open_strength=2.6,
        yesterday_limit_up_open_red_ratio=0.78,
        yesterday_limit_up_premium_ratio=0.72,
        yesterday_limit_up_fade_ratio=0.12,
        yesterday_limit_up_fail_ratio=0.08,
        morning_high_then_fall_count=180,
        morning_high_then_fall_ratio=0.04,
        intraday_fade_count=220,
        intraday_fade_ratio=0.05,
        high_mark_strong_count=6,
        high_mark_weak_count=1,
        market_volume_change_pct=8.5,
        market_avg_open_pct=0.9,
        market_avg_close_pct=1.4,
    )
    base.update(overrides)
    return MarketEnvironmentMetrics(**base)


def test_build_judgement_marks_risk_on_for_strong_market():
    service = MarketEnvironmentJudgementService()
    result = service.build_judgement(_metrics())

    assert result.market_bias == "risk_on"
    assert result.action_bias == "主做"
    assert result.market_health_score >= 75.0


def test_build_judgement_marks_defensive_for_weak_market():
    service = MarketEnvironmentJudgementService()
    result = service.build_judgement(
        _metrics(
            up_count=1300,
            down_count=3000,
            advance_decline_ratio=0.4333,
            limit_up_count=7,
            limit_down_count=28,
            limit_up_down_ratio=0.25,
            yesterday_limit_up_open_red_ratio=0.18,
            yesterday_limit_up_premium_ratio=0.22,
            yesterday_limit_up_fail_ratio=0.58,
            morning_high_then_fall_ratio=0.26,
            intraday_fade_ratio=0.21,
            high_mark_strong_count=1,
            high_mark_weak_count=6,
            market_volume_change_pct=-9.0,
            market_avg_close_pct=-1.2,
        )
    )

    assert result.market_bias == "risk_off"
    assert result.action_bias in {"防守", "放弃"}
    assert result.market_health_score < 60.0


def test_build_judgement_marks_neutral_for_mixed_market():
    service = MarketEnvironmentJudgementService()
    result = service.build_judgement(
        _metrics(
            up_count=2400,
            down_count=2100,
            advance_decline_ratio=1.1429,
            limit_up_count=16,
            limit_down_count=8,
            limit_up_down_ratio=2.0,
            yesterday_limit_up_open_red_ratio=0.46,
            yesterday_limit_up_premium_ratio=0.42,
            yesterday_limit_up_fail_ratio=0.24,
            morning_high_then_fall_ratio=0.12,
            intraday_fade_ratio=0.11,
            high_mark_strong_count=3,
            high_mark_weak_count=2,
            market_volume_change_pct=1.5,
            market_avg_close_pct=0.2,
        )
    )

    assert result.market_bias in {"neutral", "risk_off"}
    assert result.action_bias in {"谨慎试错", "防守"}
    assert len(result.evidence) >= 4


def test_build_evidence_marks_intraday_mode_when_source_version_upgraded():
    service = MarketEnvironmentJudgementService()
    result = service.build_judgement(
        _metrics(source_version="market_environment_metrics.v2.intraday_mixed")
    )

    assert "分钟口径" in result.evidence[3]
