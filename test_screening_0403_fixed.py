#!/usr/bin/env python3
"""
测试4/3日弱转强筛选（使用修复后的缺口逻辑）
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_weak_to_strong_screening import EnhancedWeakToStrongScreener

async def test():
    screener = EnhancedWeakToStrongScreener()
    await screener.connect()

    test_date = date(2026, 4, 3)
    print(f"测试弱转强筛选（修复后） - {test_date}")
    print("=" * 70)

    candidates = await screener.screening_direct(test_date)

    # 检查神剑股份
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)
    if shenjian_found:
        print(f"\n❌ 神剑股份被误判为弱转强候选股（不应该，因为4/3未回补关键缺口）")
        # 打印详细原因
        for c in candidates:
            if c['stock_id'] == '002361':
                print(f"  跌幅: {c['pct_chg']:.1f}%, 支撑位: {c.get('gap_support_level', 0):.2f}")
    else:
        print(f"\n✅ 神剑股份未被选中（正确，4/3未回补关键缺口）")

    await screener.close()

if __name__ == "__main__":
    asyncio.run(test())