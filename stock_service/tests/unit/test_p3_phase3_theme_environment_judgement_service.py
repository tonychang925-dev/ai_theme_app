from __future__ import annotations

from stock_service.services.theme_environment_judgement_service import (
    ThemeEnvironmentInput,
    ThemeEnvironmentJudgementService,
)


def _input(**overrides):
    base = dict(
        subject_key="9019999",
        theme_name="商业航天",
        theme_tier="main",
        is_main_theme=True,
        primary_cycle_stage="fermentation",
        action_bias="主做",
        limit_up_count=6,
        strong_stock_count=15,
        member_count=24,
        leader_limit_up=True,
        leader_pct_chg=12.5,
    )
    base.update(overrides)
    return ThemeEnvironmentInput(**base)


def test_build_judgement_marks_healthy_board_for_main_theme():
    service = ThemeEnvironmentJudgementService()
    result = service.build_judgement("2026-04-02", _input())

    assert result.board_health_status == "板块健康"
    assert result.board_effect_status == "板块联动明显"
    assert result.leader_support_status == "龙头强带队"
    assert result.follow_strength_status == "后排跟随强"
    assert result.action_bias == "可主做"


def test_build_judgement_marks_overheated_board_when_climax():
    service = ThemeEnvironmentJudgementService()
    result = service.build_judgement(
        "2026-04-02",
        _input(primary_cycle_stage="climax", limit_up_count=12, strong_stock_count=30),
    )

    assert result.board_health_status == "板块过热"
    assert result.action_bias == "警惕高潮"


def test_build_judgement_marks_abandon_when_board_weakens():
    service = ThemeEnvironmentJudgementService()
    result = service.build_judgement(
        "2026-04-02",
        _input(
            theme_tier="strong_branch",
            is_main_theme=False,
            primary_cycle_stage="fade",
            limit_up_count=0,
            strong_stock_count=2,
            member_count=3,
            leader_limit_up=False,
            leader_pct_chg=-3.5,
        ),
    )

    assert result.board_health_status == "板块走弱"
    assert result.leader_support_status == "龙头失速"
    assert result.action_bias == "放弃"
