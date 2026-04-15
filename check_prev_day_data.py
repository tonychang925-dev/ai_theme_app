#!/usr/bin/env python3
"""
检查前一日数据
"""
import asyncio
import asyncpg
from datetime import date, timedelta

async def main():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("连接数据库...")
    conn = await asyncpg.connect(**config)

    try:
        # 检查2026-04-09日数据
        prev_date = date(2026, 4, 9)
        print(f"\n检查{prev_date}日数据:")

        rows = await conn.fetch("""
            SELECT COUNT(*) as count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
        """, prev_date)

        count = rows[0]['count']
        print(f"   {prev_date}有{count}条记录")

        if count > 0:
            # 获取一些样本数据
            sample_rows = await conn.fetch("""
                SELECT stock_id, stock_name, subject_key, pct_chg, is_leader
                FROM subject_stock_daily_snapshot
                WHERE trade_date = $1
                LIMIT 5
            """, prev_date)

            print(f"   样本数据:")
            for i, row in enumerate(sample_rows, 1):
                print(f"   {i}. {row['stock_id']} - {row['stock_name']}")
                print(f"      主题: {row['subject_key']}, 涨跌幅: {row['pct_chg']}%, 是否龙头: {row['is_leader']}")

        # 检查2026-04-10日数据中的股票在2026-04-09日是否有数据
        print(f"\n检查2026-04-10日股票在2026-04-09日的数据:")

        # 获取2026-04-10日的股票列表
        today_date = date(2026, 4, 10)
        today_stocks = await conn.fetch("""
            SELECT DISTINCT stock_id, stock_name
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            LIMIT 10
        """, today_date)

        print(f"   2026-04-10日有{len(today_stocks)}只不同股票")

        for i, stock in enumerate(today_stocks[:5], 1):
            stock_id = stock['stock_id']
            stock_name = stock['stock_name']

            prev_data = await conn.fetch("""
                SELECT pct_chg, is_leader
                FROM subject_stock_daily_snapshot
                WHERE trade_date = $1
                AND stock_id = $2
            """, prev_date, stock_id)

            if prev_data:
                pct_chg = prev_data[0]['pct_chg']
                print(f"   {i}. {stock_id} - {stock_name}")
                print(f"      前一日涨跌幅: {pct_chg}%")
                if pct_chg and pct_chg < -2.0:
                    print(f"      ✅ 前一日弱势 (跌幅 > 2%)")
                elif pct_chg and pct_chg > 0:
                    print(f"      ❌ 前一日强势 (上涨)")
                else:
                    print(f"      ⚠️  前一日平盘或小幅下跌")
            else:
                print(f"   {i}. {stock_id} - {stock_name}")
                print(f"      ❌ 无前一日数据")

        # 检查是否有K线数据表
        print(f"\n检查K线数据表:")
        tables = await conn.fetch("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename LIKE '%kline%' OR tablename LIKE '%candle%'
            ORDER BY tablename
        """)

        if tables:
            print(f"   找到{len(tables)}个K线相关表:")
            for table in tables:
                print(f"     - {table['tablename']}")
        else:
            print(f"   未找到K线相关表")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())