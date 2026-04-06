from __future__ import annotations

from stock_service.services.mainline_judgement_service import (
    MainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
)


def test_build_judgement_marks_main_theme_when_event_chain_and_market_both_strong():
    service = MainlineJudgementService()
    event_stats = ThemeEventStats(
        subject_key="9064088",
        theme_name="商业航天",
        today_event_count=3,
        recent_event_count=7,
        distinct_event_days=4,
        key_event_count=4,
        sample_summaries=["政策催化", "首飞验证", "商业化落地"],
    )
    market_stats = ThemeMarketStats(
        subject_key="9064088",
        theme_name="商业航天",
        limit_up_count=6,
        strong_stock_count=9,
        leader_pct_chg=10.01,
        member_count=15,
        leader_limit_up=True,
    )

    result = service.build_judgement("2026-04-01", event_stats, market_stats)

    assert result.is_main_theme is True
    assert result.theme_tier == "main"
    assert result.market_recognition_score >= 50
    assert result.event_chain_continuity_score >= 35


def test_build_judgement_marks_strong_branch_when_market_has_heat_but_logic_weaker():
    service = MainlineJudgementService()
    event_stats = ThemeEventStats(
        subject_key="9013933",
        theme_name="共封装光学CPO",
        today_event_count=1,
        recent_event_count=1,
        distinct_event_days=1,
        key_event_count=0,
        sample_summaries=["技术催化"],
    )
    market_stats = ThemeMarketStats(
        subject_key="9013933",
        theme_name="共封装光学CPO",
        limit_up_count=2,
        strong_stock_count=3,
        leader_pct_chg=8.12,
        member_count=5,
        leader_limit_up=True,
    )

    result = service.build_judgement("2026-04-01", event_stats, market_stats)

    assert result.is_main_theme is False
    assert result.theme_tier == "strong_branch"


def test_build_judgement_does_not_mark_main_theme_when_only_market_is_hot():
    service = MainlineJudgementService()
    event_stats = ThemeEventStats(
        subject_key="9049134",
        theme_name="创新药出海",
        today_event_count=0,
        recent_event_count=0,
        distinct_event_days=0,
        key_event_count=0,
        sample_summaries=[],
    )
    market_stats = ThemeMarketStats(
        subject_key="9049134",
        theme_name="创新药出海",
        limit_up_count=14,
        strong_stock_count=29,
        leader_pct_chg=20.0,
        member_count=45,
        leader_limit_up=True,
    )

    result = service.build_judgement("2026-04-01", event_stats, market_stats)

    assert result.is_main_theme is False
    assert result.theme_tier == "strong_branch"


def test_count_key_events_detects_keyword_driven_summaries():
    service = MainlineJudgementService()
    count = service.count_key_events(
        [
            "工信部印发行动计划",
            "行业订单超预期",
            "普通跟风描述",
        ]
    )
    assert count == 2
