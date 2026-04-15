#!/usr/bin/env python3
"""
检查神剑股份历史数据（4/1-4/10）
"""
import asyncio
import asyncpg
from datetime import date, timedelta

async def check():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    stock_id = "002361"
    start_date = date(2026, 4, 1)
    end_date = date(2026, 4, 10)

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    print(f"检查神剑股份 {stock_id} 在 {start_date} 到 {end_date} 期间的数据")
    print("=" * 70)

    query = """
    SELECT trade_date, stock_name, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date >= $2 AND trade_date <= $3
    ORDER BY trade_date ASC
    """

    rows = await conn.fetch(query, stock_id, start_date, end_date)

    if not rows:
        print("未找到任何数据")
        await conn.close()
        return

    # 统计涨停情况
    limit_up_count = 0
    consecutive_limit_up = 0
    max_consecutive = 0
    current_consecutive = 0

    print("日期        涨跌幅    是否涨停   是否龙头   排名  主题")
    print("-" * 70)

    for row in rows:
        pct = float(row['pct_chg'])
        is_limit_up = pct >= 9.9
        is_leader = row['is_leader']
        date_str = row['trade_date'].strftime("%Y-%m-%d")

        # 检查数据是否异常（高低价颠倒）
        high = float(row['high_price'])
        low = float(row['low_price'])
        data_issue = high < low

        print(f"{date_str}  {pct:6.2f}%   {'✅是' if is_limit_up else '❌否':<6}    {'✅是' if is_leader else '❌否':<6}    {row['rank_order']:4}  {row['subject_key']}", end="")
        if data_issue:
            print("  ⚠️ 数据异常：high < low")
        else:
            print()

        # 统计涨停
        if is_limit_up:
            limit_up_count += 1
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    print("\n" + "=" * 70)
    print(f"统计:")
    print(f"  总交易日数: {len(rows)}")
    print(f"  涨停次数: {limit_up_count}")
    print(f"  最长连续涨停: {max_consecutive}")
    print(f"  是否有连续2天以上涨停: {'✅是' if max_consecutive >= 2 else '❌否'}")

    # 检查4/7-4/8的弱转强模式
    date_data = {row['trade_date']: row for row in rows}
    if date(2026, 4, 7) in date_data and date(2026, 4, 8) in date_data:
        pct_0407 = float(date_data[date(2026, 4, 7)]['pct_chg'])
        pct_0408 = float(date_data[date(2026, 4, 8)]['pct_chg'])
        print(f"\n弱转强模式分析（4/7→4/8）:")
        print(f"  4/7涨跌幅: {pct_0407:.2f}%")
        print(f"  4/8涨跌幅: {pct_0408:.2f}%")
        print(f"  是否为弱转强: {'✅是' if pct_0407 < -2.0 and pct_0408 > 9.9 else '❌否'}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())