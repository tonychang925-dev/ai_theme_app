#!/usr/bin/env python3
"""
测试4/10日的弱转强筛选，找出所有具备弱转强的股票
"""
import asyncio
import sys
import os
from datetime import date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_weak_to_strong_screening import EnhancedWeakToStrongScreener

async def test_0410_weak_to_strong():
    """测试4/10日的弱转强筛选"""
    print("测试4/10日弱转强筛选 - 找出所有具备弱转强的股票")
    print("=" * 80)

    screener = EnhancedWeakToStrongScreener()
    await screener.connect()

    # 测试日期：4/10日
    test_date = date(2026, 4, 10)

    print(f"执行直接弱转强筛选 - {test_date}")
    print("-" * 80)

    # 执行直接筛选
    candidates = await screener.screening_direct(test_date)

    print("\n" + "=" * 80)
    print("筛选结果总结:")
    print(f"  总候选股数量: {len(candidates)}")

    if candidates:
        print("\n候选股详细列表:")
        for i, cand in enumerate(candidates, 1):
            stock_id = cand['stock_id']
            stock_name = cand['stock_name']
            pct_chg = cand['pct_chg']
            pattern_type = cand['limit_up_pattern']['pattern_type']
            support_type = cand['support_type']
            support_level = cand.get('gap_support_level', 0)
            theme_key = cand['theme_key']

            print(f"  {i:2d}. {stock_id} {stock_name}:")
            print(f"     跌幅: {pct_chg:.1f}%, 涨停模式: {pattern_type}")
            print(f"     支撑位: {support_level:.2f} ({support_type}), 主题: {theme_key}")

            # 显示技术信号（如果有）
            gap_analysis = cand.get('gap_analysis', {})
            tech_signals = gap_analysis.get('technical_signals', [])
            if tech_signals:
                print(f"     技术信号: {tech_signals[0]}")
            print()
    else:
        print("  未找到弱转强候选股")

    # 检查神剑股份是否在候选股中
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)
    print(f"\n神剑股份(002361)检测结果: {'✅ 被识别为弱转强候选股' if shenjian_found else '❌ 未被识别'}")

    await screener.close()

async def main():
    try:
        await test_0410_weak_to_strong()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())