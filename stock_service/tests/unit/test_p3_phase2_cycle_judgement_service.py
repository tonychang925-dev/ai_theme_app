from __future__ import annotations

from stock_service.services.cycle_judgement_service import (
    CycleJudgementService,
    ThemeCycleMainlineInput,
    ThemeCycleMarketInput,
    ThemeCycleRecentInput,
)


def _mainline(**overrides):
    base = dict(
        subject_key="9025631",
        theme_name="创新药",
        is_main_theme=True,
        theme_tier="main",
        event_chain_score=21.0,
        event_chain_continuity_score=15.0,
        market_recognition_score=100.0,
        mainline_stability_score=70.0,
        limit_up_count=23,
    )
    base.update(overrides)
    return ThemeCycleMainlineInput(**base)


def _market(**overrides):
    base = dict(
        subject_key="9025631",
        theme_name="创新药",
        limit_up_count=23,
        strong_stock_count=61,
        leader_pct_chg=20.0,
        member_count=80,
        leader_limit_up=True,
    )
    base.update(overrides)
    return ThemeCycleMarketInput(**base)


def _recent(**overrides):
    base = dict(
        subject_key="9025631",
        recent_rank_days=2,
        recent_positive_days=1,
        recent_red_days=1,
        recent_negative_days=0,
    )
    base.update(overrides)
    return ThemeCycleRecentInput(**base)


def test_build_judgement_marks_climax_for_overheated_main_theme():
    service = CycleJudgementService()
    result = service.build_judgement("2026-04-01", _mainline(), _market(), _recent())

    assert result.is_climax is True
    assert result.primary_cycle_stage == "climax"
    assert result.action_bias == "警惕高潮"


def test_build_judgement_marks_fermentation_for_healthy_main_theme():
    service = CycleJudgementService()
    result = service.build_judgement(
        "2026-04-01",
        _mainline(subject_key="9013933", theme_name="共封装光学CPO", market_recognition_score=99.59),
        _market(subject_key="9013933", theme_name="共封装光学CPO", limit_up_count=6, strong_stock_count=20, leader_pct_chg=12.88),
        _recent(subject_key="9013933", recent_rank_days=1, recent_red_days=0),
    )

    assert result.is_fermentation is True
    assert result.primary_cycle_stage == "fermentation"
    assert result.action_bias == "主做"


def test_build_judgement_marks_divergence_when_leader_holds_but_board_weakens():
    service = CycleJudgementService()
    result = service.build_judgement(
        "2026-04-01",
        _mainline(subject_key="9018144", theme_name="PCB印制电路板", market_recognition_score=65.03, mainline_stability_score=50.0),
        _market(subject_key="9018144", theme_name="PCB印制电路板", limit_up_count=2, strong_stock_count=6, leader_pct_chg=10.03),
        _recent(subject_key="9018144", recent_rank_days=1),
    )

    assert result.is_divergence is True
    assert result.primary_cycle_stage == "divergence"
    assert result.action_bias == "关注弱转强"


def test_build_judgement_marks_start_for_non_main_theme_with_logic_but_low_spread():
    service = CycleJudgementService()
    result = service.build_judgement(
        "2026-04-01",
        _mainline(
            subject_key="9064088",
            theme_name="商业航天",
            is_main_theme=False,
            theme_tier="strong_branch",
            event_chain_score=24.0,
            event_chain_continuity_score=12.0,
            market_recognition_score=48.0,
            mainline_stability_score=32.0,
            limit_up_count=1,
        ),
        _market(
            subject_key="9064088",
            theme_name="商业航天",
            limit_up_count=1,
            strong_stock_count=4,
            leader_pct_chg=9.9,
            member_count=6,
            leader_limit_up=True,
        ),
        _recent(subject_key="9064088", recent_rank_days=0, recent_red_days=0),
    )

    assert result.is_start is True
    assert result.primary_cycle_stage == "start"
    assert result.action_bias == "试错"
