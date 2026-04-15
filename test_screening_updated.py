#!/usr/bin/env python3
"""
测试更新后的screening()方法（使用新的支撑位识别逻辑）
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_weak_to_strong_screening import EnhancedWeakToStrongScreener

async def test_date(test_date, expected_shenjian_selected):
    screener = EnhancedWeakToStrongScreener()
    await screener.connect()

    print(f"测试弱转强筛选（screening方法） - {test_date}")
    print("=" * 70)

    candidates = await screener.screening(test_date)

    # 检查神剑股份
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)

    if shenjian_found:
        print(f"\n神剑股份被识别为弱转强候选股！")
        for c in candidates:
            if c['stock_id'] == '002361':
                print(f"  跌幅: {c['pct_chg']:.1f}%, 支撑位: {c.get('gap_support_level', 0):.2f}, 支撑类型: {c.get('support_type', 'unknown')}")
    else:
        print(f"\n神剑股份未被选中")

    # 验证是否符合预期
    if shenjian_found == expected_shenjian_selected:
        print(f"✅ 结果符合预期")
    else:
        print(f"❌ 结果不符合预期: 期望{'选中' if expected_shenjian_selected else '拒绝'}, 实际{'选中' if shenjian_found else '拒绝'}")

    await screener.close()
    return shenjian_found == expected_shenjian_selected

async def main():
    # 测试4月7日（应选中）
    print("\n1. 测试4月7日（神剑股份应被选中）")
    print("=" * 70)
    result1 = await test_date(date(2026, 4, 7), True)

    # 测试4月3日（应拒绝）
    print("\n\n2. 测试4月3日（神剑股份应被拒绝）")
    print("=" * 70)
    result2 = await test_date(date(2026, 4, 3), False)

    print("\n" + "=" * 70)
    print("测试总结:")
    print(f"  4月7日测试: {'通过' if result1 else '失败'}")
    print(f"  4月3日测试: {'通过' if result2 else '失败'}")
    print(f"  总体结果: {'✅ 所有测试通过' if result1 and result2 else '❌ 有测试失败'}")

if __name__ == "__main__":
    asyncio.run(main())