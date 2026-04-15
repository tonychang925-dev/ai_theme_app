#!/usr/bin/env python3
"""
简单的支撑位检测测试
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_support():
    print("🔧 测试支撑位检测...")
    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 直接测试支撑位检测
        print(f"测试神剑股份(002361)在{test_date}的支撑位...")
        result = await builder.analyze_strict_support("002361", 0.0, test_date)

        print(f"\n支撑检测结果:")
        print(f"  has_support: {result['has_support']}")
        print(f"  support_type: {result.get('support_type')}")
        print(f"  support_strength: {result.get('support_strength', 0.0) * 100:.1f}%")
        print(f"  support_count: {result.get('support_count', 0)}")
        print(f"  combined_strength: {result.get('combined_strength', 0.0)}")

        support_types = result.get('support_types', [])
        print(f"\n检测到的支撑类型 ({len(support_types)}):")
        for i, st in enumerate(support_types, 1):
            print(f"  {i}. {st.get('type')} - 强度: {st.get('strength', 0.0)}, 水平: {st.get('level', 0.0):.2f}")

        # 检查是否满足门槛
        support_strength_score = result.get('support_strength', 0.0) * 100.0
        print(f"\n支撑强度分数: {support_strength_score:.1f}/100")
        print(f"是否≥30分: {'✅ 是' if support_strength_score >= 30.0 else '❌ 否'}")

        if support_strength_score >= 30.0:
            print("\n🎯 支撑位检测已解决!")
            print("神剑股份应有有效支撑位，支撑强度足够。")
        else:
            print("\n⚠️ 支撑位强度不足")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test_support())