#!/usr/bin/env python3
"""
测试4/3日弱转强筛选
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
    print(f"测试弱转强筛选 - {test_date}")
    print("=" * 70)

    candidates = await screener.screening_direct(test_date)

    # 检查神剑股份
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)
    if shenjian_found:
        print(f"\n❌ 神剑股份被误判为弱转强候选股（不应该，因为4/3未回补缺口）")
    else:
        print(f"\n✅ 神剑股份未被选中（正确，4/3未回补缺口）")

    await screener.close()

if __name__ == "__main__":
    asyncio.run(test())