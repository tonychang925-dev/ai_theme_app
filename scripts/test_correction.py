#!/usr/bin/env python3
"""测试周期状态修正逻辑"""

import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test():
    builder = EnhancedCandidateBuilder()
    test_date = date(2026, 4, 7)
    subject_key = "9062832"  # 安徽商业航天

    try:
        # 获取周期特征
        cycle_features = await builder.fetch_cycle_features(test_date, subject_key)

        print("周期特征:")
        print(f"  主题键: {cycle_features.subject_key}")
        print(f"  主线存活: {cycle_features.mainline_alive}")
        print(f"  主线强度评分: {cycle_features.mainline_strength_score}")
        print(f"  周期状态: {cycle_features.cycle_state}")
        print(f"  退潮观察: {cycle_features.fade_watch}")
        print(f"  退潮确认: {cycle_features.fade_confirmed}")

        # 模拟一个row数据（基于实际数据）
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            # 获取神剑股份的基础数据
            sql = """
            SELECT s.*,
                c.primary_cycle_stage,
                c.action_bias,
                c.is_divergence,
                c.is_rebound,
                c.is_fermentation,
                c.is_fade,
                m.is_main_theme
            FROM subject_stock_daily_snapshot s
            LEFT JOIN theme_mainline_judgement m
              ON m.trade_date = s.trade_date
             AND m.subject_key = s.subject_key
            LEFT JOIN theme_cycle_judgement c
              ON c.trade_date = s.trade_date
             AND c.subject_key = s.subject_key
            WHERE s.trade_date = $1::date
              AND s.stock_id LIKE '%002361%'
              AND s.subject_key = $2
            LIMIT 1
            """
            row = await conn.fetchrow(sql, test_date, subject_key)

            if row:
                print("\n原始row数据:")
                print(f"  stock_id: {row['stock_id']}")
                print(f"  pct_chg: {row['pct_chg']}")
                print(f"  limit_up: {row['limit_up']}")
                print(f"  is_leader: {row['is_leader']}")
                print(f"  rank_order: {row['rank_order']}")
                print(f"  primary_cycle_stage: {row['primary_cycle_stage']}")
                print(f"  action_bias: {row['action_bias']}")
                print(f"  is_fade: {row['is_fade']}")
                print(f"  is_main_theme: {row['is_main_theme']}")

                # 测试_to_enhanced_candidate方法
                next_date = date(2026, 4, 8)
                candidate = builder._to_enhanced_candidate(row, test_date, next_date, cycle_features)

                if candidate:
                    print("\n✅ 成功构建候选!")
                    print(f"  准入类型: {candidate.get('pool_entry_type')}")
                    print(f"  候选评分: {candidate.get('candidate_score')}")
                    print(f"  周期状态: {candidate.get('cycle_state')}")
                    print(f"  退潮确认: {candidate.get('fade_confirmed')}")

                    # 检查增强特征
                    import json
                    evidence = json.loads(candidate.get("evidence_json", "{}"))
                    enhanced = evidence.get("enhanced_features", {})
                    print(f"  强势背景评分: {enhanced.get('strong_background_score', 0):.1f}")
                    print(f"  修复窗口评分: {enhanced.get('repair_window_score', 0):.1f}")
                else:
                    print("\n❌ 未能构建候选")
            else:
                print("未找到神剑股份数据")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())