from __future__ import annotations

from stock_service.services.auction_watch_universe_service import (
    AuctionWatchUniverseService,
    WatchCycleInput,
    WatchLeaderInput,
    WatchMainlineInput,
)


def test_priority_maps_core_roles_to_p1_and_trend_to_p2():
    service = AuctionWatchUniverseService()
    assert service.derive_candidate_priority("龙头") == "P1"
    assert service.derive_candidate_priority("龙二") == "P1"
    assert service.derive_candidate_priority("卡位") == "P1"
    assert service.derive_candidate_priority("强趋势") == "P2"
    assert service.derive_candidate_priority("补涨") == "P3"


def test_is_eligible_allows_mainline_core_roles():
    service = AuctionWatchUniverseService()
    mainline = WatchMainlineInput("9018216", "石油", True, "main")
    cycle = WatchCycleInput("9018216", "fermentation", "主做")
    leader = WatchLeaderInput("9018216", "600001", "测试股", "龙头", 1)
    assert service.is_eligible(mainline, cycle, leader) is True


def test_is_eligible_allows_non_main_theme_only_for_watch_bias():
    service = AuctionWatchUniverseService()
    mainline = WatchMainlineInput("9010001", "支线", False, "strong_branch")
    leader = WatchLeaderInput("9010001", "600002", "测试股", "卡位", 2)
    assert service.is_eligible(mainline, WatchCycleInput("9010001", "start", "关注弱转强"), leader) is True
    assert service.is_eligible(mainline, WatchCycleInput("9010001", "fade", "放弃"), leader) is False


def test_build_item_carries_phase2_context_into_universe_row():
    service = AuctionWatchUniverseService()
    item = service.build_item(
        "2026-04-02",
        "2026-04-03",
        WatchMainlineInput("9018216", "石油", True, "main"),
        WatchCycleInput("9018216", "fermentation", "主做"),
        WatchLeaderInput("9018216", "601872", "招商轮船", "龙二", 2),
    )
    assert item.candidate_priority == "P1"
    assert item.theme_name == "石油"
    assert item.role_label == "龙二"
    assert item.primary_cycle_stage == "fermentation"
