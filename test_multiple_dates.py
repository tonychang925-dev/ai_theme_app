#!/usr/bin/env python3
"""
测试多个日期的严格弱转强筛选结果
"""
import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strict_weak_to_strong_screening_v2 import StrictWeakToStrongScreener

async def test_date(test_date: date):
    """测试指定日期的筛选结果"""
    screener = StrictWeakToStrongScreener()
    await screener.connect()

    # 临时重定向打印输出，减少干扰
    import io
    import contextlib
    f = io.StringIO()

    with contextlib.redirect_stdout(f):
        candidates = await screener.screening_strict(test_date)

    await screener.close()

    print(f"\n{'='*60}")
    print(f"测试日期: {test_date}")
    print(f"候选股总数: {len(candidates)}")
    print(f"候选股列表:")
    for i, cand in enumerate(candidates, 1):
        pattern_type = cand['limit_up_pattern']['pattern_type']
        support_level = cand.get('gap_support_level', 0)
        print(f"  {i:2d}. {cand['stock_id']} {cand['stock_name']}")
        print(f"      跌幅: {cand['pct_chg']:.1f}%, {pattern_type}")
        print(f"      支撑位: {support_level:.2f} ({cand['support_type']}), 主题: {cand['theme_key']}")

    # 检查神剑股份是否在列表中
    shenjian = any(c['stock_id'] == '002361' for c in candidates)
    if shenjian:
        print(f"\n神剑股份 (002361) 被选中: ✅")
        for c in candidates:
            if c['stock_id'] == '002361':
                print(f"  跌幅: {c['pct_chg']:.1f}%")
                print(f"  涨停模式: {c['limit_up_pattern']['pattern_type']}")
                print(f"  支撑位: {c.get('gap_support_level', 0):.2f} ({c['support_type']})")
                break
    else:
        print(f"\n神剑股份 (002361) 未被选中: ❌")

    return len(candidates)

async def main():
    test_dates = [
        date(2026, 4, 3),
        date(2026, 4, 7),
        date(2026, 4, 8),
        date(2026, 4, 9),
        date(2026, 4, 10),
    ]

    total_candidates = 0
    for d in test_dates:
        count = await test_date(d)
        total_candidates += count

    print(f"\n{'='*60}")
    print(f"测试日期范围: {test_dates[0]} 至 {test_dates[-1]}")
    print(f"总候选股数: {total_candidates}")
    print(f"平均每天候选股数: {total_candidates / len(test_dates):.1f}")

if __name__ == "__main__":
    asyncio.run(main())