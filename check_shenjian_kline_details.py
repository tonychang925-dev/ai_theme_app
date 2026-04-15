#!/usr/bin/env python3
"""
检查神剑股份K线细节
"""
import asyncio
import asyncpg
from datetime import date

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
    dates = [date(2026, 4, 4), date(2026, 4, 7), date(2026, 4, 8)]

    for d in dates:
        query = """
        SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        LIMIT 1
        """
        row = await conn.fetchrow(query, stock_id, d)
        if row:
            print(f"{d}: open={row['open_price']}, high={row['high_price']}, low={row['low_price']}, close={row['close_price']}, pct={row['pct_chg']}%")
        else:
            print(f"{d}: 无数据")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())