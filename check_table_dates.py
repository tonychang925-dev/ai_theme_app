#!/usr/bin/env python3
"""
检查数据表的日期范围
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def check_table_dates():
    stock_ids = ["002335", "301236", "000034", "002361"]
    test_date = date(2026, 4, 7)

    print("检查数据表日期范围")
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

    for stock_id in stock_ids:
        print(f"\n股票 {stock_id}:")
        print("-" * 40)

        # 查询总体日期范围
        date_range_query = """
        SELECT
            MIN(trade_date) as earliest,
            MAX(trade_date) as latest,
            COUNT(*) as total_count
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1
        """
        date_range = await conn.fetchrow(date_range_query, stock_id)

        if date_range:
            print(f"  总体日期范围: {date_range['earliest']} 到 {date_range['latest']}")
            print(f"  总数据条数: {date_range['total_count']}")

        # 查询测试日期前后的数据
        date_test_query = """
        SELECT
            COUNT(*) as count,
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1
          AND trade_date >= $2::date - INTERVAL '60 days'
          AND trade_date <= $2::date
        """
        test_range = await conn.fetchrow(date_test_query, stock_id, test_date)

        if test_range:
            print(f"  在{test_date}前60天内数据: {test_range['count']}条")
            if test_range['count'] > 0:
                print(f"    日期范围: {test_range['min_date']} 到 {test_range['max_date']}")

        # 查询具体的数据样例
        sample_query = """
        SELECT trade_date, open_price, close_price, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1
        ORDER BY trade_date DESC
        LIMIT 5
        """
        samples = await conn.fetch(sample_query, stock_id)

        if samples:
            print(f"  最近5条数据:")
            for row in samples:
                print(f"    {row['trade_date']}: 开盘{row['open_price']:.2f}, 收盘{row['close_price']:.2f}, 涨跌幅{row['pct_chg']:.1f}%")

        # 检查日期连续性
        continuity_query = """
        WITH date_series AS (
            SELECT generate_series(
                (SELECT MIN(trade_date) FROM subject_stock_daily_snapshot WHERE stock_id = $1),
                (SELECT MAX(trade_date) FROM subject_stock_daily_snapshot WHERE stock_id = $1),
                '1 day'::interval
            )::date as date
        ),
        actual_dates AS (
            SELECT DISTINCT trade_date as date
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
        )
        SELECT
            COUNT(*) as total_days,
            COUNT(a.date) as data_days,
            COUNT(*) - COUNT(a.date) as missing_days,
            (COUNT(a.date) * 100.0 / COUNT(*)) as coverage_pct
        FROM date_series d
        LEFT JOIN actual_dates a ON d.date = a.date
        """
        continuity = await conn.fetchrow(continuity_query, stock_id)

        if continuity:
            print(f"  日期连续性分析:")
            print(f"    总日历天数: {continuity['total_days']}")
            print(f"    有数据的天数: {continuity['data_days']}")
            print(f"    缺失天数: {continuity['missing_days']}")
            print(f"    覆盖率: {continuity['coverage_pct']:.1f}%")

    # 检查整个表的统计信息
    print(f"\n{'='*80}")
    print("整个数据表统计:")

    table_stats_query = """
    SELECT
        COUNT(DISTINCT stock_id) as stock_count,
        COUNT(*) as total_records,
        MIN(trade_date) as earliest_date,
        MAX(trade_date) as latest_date,
        AVG(records_per_stock) as avg_records_per_stock
    FROM (
        SELECT stock_id, COUNT(*) as records_per_stock
        FROM subject_stock_daily_snapshot
        GROUP BY stock_id
    ) t
    """
    table_stats = await conn.fetchrow(table_stats_query)

    if table_stats:
        print(f"  股票数量: {table_stats['stock_count']}")
        print(f"  总记录数: {table_stats['total_records']}")
        print(f"  日期范围: {table_stats['earliest_date']} 到 {table_stats['latest_date']}")
        print(f"  平均每只股票记录数: {table_stats['avg_records_per_stock']:.1f}")

    # 检查测试日期附近的数据分布
    print(f"\n{'='*80}")
    print(f"测试日期{test_date}附近的数据分布:")

    date_dist_query = """
    SELECT
        CASE
            WHEN trade_date = $2 THEN '当天'
            WHEN trade_date > $2 THEN '之后'
            ELSE '之前'
        END as time_period,
        COUNT(*) as record_count,
        COUNT(DISTINCT stock_id) as stock_count
    FROM subject_stock_daily_snapshot
    WHERE trade_date >= $2::date - INTERVAL '10 days'
       AND trade_date <= $2::date + INTERVAL '10 days'
    GROUP BY time_period
    ORDER BY
        CASE time_period
            WHEN '之前' THEN 1
            WHEN '当天' THEN 2
            WHEN '之后' THEN 3
        END
    """
    date_dist = await conn.fetch(date_dist_query, test_date, test_date)

    if date_dist:
        for row in date_dist:
            print(f"  {row['time_period']}: {row['record_count']}条记录, {row['stock_count']}只股票")

    await conn.close()

async def main():
    try:
        await check_table_dates()
    except Exception as e:
        print(f"\n❌ 检查过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())