from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.identity_rule_engine import IdentityRuleEngine, IdentityRuleInput


def _base_input(**overrides):
    data = dict(
        subject_key="satcom",
        subject_name="卫星互联网",
        strong_event_count_7d=2,
        event_count_3d=2,
        event_recency_days=2,
        event_strength_score=Decimal("78"),
        event_continuity_score=Decimal("72"),
        heat_latest=Decimal("70"),
        avg_heat_5d=Decimal("66"),
        limit_up_count=3,
        limit_up_ratio_today=Decimal("0.03"),
        board_boom_days_5d=2,
        front_row_strength_score=Decimal("74"),
        front_row_alive_ratio=Decimal("0.68"),
        net_inflow_sum_5d=Decimal("520000000"),
        net_inflow_days_5d=3,
        one_day_tour_flag=False,
        kline_support_hold=True,
        platform_breakout_flag=False,
    )
    data.update(overrides)
    return IdentityRuleInput(**data)


def test_identity_rule_engine_main_theme_pass() -> None:
    engine = IdentityRuleEngine()
    result = engine.evaluate(_base_input())

    assert result.rule_is_main_theme is True
    assert result.logic_ok is True
    assert result.market_ok is True
    assert result.composite_score > Decimal("60")


def test_identity_rule_engine_blocked_by_one_day_tour() -> None:
    engine = IdentityRuleEngine()
    result = engine.evaluate(_base_input(one_day_tour_flag=True))

    assert result.rule_is_main_theme is False
    assert result.market_ok is False
    assert any("blocked_by_one_day_tour" in x for x in result.reasons)


def test_identity_rule_engine_fund_condition_failed() -> None:
    engine = IdentityRuleEngine()
    result = engine.evaluate(
        _base_input(
            net_inflow_days_5d=0,
            net_inflow_sum_5d=Decimal("0"),
            kline_support_hold=False,
            platform_breakout_flag=False,
        )
    )

    assert result.rule_is_main_theme is False
    assert result.market_ok is False
    assert any("fund_condition_failed" in x for x in result.reasons)
