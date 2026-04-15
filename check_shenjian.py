#!/usr/bin/env python3
"""
检查神剑股份在特定日期的筛选结果
"""
import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strict_weak_to_strong_screening_v2 import StrictWeakToStrongScreener

async def check_stock_on_date(stock_id: str, check_date: date):
    """检查指定股票在指定日期是否被选中"""
    screener = StrictWeakToStrongScreener()
    await screener.connect()

    # 临时重定向打印输出，减少干扰
    import io
    import contextlib
    f = io.StringIO()

    with contextlib.redirect_stdout(f):
        candidates = await screener.screening_strict(check_date)

    await screener.close()

    # 检查股票是否在候选列表中
    found = any(cand['stock_id'] == stock_id for cand in candidates)

    print(f"\n{'='*60}")
    print(f"股票 {stock_id} 在 {check_date} 的筛选结果:")
    print(f"  候选股总数: {len(candidates)}")
    if found:
        print(f"  ✅ 被选中为弱转强候选股")
        # 显示详细信息
        for cand in candidates:
            if cand['stock_id'] == stock_id:
                print(f"     跌幅: {cand['pct_chg']:.1f}%")
                print(f"     涨停模式: {cand['limit_up_pattern']['pattern_type']}")
                print(f"     支撑位: {cand.get('gap_support_level', 0):.2f} ({cand['support_type']})")
                print(f"     主题: {cand['theme_key']}")
                break
    else:
        print(f"  ❌ 未被选中")

    return found

async def main():
    stock_id = "002361"
    dates = [
        date(2026, 4, 7),
        date(2026, 4, 3),
    ]

    for d in dates:
        await check_stock_on_date(stock_id, d)

if __name__ == "__main__":
    asyncio.run(main())