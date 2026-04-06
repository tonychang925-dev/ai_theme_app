from __future__ import annotations

from stock_service.services.pre_market_execution_service import (
    ExecutionAuctionSignalInput,
    ExecutionCycleInput,
    ExecutionLeaderInput,
    ExecutionMainlineInput,
    PreMarketExecutionService,
)


def test_build_plan_marks_act_for_mainline_fermentation():
    service = PreMarketExecutionService()
    plan = service.build_plan(
        "2026-04-01",
        "2026-04-02",
        ExecutionMainlineInput("9013933", "共封装光学CPO", True, "main", "主线成立"),
        ExecutionCycleInput("9013933", "fermentation", "主做", "龙头强势", "板块健康", "发酵主做"),
        ExecutionLeaderInput("9013933", "688025", "杰普特", "龙头", 1, 61.14, "低位启动", ("放量突破",)),
    )

    assert plan.source_trade_date == "2026-04-01"
    assert plan.theme_status == "延续"
    assert plan.leader_status == "继续成立"
    assert plan.action_today == "act"
    assert "K线位置 低位启动" in plan.watch_reason
    assert "K线形态 放量突破" in plan.watch_reason


def test_build_plan_marks_watch_for_divergence():
    service = PreMarketExecutionService()
    plan = service.build_plan(
        "2026-04-01",
        "2026-04-02",
        ExecutionMainlineInput("9014072", "光伏", True, "main", "主线成立"),
        ExecutionCycleInput("9014072", "divergence", "关注弱转强", "龙头强势", "板块联动", "分歧观察"),
        ExecutionLeaderInput("9014072", "688726", "拉普拉斯", "龙头", 1, 62.67),
    )

    assert plan.theme_status == "弱化"
    assert plan.leader_status == "弱转强候选"
    assert plan.action_today == "watch"
    assert plan.source_trade_date == "2026-04-01"


def test_build_plan_marks_avoid_for_fade():
    service = PreMarketExecutionService()
    plan = service.build_plan(
        "2026-04-01",
        "2026-04-02",
        ExecutionMainlineInput("9011554", "游戏", False, "strong_branch", "支线观察"),
        ExecutionCycleInput("9011554", "fade", "放弃", "龙头走弱", "板块分化", "退潮放弃"),
        ExecutionLeaderInput("9011554", "002000", "某股", "龙头", 1, 40.0),
    )

    assert plan.theme_status == "证伪"
    assert plan.leader_status == "放弃"
    assert plan.action_today == "avoid"
    assert plan.source_trade_date == "2026-04-01"


def test_build_plan_overrides_action_with_auction_signal():
    service = PreMarketExecutionService()
    plan = service.build_plan(
        "2026-04-02",
        "2026-04-03",
        ExecutionMainlineInput("9064103", "AI光纤", True, "main", "主线成立"),
        ExecutionCycleInput("9064103", "fermentation", "主做", "龙头强势", "板块健康", "发酵主做"),
        ExecutionLeaderInput("9064103", "603042", "华脉科技", "龙头", 1, 61.0),
        ExecutionAuctionSignalInput("603042.SH", "华脉科技", "watch", "弱转强候选", "watch", "", 58.6),
    )

    assert plan.action_today == "watch"
    assert plan.auction_signal_level == "watch"
    assert plan.auction_signal_type == "弱转强候选"


def test_build_plan_appends_hard_reject_reason():
    service = PreMarketExecutionService()
    plan = service.build_plan(
        "2026-04-02",
        "2026-04-03",
        ExecutionMainlineInput("9064103", "AI光纤", True, "main", "主线成立"),
        ExecutionCycleInput("9064103", "fermentation", "主做", "龙头强势", "板块健康", "发酵主做"),
        ExecutionLeaderInput("9064103", "000015", "中利集团", "龙二", 2, 58.0),
        ExecutionAuctionSignalInput("000015.SZ", "中利集团", "invalid", "情绪转弱", "avoid", "低开不及预期", 12.0),
    )

    assert plan.action_today == "avoid"
    assert plan.auction_hard_reject_reason == "低开不及预期"
    assert plan.invalid_conditions[0] == "低开不及预期"
