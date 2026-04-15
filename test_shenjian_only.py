#!/usr/bin/env python3
"""
只测试神剑股份的增强支撑位检测
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian_enhanced_support():
    """测试神剑股份的增强支撑位检测"""
    print("测试神剑股份(002361)增强支撑位检测")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()

    # 测试日期：4月7日（弱转强发生日）
    test_date = date(2026, 4, 7)
    stock_id = "002361"

    try:
        # 使用增强版支撑位分析
        print(f"分析 {stock_id} 在 {test_date} 的支撑位...")
        support_analysis = await builder.analyze_strict_support(stock_id, 0.0, test_date)

        # 打印结果
        print(f"has_support: {support_analysis.get('has_support')}")
        print(f"support_type: {support_analysis.get('support_type')}")
        print(f"support_strength: {support_analysis.get('support_strength'):.3f} (0.0-1.0)")
        print(f"support_count: {support_analysis.get('support_count')}")
        print(f"primary_type: {support_analysis.get('primary_type')}")
        print(f"combined_strength: {support_analysis.get('combined_strength'):.3f}")
        print(f"is_gap_support: {support_analysis.get('is_gap_support')}")

        # 打印所有支撑类型
        support_types = support_analysis.get('support_types', [])
        print(f"\n检测到的支撑类型 ({len(support_types)} 种):")
        for i, st in enumerate(support_types, 1):
            print(f"  {i}. type: {st.get('type')}, strength: {st.get('strength'):.3f}, "
                  f"level: {st.get('level', 0.0):.2f}, "
                  f"desc: {st.get('description', '')}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    """主测试函数"""
    await test_shenjian_enhanced_support()

if __name__ == "__main__":
    asyncio.run(main())