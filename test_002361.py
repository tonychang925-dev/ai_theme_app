#!/usr/bin/env python3
import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strict_weak_to_strong_screening_v2 import StrictWeakToStrongScreener

async def test():
    screener = StrictWeakToStrongScreener()
    await screener.connect()

    test_date = date(2026, 4, 7)
    print(f"测试日期: {test_date}")
    candidates = await screener.screening_strict(test_date)

    print(f"\n总候选股数量: {len(candidates)}")
    shenjian = any(c['stock_id'] == '002361' for c in candidates)
    print(f"神剑股份 (002361) 是否被选中: {'✅ 是' if shenjian else '❌ 否'}")
    if shenjian:
        for c in candidates:
            if c['stock_id'] == '002361':
                print(f"  跌幅: {c['pct_chg']:.1f}%")
                print(f"  涨停模式: {c['limit_up_pattern']['pattern_type']}")
                print(f"  支撑位: {c.get('gap_support_level', 0):.2f} ({c['support_type']})")
                break

    await screener.close()

if __name__ == "__main__":
    asyncio.run(test())