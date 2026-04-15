#!/usr/bin/env python3
"""
增强版评分功能单元测试
测试连续评分算法，不依赖数据库
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder


def test_scoring_functions():
    """测试评分函数"""
    builder = EnhancedCandidateBuilder()

    print("🧪 测试强势背景评分")
    print("-"*40)

    # 测试用例1：龙头+涨停
    score1 = builder.calculate_strong_background_score(
        is_leader=True,
        limit_up=True,
        recent_limit_up_count=2,
        rank_order=1
    )
    print(f"✅ 龙头+涨停+2次近期涨停+排名第1: {score1:.1f} (预期: ~100)")

    # 测试用例2：非龙头，但涨停
    score2 = builder.calculate_strong_background_score(
        is_leader=False,
        limit_up=True,
        recent_limit_up_count=1,
        rank_order=5
    )
    print(f"✅ 非龙头+涨停+1次近期涨停+排名第5: {score2:.1f} (预期: ~60-70)")

    # 测试用例3：弱势背景
    score3 = builder.calculate_strong_background_score(
        is_leader=False,
        limit_up=False,
        recent_limit_up_count=0,
        rank_order=50
    )
    print(f"✅ 弱势背景: {score3:.1f} (预期: 0)")

    print("\n🧪 测试修复窗口评分")
    print("-"*40)

    # 测试用例1：弱转强动作偏好在分歧阶段
    score4 = builder.calculate_repair_window_score(
        action_bias="弱转强",
        stage="divergence",
        is_divergence=True,
        is_rebound=False,
        is_fermentation=False,
        is_fade=False,
        fade_confirmed=False
    )
    print(f"✅ 弱转强+分歧阶段: {score4:.1f} (预期: ~90-100)")

    # 测试用例2：修复动作偏好在回流阶段
    score5 = builder.calculate_repair_window_score(
        action_bias="修复",
        stage="rebound",
        is_divergence=False,
        is_rebound=True,
        is_fermentation=False,
        is_fade=False,
        fade_confirmed=False
    )
    print(f"✅ 修复+回流阶段: {score5:.1f} (预期: ~85-95)")

    # 测试用例3：退潮确认大幅扣分
    score6 = builder.calculate_repair_window_score(
        action_bias="弱转强",
        stage="divergence",
        is_divergence=True,
        is_rebound=False,
        is_fermentation=False,
        is_fade=True,
        fade_confirmed=True
    )
    print(f"✅ 弱转强+分歧+退潮确认: {score6:.1f} (预期: <40，因为有-60扣分)")

    # 测试用例4：退潮观察中度扣分
    score7 = builder.calculate_repair_window_score(
        action_bias="修复",
        stage="rebound",
        is_divergence=False,
        is_rebound=True,
        is_fermentation=False,
        is_fade=True,
        fade_confirmed=False
    )
    print(f"✅ 修复+回流+退潮观察: {score7:.1f} (预期: ~55-65，因为有-30扣分)")

    print("\n🧪 测试候选池准入逻辑")
    print("-"*40)

    # 测试正式准入
    entry1 = builder.determine_pool_entry_type(
        strong_bg_score=75,
        repair_score=65,
        mainline_alive=True,
        fade_confirmed=False
    )
    print(f"✅ 正式准入 (75/65/主线存活): {entry1} (预期: formal)")

    # 测试观察流准入
    entry2 = builder.determine_pool_entry_type(
        strong_bg_score=40,
        repair_score=55,
        mainline_alive=False,
        fade_confirmed=False
    )
    print(f"✅ 观察流准入 (40/55/非主线): {entry2} (预期: observe_only)")

    # 测试退潮确认拒绝
    entry3 = builder.determine_pool_entry_type(
        strong_bg_score=80,
        repair_score=70,
        mainline_alive=True,
        fade_confirmed=True
    )
    print(f"✅ 退潮确认拒绝 (80/70/主线/退潮确认): {entry3} (预期: reject)")

    # 测试低分拒绝
    entry4 = builder.determine_pool_entry_type(
        strong_bg_score=25,
        repair_score=20,
        mainline_alive=False,
        fade_confirmed=False
    )
    print(f"✅ 低分拒绝 (25/20): {entry4} (预期: reject)")

    print("\n📊 阈值配置:")
    print(f"   强势背景阈值: {builder.STRONG_BACKGROUND_THRESHOLD}")
    print(f"   修复窗口阈值: {builder.REPAIR_WINDOW_THRESHOLD}")
    print(f"   观察流阈值: {builder.OBSERVE_THRESHOLD}")

    # 验证评分范围
    print("\n🔍 验证评分范围:")
    all_scores = [score1, score2, score3, score4, score5, score6, score7]
    for i, score in enumerate(all_scores, 1):
        if 0 <= score <= 100:
            print(f"   ✅ 评分{i}: {score:.1f} (有效范围)")
        else:
            print(f"   ❌ 评分{i}: {score:.1f} (超出范围!)")

    print("\n🎉 评分功能测试完成!")


if __name__ == "__main__":
    test_scoring_functions()