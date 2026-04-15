#!/usr/bin/env python3
"""
测试4/7日弱转强筛选（使用修复后的缺口逻辑）
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

    test_date = date(2026, 4, 7)
    print(f"测试弱转强筛选（修复后） - {test_date}")
    print("=" * 70)

    candidates = await screener.screening_direct(test_date)

    # 检查神剑股份
    shenjian_found = any(c['stock_id'] == '002361' for c in candidates)
    if shenjian_found:
        print(f"\n✅ 神剑股份被识别为弱转强候选股！")
        # 打印详细原因
        for c in candidates:
            if c['stock_id'] == '002361':
                print(f"  跌幅: {c['pct_chg']:.1f}%, 支撑位: {c.get('gap_support_level', 0):.2f}")
    else:
        print(f"\n❌ 神剑股份未被选中（错误，4/7应回补关键缺口）")
        # 分析原因
        print("\n分析原因:")
        # 检查神剑股份是否满足三个条件
        # 直接调用内部方法检查
        stock_id = "002361"
        # 获取当日数据
        query = """
        SELECT stock_id, stock_name, pct_chg, low_price
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        """
        row = await screener.conn.fetchrow(query, stock_id, test_date)
        if row:
            pct_chg = float(row['pct_chg'])
            current_low = float(row['low_price'])
            print(f"  跌幅: {pct_chg:.1f}%, 最低价: {current_low:.2f}")

    await screener.close()

if __name__ == "__main__":
    asyncio.run(test())