from __future__ import annotations

from decimal import Decimal
from datetime import date

from stock_processing_service.domain.services.identity_rule_engine import IdentityRuleEngine, IdentityRuleInput
from stock_service.scripts.build_mainline_identity_registry import _decide_identity


def _base_input(**overrides):
    data = dict(
        subject_key="satcom",
        subject_name="卫星互联网",
        heat_latest=Decimal("70"),
        avg_heat_5d=Decimal("66"),
        hot_days_5d=3,
        active_days_10d=5,
        active_days_20d=8,
        his_pct_chg_30d=[Decimal("0.5")] * 30,
        his_pct_chg_latest=Decimal("0.8"),
        strong_event_count_7d=2,
        event_count_3d=2,
        event_count_7d=5,
        event_recency_days=2,
        event_strength_score=Decimal("78"),
        event_continuity_score=Decimal("72"),
        board_stock_count=100,
        limit_up_count=3,
        front_row_strength_score=Decimal("74"),
        front_row_alive_ratio=Decimal("0.68"),
        above_ma10=True,
        above_ma20=True,
        theme_support_score=Decimal("80"),
        theme_ret_10d=Decimal("3"),
        board_boom_days_5d=2,
        net_inflow_sum_5d=Decimal("520000000"),
        net_inflow_days_5d=3,
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
    result = engine.evaluate(
        _base_input(
            active_days_20d=1,
            board_boom_days_5d=0,
            net_inflow_sum_5d=Decimal("0"),
            net_inflow_days_5d=0,
            above_ma10=False,
            above_ma20=False,
            theme_support_score=Decimal("0"),
            theme_ret_10d=Decimal("-10"),
        )
    )

    assert result.rule_is_main_theme is False
    assert result.market_ok is False
    assert any("blocked_by_one_day_tour" in x for x in result.reasons)


def test_identity_rule_engine_fund_condition_failed() -> None:
    engine = IdentityRuleEngine()
    result = engine.evaluate(
        _base_input(
            net_inflow_days_5d=0,
            net_inflow_sum_5d=Decimal("0"),
        )
    )

    assert result.rule_is_main_theme is False
    assert result.market_ok is False
    assert any("fund_condition_failed" in x for x in result.reasons)


def test_identity_rule_engine_matches_legacy_decide_identity() -> None:
    legacy_row = {
        "subject_key": "satcom",
        "theme_name": "卫星互联网",
        "source_trade_date": date(2026, 4, 7),
        "heat_latest": Decimal("70"),
        "avg_heat_5d": Decimal("66"),
        "hot_days_5d": 3,
        "active_days_10d": 5,
        "active_days_20d": 8,
        "his_pct_chg_30d": [Decimal("0.5")] * 30,
        "his_pct_chg_latest": Decimal("0.8"),
        "event_count_3d": 2,
        "event_count_7d": 5,
        "strong_event_count_7d": 2,
        "event_continuity_score": Decimal("72"),
        "event_strength_score": Decimal("78"),
        "event_recency_days": 2,
        "board_stock_count": 100,
        "limit_up_count": 3,
        "front_row_strength_score": Decimal("74"),
        "front_row_alive_ratio": Decimal("0.68"),
        "above_ma10": True,
        "above_ma20": True,
        "theme_support_score": Decimal("80"),
        "theme_ret_10d": Decimal("3"),
        "board_boom_days_5d": 2,
        "net_inflow_sum_5d": Decimal("520000000"),
        "net_inflow_days_5d": 3,
    }

    legacy = _decide_identity(legacy_row)
    current = IdentityRuleEngine().evaluate(
        IdentityRuleInput(
            subject_key=str(legacy_row["subject_key"]),
            subject_name=str(legacy_row["theme_name"]),
            heat_latest=Decimal(str(legacy_row["heat_latest"])),
            avg_heat_5d=Decimal(str(legacy_row["avg_heat_5d"])),
            hot_days_5d=int(legacy_row["hot_days_5d"]),
            active_days_10d=int(legacy_row["active_days_10d"]),
            active_days_20d=int(legacy_row["active_days_20d"]),
            his_pct_chg_30d=list(legacy_row["his_pct_chg_30d"]),
            his_pct_chg_latest=Decimal(str(legacy_row["his_pct_chg_latest"])),
            strong_event_count_7d=int(legacy_row["strong_event_count_7d"]),
            event_count_3d=int(legacy_row["event_count_3d"]),
            event_count_7d=int(legacy_row["event_count_7d"]),
            event_recency_days=int(legacy_row["event_recency_days"]),
            event_strength_score=Decimal(str(legacy_row["event_strength_score"])),
            event_continuity_score=Decimal(str(legacy_row["event_continuity_score"])),
            board_stock_count=int(legacy_row["board_stock_count"]),
            limit_up_count=int(legacy_row["limit_up_count"]),
            front_row_strength_score=Decimal(str(legacy_row["front_row_strength_score"])),
            front_row_alive_ratio=Decimal(str(legacy_row["front_row_alive_ratio"])),
            above_ma10=bool(legacy_row["above_ma10"]),
            above_ma20=bool(legacy_row["above_ma20"]),
            theme_support_score=Decimal(str(legacy_row["theme_support_score"])),
            theme_ret_10d=Decimal(str(legacy_row["theme_ret_10d"])),
            board_boom_days_5d=int(legacy_row["board_boom_days_5d"]),
            net_inflow_sum_5d=Decimal(str(legacy_row["net_inflow_sum_5d"])),
            net_inflow_days_5d=int(legacy_row["net_inflow_days_5d"]),
        )
    )

    assert float(round(current.logic_score, 3)) == legacy.logic_score
    assert float(round(current.market_score, 3)) == legacy.market_score
    assert float(round(current.composite_score, 3)) == legacy.composite_score
    assert current.logic_ok is legacy.logic_ok
    assert current.market_ok is legacy.market_ok
    assert current.rule_is_main_theme is legacy.rule_is_main_theme
    assert current.one_day_tour_flag is legacy.evidence["one_day_tour_flag"]
    assert float(round(current.mainline_continuity_score, 3)) == legacy.evidence["mainline_continuity_score"]
