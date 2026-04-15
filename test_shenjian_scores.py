#!/usr/bin/env python3
"""测试神剑股份评分计算"""
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

def test_scores():
    builder = EnhancedCandidateBuilder()

    # 神剑股份数据
    is_leader = False
    limit_up = False
    recent_limit_up_count = 4
    rank_order = 12

    action_bias = "关注弱转强"
    stage = "divergence"
    is_divergence = True
    is_rebound = False
    is_fermentation = False
    is_fade = False  # parent_row中设置为False
    fade_confirmed = False  # cycle_features.fade_confirmed

    # 计算评分
    strong_bg_score = builder.calculate_strong_background_score(
        is_leader, limit_up, recent_limit_up_count, rank_order
    )

    repair_score = builder.calculate_repair_window_score(
        action_bias, stage, is_divergence, is_rebound, is_fermentation,
        is_fade, fade_confirmed
    )

    # 确定准入类型
    mainline_alive = False  # cycle_features.mainline_alive
    entry_type = builder.determine_pool_entry_type(
        strong_bg_score, repair_score, mainline_alive, fade_confirmed
    )

    print("神剑股份评分计算:")
    print("=" * 50)
    print(f"强势背景评分:")
    print(f"  is_leader: {is_leader}")
    print(f"  limit_up: {limit_up}")
    print(f"  recent_limit_up_count: {recent_limit_up_count}")
    print(f"  rank_order: {rank_order}")
    print(f"  得分: {strong_bg_score}")
    print(f"  阈值({builder.STRONG_BACKGROUND_THRESHOLD}): {strong_bg_score >= builder.STRONG_BACKGROUND_THRESHOLD}")

    print(f"\n修复窗口评分:")
    print(f"  action_bias: {action_bias}")
    print(f"  stage: {stage}")
    print(f"  is_divergence: {is_divergence}")
    print(f"  is_rebound: {is_rebound}")
    print(f"  is_fermentation: {is_fermentation}")
    print(f"  is_fade: {is_fade}")
    print(f"  fade_confirmed: {fade_confirmed}")
    print(f"  得分: {repair_score}")
    print(f"  阈值({builder.REPAIR_WINDOW_THRESHOLD}): {repair_score >= builder.REPAIR_WINDOW_THRESHOLD}")

    print(f"\n其他条件:")
    print(f"  mainline_alive: {mainline_alive}")
    print(f"  fade_confirmed: {fade_confirmed}")

    print(f"\n准入类型: {entry_type}")
    print(f"  正式准入条件:")
    print(f"    strong_bg_score >= {builder.STRONG_BACKGROUND_THRESHOLD}: {strong_bg_score >= builder.STRONG_BACKGROUND_THRESHOLD}")
    print(f"    repair_score >= {builder.REPAIR_WINDOW_THRESHOLD}: {repair_score >= builder.REPAIR_WINDOW_THRESHOLD}")
    print(f"    not fade_confirmed: {not fade_confirmed}")
    print(f"    全部满足: {strong_bg_score >= builder.STRONG_BACKGROUND_THRESHOLD and repair_score >= builder.REPAIR_WINDOW_THRESHOLD and not fade_confirmed}")

    print(f"\n观察准入条件:")
    print(f"  not fade_confirmed: {not fade_confirmed}")
    print(f"  strong_bg_score >= {builder.OBSERVE_THRESHOLD}: {strong_bg_score >= builder.OBSERVE_THRESHOLD}")
    print(f"  repair_score >= {builder.OBSERVE_THRESHOLD}: {repair_score >= builder.OBSERVE_THRESHOLD}")

if __name__ == "__main__":
    test_scores()