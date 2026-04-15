from stock_service.services.theme_leader_llm_queue_service import (
    ThemeLeaderLlmQueueInput,
    ThemeLeaderLlmQueueService,
)


def test_queue_main_divergence_theme_when_leader_unconfirmed():
    service = ThemeLeaderLlmQueueService()
    decision = service.evaluate(
        ThemeLeaderLlmQueueInput(
            trade_date="2026-04-08",
            subject_key="9064103",
            theme_name="AI光纤",
            theme_tier="main",
            primary_cycle_stage="divergence",
            leader_status="待确认龙头",
            action_bias="关注弱转强",
            candidate_count=4,
            limit_up_count=3,
            top_candidate_score=56.8,
            second_candidate_score=55.9,
            top_is_limit_up=True,
            second_is_limit_up=True,
            top_role_label="龙头",
            second_role_label="龙二",
        )
    )
    assert decision.need_llm_judgement is True
    assert decision.is_trade_focus is True
    assert decision.queue_priority > 0
    assert "分歧阶段" in decision.queue_reason
    assert "龙头状态未确认" in decision.queue_reason


def test_queue_skips_climax_theme():
    service = ThemeLeaderLlmQueueService()
    decision = service.evaluate(
        ThemeLeaderLlmQueueInput(
            trade_date="2026-04-08",
            subject_key="theme:hot",
            theme_name="商业航天",
            theme_tier="main",
            primary_cycle_stage="climax",
            leader_status="确认龙头",
            action_bias="警惕高潮",
            candidate_count=4,
            limit_up_count=4,
            top_candidate_score=78.0,
            second_candidate_score=65.0,
            top_is_limit_up=True,
            second_is_limit_up=True,
            top_role_label="龙头",
            second_role_label="卡位",
        )
    )
    assert decision.need_llm_judgement is False
    assert decision.queue_priority == 0
    assert "非启动/发酵/分歧/弱转强阶段" in decision.queue_reason


def test_queue_skips_clear_theme_without_conflict():
    service = ThemeLeaderLlmQueueService()
    decision = service.evaluate(
        ThemeLeaderLlmQueueInput(
            trade_date="2026-04-08",
            subject_key="theme:clear",
            theme_name="普通分支",
            theme_tier="strong_branch",
            primary_cycle_stage="fermentation",
            leader_status="确认龙头",
            action_bias="可观察",
            candidate_count=1,
            limit_up_count=1,
            top_candidate_score=72.0,
            second_candidate_score=0.0,
            top_is_limit_up=True,
            second_is_limit_up=False,
            top_role_label="龙头",
            second_role_label="",
        )
    )
    assert decision.need_llm_judgement is False
    assert decision.queue_priority == 0
