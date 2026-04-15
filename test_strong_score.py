#!/usr/bin/env python3
"""测试强势背景评分计算"""
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

def test_strong_score():
    builder = EnhancedCandidateBuilder()

    # 测试神剑股份情况
    is_leader = False
    limit_up = False
    recent_limit_up_count = 4
    rank_order = 12

    score = builder.calculate_strong_background_score(
        is_leader, limit_up, recent_limit_up_count, rank_order
    )

    print(f"神剑股份强势背景评分:")
    print(f"  is_leader: {is_leader}")
    print(f"  limit_up: {limit_up}")
    print(f"  recent_limit_up_count: {recent_limit_up_count}")
    print(f"  rank_order: {rank_order}")
    print(f"  计算得分: {score}")
    print(f"  正式准入阈值: {builder.STRONG_BACKGROUND_THRESHOLD}")
    print(f"  是否达到正式准入: {score >= builder.STRONG_BACKGROUND_THRESHOLD}")

    # 测试其他情况
    print(f"\n其他测试案例:")
    test_cases = [
        (False, False, 0, 999, "无涨停"),
        (False, False, 1, 999, "1个涨停"),
        (False, False, 2, 999, "2个涨停"),
        (False, False, 3, 999, "3个涨停"),
        (False, False, 4, 999, "4个涨停"),
        (False, False, 5, 999, "5个涨停"),
        (True, False, 0, 999, "龙头无涨停"),
        (False, True, 0, 999, "当日涨停"),
        (False, False, 2, 2, "排名第2"),
    ]

    for is_leader, limit_up, count, rank, desc in test_cases:
        s = builder.calculate_strong_background_score(is_leader, limit_up, count, rank)
        print(f"  {desc}: {s}分")

if __name__ == "__main__":
    test_strong_score()