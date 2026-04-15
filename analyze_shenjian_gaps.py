#!/usr/bin/env python3
"""
分析神剑股份的历史缺口
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date, timedelta
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def analyze_historical_gaps():
    stock_id = "002361"
    analysis_date = date(2026, 4, 7)

    print(f"分析神剑股份历史缺口 - {stock_id} - {analysis_date}")
    print("=" * 80)

    # 连接数据库
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    # 获取最近30天的数据
    query = """
    SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1
      AND trade_date <= $2
      AND trade_date >= $2 - INTERVAL '30 days'
    ORDER BY trade_date ASC
    """
    rows = await conn.fetch(query, stock_id, analysis_date)

    print(f"获取到{len(rows)}天的历史数据")

    if len(rows) < 2:
        print("数据不足，无法分析缺口")
        await conn.close()
        return

    # 分析缺口
    gaps = []
    for i in range(1, len(rows)):
        prev = rows[i-1]
        curr = rows[i]

        prev_close = float(prev['close_price']) if prev['close_price'] else 0
        curr_open = float(curr['open_price']) if curr['open_price'] else 0
        prev_high = float(prev['high_price']) if prev['high_price'] else 0
        curr_low = float(curr['low_price']) if curr['low_price'] else 0

        if prev_close <= 0 or curr_open <= 0:
            continue

        # 检查向上缺口
        if curr_open > prev_close * 1.001:  # 0.1%阈值
            gap_size = (curr_open - prev_close) / prev_close * 100
            gap_info = {
                'date': curr['trade_date'],
                'type': 'up',
                'gap_range': (prev_close, curr_open),
                'size_pct': gap_size,
                'prev_close': prev_close,
                'curr_open': curr_open
            }
            gaps.append(gap_info)

        # 检查向下缺口
        if curr_open < prev_close * 0.999:  # 0.1%阈值
            gap_size = (prev_close - curr_open) / prev_close * 100
            gap_info = {
                'date': curr['trade_date'],
                'type': 'down',
                'gap_range': (curr_open, prev_close),
                'size_pct': gap_size,
                'prev_close': prev_close,
                'curr_open': curr_open
            }
            gaps.append(gap_info)

    print(f"\n发现 {len(gaps)} 个缺口:")
    for i, gap in enumerate(gaps, 1):
        print(f"  {i}. {gap['date']}: {gap['type']}缺口, 大小: {gap['size_pct']:.2f}%")
        print(f"     范围: [{gap['gap_range'][0]:.2f}, {gap['gap_range'][1]:.2f}]")

    # 获取分析日期的价格
    analysis_day_query = """
    SELECT low_price, high_price, close_price
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    """
    analysis_row = await conn.fetchrow(analysis_day_query, stock_id, analysis_date)

    if analysis_row:
        current_low = float(analysis_row['low_price']) if analysis_row['low_price'] else 0
        current_high = float(analysis_row['high_price']) if analysis_row['high_price'] else 0

        print(f"\n分析日({analysis_date})价格:")
        print(f"  最低价: {current_low:.2f}")
        print(f"  最高价: {current_high:.2f}")

        # 检查是否回补了关键缺口
        if gaps:
            # 找出所有向上缺口（突破缺口）
            up_gaps = [g for g in gaps if g['type'] == 'up']

            print(f"\n向上缺口分析 ({len(up_gaps)}个):")
            for i, gap in enumerate(up_gaps, 1):
                gap_lower = gap['gap_range'][0]
                gap_upper = gap['gap_range'][1]

                # 检查是否回补缺口
                if current_low <= gap_lower:
                    print(f"  {i}. ✅ 已回补缺口: {gap['date']}")
                    print(f"     缺口范围: [{gap_lower:.2f}, {gap_upper:.2f}], 大小: {gap['size_pct']:.2f}%")
                    print(f"     当前最低价{current_low:.2f} ≤ 缺口下沿{gap_lower:.2f}")
                else:
                    print(f"  {i}. ❌ 未回补缺口: {gap['date']}")
                    print(f"     缺口范围: [{gap_lower:.2f}, {gap_upper:.2f}], 大小: {gap['size_pct']:.2f}%")
                    print(f"     当前最低价{current_low:.2f} > 缺口下沿{gap_lower:.2f}")

        # 找出最相关的缺口（通常是最早的显著向上缺口）
        if up_gaps:
            # 按日期排序，选择最早的缺口
            up_gaps.sort(key=lambda x: x['date'])
            key_gap = up_gaps[0]
            gap_lower = key_gap['gap_range'][0]

            print(f"\n关键缺口分析:")
            print(f"  最早向上缺口: {key_gap['date']}, 大小: {key_gap['size_pct']:.2f}%")
            print(f"  缺口下沿: {gap_lower:.2f}")
            print(f"  当前最低价: {current_low:.2f}")

            if current_low <= gap_lower:
                print(f"  ✅ 已到达关键缺口支撑!")
                print(f"  支撑位: {gap_lower:.2f}")
            else:
                print(f"  ❌ 未到达关键缺口支撑")
                print(f"  当前价{current_low:.2f} > 缺口下沿{gap_lower:.2f}, 还差{(current_low - gap_lower):.2f}")

    # 显示完整的历史数据
    print(f"\n完整历史数据 (最近{len(rows)}天):")
    print("-" * 80)
    for i, row in enumerate(rows):
        trade_date = row['trade_date']
        open_price = float(row['open_price']) if row['open_price'] else 0
        close_price = float(row['close_price']) if row['close_price'] else 0
        pct_chg = float(row['pct_chg']) if row['pct_chg'] else 0

        mark = "➡️ " if trade_date == analysis_date else "  "
        print(f"{mark}{trade_date}: 开盘{open_price:.2f}, 收盘{close_price:.2f}, 涨跌幅{pct_chg:.1f}%")

    await conn.close()

async def main():
    try:
        await analyze_historical_gaps()
    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())