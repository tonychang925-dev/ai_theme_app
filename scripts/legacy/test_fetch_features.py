#!/usr/bin/env python3
"""测试enhanced_candidate_builder的fetch_cycle_features方法（LEGACY，建议改用 analyze_stock_w2s.py）。"""

import asyncio
import sys
import os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder


async def test_fetch_features():
    """测试获取周期特征"""
    print("🧪 测试fetch_cycle_features方法")
    print("="*60)

    builder = EnhancedCandidateBuilder()

    try:
        # 测试一个已知有数据的主题和日期
        # 从之前的检查看，theme_cycle_judgement表有主题"1"在2026-04-13的数据
        test_date = date(2026, 4, 13)
        test_subject = "1"  # 从样本数据看到的主题键

        print(f"📅 测试日期: {test_date}")
        print(f"🎯 测试主题: {test_subject}")

        print("\n🔍 获取周期特征...")
        features = await builder.fetch_cycle_features(test_date, test_subject)

        print(f"\n📊 获取到的特征:")
        print(f"   主题键: {features.subject_key}")
        print(f"   交易日: {features.trade_date}")
        print(f"   主线存活: {features.mainline_alive}")
        print(f"   主线强度评分: {features.mainline_strength_score:.1f}")
        print(f"   周期状态: {features.cycle_state}")
        print(f"   退潮观察: {features.fade_watch}")
        print(f"   退潮确认: {features.fade_confirmed}")
        print(f"   前一周期状态: {features.previous_cycle_state}")

        # 验证特征是否合理
        if features.subject_key == test_subject and features.trade_date == test_date:
            print("\n✅ 特征获取成功!")
        else:
            print("\n⚠ 特征数据可能有问题")

        # 测试另一个主题和日期
        print("\n" + "="*60)
        print("🔍 测试另一个主题...")

        # 尝试主题"129"，也从样本数据看到过
        test_subject2 = "129"
        features2 = await builder.fetch_cycle_features(test_date, test_subject2)

        print(f"📊 主题 {test_subject2} 的特征:")
        print(f"   主线存活: {features2.mainline_alive}")
        print(f"   主线强度评分: {features2.mainline_strength_score:.1f}")
        print(f"   周期状态: {features2.cycle_state}")
        print(f"   退潮确认: {features2.fade_confirmed}")

        # 检查是否从V2表或原表获取
        print("\n📋 数据源分析:")
        print(f"   V2表查询: {'theme_cycle_judgement_v2' if hasattr(features, 'source') else '回退到原表'}")
        print(f"   原表查询: theme_cycle_judgement")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()


async def test_table_exists():
    """检查表是否存在"""
    print("\n" + "="*60)
    print("🔍 检查表结构...")

    builder = EnhancedCandidateBuilder()
    try:
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            tables = ["theme_cycle_judgement_v2", "theme_cycle_judgement"]
            for table in tables:
                sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
                """
                exists = await conn.fetchval(sql, table)
                print(f"   {table}: {'✅ 存在' if exists else '❌ 不存在'}")

                if exists and table == "theme_cycle_judgement":
                    # 检查行数
                    count_sql = f"SELECT COUNT(*) FROM {table}"
                    count = await conn.fetchval(count_sql)
                    print(f"       行数: {count}")

                    # 检查主题"1"的数据
                    sample_sql = """
                    SELECT
                        trade_date,
                        subject_key,
                        final_mainline_alive AS mainline_alive,
                        final_cycle_state AS cycle_state,
                        fade_confirmed
                    FROM theme_cycle_judgement_v2
                    WHERE subject_key = '1' AND trade_date = '2026-04-13'
                    LIMIT 1
                    """
                    sample = await conn.fetchrow(sample_sql)
                    if sample:
                        print(
                            f"       样本数据: 主线存活={sample['mainline_alive']}, "
                            f"阶段={sample['cycle_state']}, 退潮确认={sample['fade_confirmed']}"
                        )
    finally:
        await builder.close()


async def main():
    print("增强候选构建器特征获取测试")
    print("="*60)
    print("[LEGACY] 建议改用: .venv/bin/python scripts/analyze_stock_w2s.py --stock-code 002361 --trade-date 2026-04-07")

    # 检查表结构
    await test_table_exists()

    # 测试特征获取
    success = await test_fetch_features()

    print("\n" + "="*60)
    if success:
        print("✅ 所有测试完成!")
    else:
        print("❌ 测试失败!")


if __name__ == "__main__":
    asyncio.run(main())
