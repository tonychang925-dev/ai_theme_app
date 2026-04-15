#!/usr/bin/env python3
"""
测试优化后的主线周期判断逻辑集成到弱转强选股
验证2026-04-07神剑股份是否成功进入候选池
"""

import asyncio
import sys
import os
from datetime import date
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder


async def test_shenjian_0407():
    """测试2026-04-07神剑股份在增强版构建器中的表现"""
    print("=" * 70)
    print("测试优化后的主线周期判断逻辑集成")
    print("日期: 2026-04-07")
    print("股票: 神剑股份 (002361.SZ)")
    print("=" * 70)

    builder = EnhancedCandidateBuilder()

    try:
        # 设置测试环境
        test_date = date(2026, 4, 7)

        # 获取下一个交易日
        next_trade_date = await builder.resolve_next_trade_date(test_date)
        print(f"测试日期: {test_date}")
        print(f"下一个交易日: {next_trade_date}")

        # 清理测试数据
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            delete_sql = """
            DELETE FROM weak_to_strong_candidate_pool
            WHERE trade_date = $1 OR next_trade_date = $1
            """
            await conn.execute(delete_sql, test_date)
        print("✅ 清理测试数据完成")

        # 1. 首先检查神剑股份的主题周期特征
        print("\n🔍 检查神剑股份主题周期特征...")
        # 从之前的测试得知神剑股份的主题键是9062832
        subject_key = "9062832"
        cycle_features = await builder.fetch_cycle_features(test_date, subject_key)

        print(f"   主题键: {cycle_features.subject_key}")
        print(f"   交易日: {cycle_features.trade_date}")
        print(f"   主线存活: {cycle_features.mainline_alive}")
        print(f"   主线强度评分: {cycle_features.mainline_strength_score:.1f}")
        print(f"   周期状态: {cycle_features.cycle_state}")
        print(f"   退潮观察: {cycle_features.fade_watch}")
        print(f"   退潮确认: {cycle_features.fade_confirmed}")

        # 2. 运行增强构建器
        print("\n🚀 运行增强构建器...")
        result = await builder.build_enhanced(
            test_date,
            next_trade_date=next_trade_date,
            max_formal=35,
            max_observe=15
        )

        # 分类统计
        formal_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "formal"]
        observe_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "observe_only"]

        print(f"📊 扫描股票: {result.total_scanned}")
        print(f"📊 候选总数: {len(result.candidates)}")
        print(f"📊 正式候选: {len(formal_candidates)}")
        print(f"📊 观察候选: {len(observe_candidates)}")
        print(f"📊 插入数量: {result.total_inserted}")

        # 3. 检查神剑股份是否在候选池中
        print("\n🔍 查找神剑股份 (002361.SZ)...")
        shenjian_found = False
        shenjian_candidate = None

        for candidate in result.candidates:
            if candidate.get("stock_id") == "002361.SZ":
                shenjian_found = True
                shenjian_candidate = candidate
                break

        if shenjian_found:
            print("✅ 神剑股份成功进入候选池!")
            print(f"   准入类型: {shenjian_candidate.get('pool_entry_type')}")
            print(f"   候选评分: {shenjian_candidate.get('candidate_score')}")
            print(f"   周期状态: {shenjian_candidate.get('cycle_state')}")
            print(f"   主线强度: {shenjian_candidate.get('mainline_strength_score')}")

            # 显示增强特征
            evidence = json.loads(shenjian_candidate.get("evidence_json", "{}"))
            enhanced = evidence.get("enhanced_features", {})
            if enhanced:
                print(f"   强势背景评分: {enhanced.get('strong_background_score', 0):.1f}")
                print(f"   修复窗口评分: {enhanced.get('repair_window_score', 0):.1f}")
                print(f"   退潮确认: {enhanced.get('fade_confirmed', False)}")
        else:
            print("❌ 神剑股份未进入候选池")

            # 尝试分析原因
            print("\n🔍 分析未入选原因...")
            print(f"   主题周期特征:")
            print(f"     主线存活: {cycle_features.mainline_alive}")
            print(f"     周期状态: {cycle_features.cycle_state}")
            print(f"     退潮观察: {cycle_features.fade_watch}")
            print(f"     退潮确认: {cycle_features.fade_confirmed}")
            print(f"     主线强度评分: {cycle_features.mainline_strength_score:.1f}")

            # 打印部分候选特征，分析筛选标准
            print(f"\n📋 被选中的候选股特征分析 (前10个):")
            for i, cand in enumerate(result.candidates[:10], 1):
                entry_type = cand.get("pool_entry_type", "unknown")
                cycle_state = cand.get("cycle_state", "unknown")
                mainline_alive = cand.get("mainline_alive", False)
                fade_confirmed = cand.get("fade_confirmed", False)

                print(f"   {i:2d}. {cand.get('stock_id')} {cand.get('stock_name')}")
                print(f"      准入: {entry_type}, 周期: {cycle_state}, 主线存活: {mainline_alive}, 退潮确认: {fade_confirmed}")

                # 显示增强评分
                evidence = json.loads(cand.get("evidence_json", "{}"))
                enhanced = evidence.get("enhanced_features", {})
                if enhanced:
                    bg_score = enhanced.get("strong_background_score", 0)
                    repair_score = enhanced.get("repair_window_score", 0)
                    print(f"      评分: 背景{bg_score:.1f}, 修复{repair_score:.1f}")

        # 4. 对比原始构建器
        print("\n" + "="*70)
        print("对比原始构建器表现...")

        original_builder = WeakToStrongCandidateBuilder()
        try:
            original_result = await original_builder.build(
                test_date,
                next_trade_date=next_trade_date,
                max_candidates=50
            )

            original_found = any(c.get("stock_id") == "002361.SZ" for c in original_result.candidates)
            print(f"原始构建器候选数量: {len(original_result.candidates)}")
            print(f"原始构建器中是否包含神剑股份: {'✅ 是' if original_found else '❌ 否'}")
        finally:
            await original_builder.close()

        print("\n" + "="*70)
        print("测试完成!")

        return shenjian_found

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()


async def main():
    print("优化后的主线周期判断逻辑集成测试")
    print("验证2026-04-07神剑股份是否进入弱转强候选池")
    print()

    success = await test_shenjian_0407()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())