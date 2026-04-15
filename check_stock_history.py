#!/usr/bin/env python3
"""
检查神剑股份的历史数据量
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def check_stock_history():
    stock_id = "002361"
    test_date = date(2026, 4, 7)

    print(f"检查神剑股份({stock_id})历史数据量 - {test_date}")
    print("=" * 60)

    # 连接数据库
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    # 检查数据表是否存在
    check_table_query = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'subject_stock_daily_snapshot'
    );
    """
    table_exists = await conn.fetchval(check_table_query)
    print(f"数据表 subject_stock_daily_snapshot 是否存在: {table_exists}")

    if not table_exists:
        print("❌ 数据表不存在")
        await conn.close()
        return

    # 检查股票在表中是否存在
    check_stock_query = """
    SELECT COUNT(*) as count
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1
    """
    stock_count = await conn.fetchval(check_stock_query, stock_id)
    print(f"神剑股份总数据条数: {stock_count}")

    # 检查特定日期附近的数据
    check_date_range_query = """
    SELECT
        COUNT(*) as total_count,
        MIN(trade_date) as earliest_date,
        MAX(trade_date) as latest_date
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date <= $2
    """
    date_range = await conn.fetchrow(check_date_range_query, stock_id, test_date)

    if date_range:
        print(f"  在{test_date}之前的数据条数: {date_range['total_count']}")
        print(f"  最早日期: {date_range['earliest_date']}")
        print(f"  最新日期: {date_range['latest_date']}")

    # 检查具体某天的数据
    check_specific_day_query = """
    SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    """
    specific_day_data = await conn.fetchrow(check_specific_day_query, stock_id, test_date)

    if specific_day_data:
        print(f"\n{test_date}当日数据:")
        print(f"  开盘价: {specific_day_data['open_price']:.2f}")
        print(f"  最高价: {specific_day_data['high_price']:.2f}")
        print(f"  最低价: {specific_day_data['low_price']:.2f}")
        print(f"  收盘价: {specific_day_data['close_price']:.2f}")
        print(f"  涨跌幅: {specific_day_data['pct_chg']:.1f}%")
    else:
        print(f"\n❌ 未找到{test_date}当日数据")

    # 检查前60天的数据量
    check_60_days_query = """
    SELECT COUNT(*) as count
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $2 - INTERVAL '60 days'
    """
    days_60_count = await conn.fetchval(check_60_days_query, stock_id, test_date)
    print(f"\n前60天数据条数: {days_60_count}")

    # 列出前20天的数据（用于调试）
    list_recent_20_query = """
    SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date <= $2
    ORDER BY trade_date DESC
    LIMIT 20
    """
    recent_20_data = await conn.fetch(list_recent_20_query, stock_id, test_date)

    if recent_20_data:
        print(f"\n最近20条数据:")
        print("  日期       开盘价  最高价  最低价  收盘价  涨跌幅")
        print("  " + "-" * 55)
        for row in recent_20_data:
            print(f"  {row['trade_date']}  {row['open_price']:6.2f}  {row['high_price']:6.2f}  {row['low_price']:6.2f}  {row['close_price']:6.2f}  {row['pct_chg']:6.1f}%")

    # 检查其他股票数据量（对比）
    check_other_stocks_query = """
    SELECT stock_id, COUNT(*) as count
    FROM subject_stock_daily_snapshot
    GROUP BY stock_id
    ORDER BY count DESC
    LIMIT 10
    """
    top_stocks = await conn.fetch(check_other_stocks_query)

    if top_stocks:
        print(f"\n数据量最多的10只股票:")
        for row in top_stocks:
            print(f"  {row['stock_id']}: {row['count']}条")

    await conn.close()

    return {
        'table_exists': table_exists,
        'stock_count': stock_count,
        'days_60_count': days_60_count,
        'has_specific_day': specific_day_data is not None
    }

async def main():
    try:
        result = await check_stock_history()

        print("\n" + "=" * 60)
        print("数据检查总结:")
        print(f"  数据表存在: {'✅' if result['table_exists'] else '❌'}")
        print(f"  股票总数据量: {result['stock_count']}条")
        print(f"  前60天数据量: {result['days_60_count']}条")
        print(f"  测试日数据存在: {'✅' if result['has_specific_day'] else '❌'}")

        # 判断是否满足高级分析要求
        if result['days_60_count'] >= 20:
            print(f"  ✅ 满足高级分析要求（≥20条数据）")
        else:
            print(f"  ❌ 不满足高级分析要求（需要≥20条数据）")

    except Exception as e:
        print(f"\n❌ 检查过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())