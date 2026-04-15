#!/usr/bin/env python3
"""
检查神剑股份数据列
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
    d = date(2026, 4, 7)

    query = """
    SELECT trade_date, stock_name,
           open_price, high_price, low_price, close_price,
           pre_close, pct_chg, change_amount,
           volume, amount, limit_up,
           is_leader, rank_order, subject_key
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    LIMIT 1
    """
    row = await conn.fetchrow(query, stock_id, d)
    if row:
        print(f"Date: {row['trade_date']}")
        print(f"Stock: {row['stock_name']}")
        print(f"Open: {row['open_price']}")
        print(f"High: {row['high_price']}")
        print(f"Low: {row['low_price']}")
        print(f"Close: {row['close_price']}")
        print(f"PreClose: {row['pre_close']}")
        print(f"PctChg: {row['pct_chg']}%")
        print(f"ChangeAmount: {row['change_amount']}")
        print(f"Volume: {row['volume']}")
        print(f"Amount: {row['amount']}")
        print(f"LimitUp: {row['limit_up']}")
        print(f"IsLeader: {row['is_leader']}")
        print(f"RankOrder: {row['rank_order']}")
        print(f"SubjectKey: {row['subject_key']}")

        # Check if high < low
        if row['high_price'] < row['low_price']:
            print("WARNING: high_price < low_price! Data likely swapped.")
            print(f"Possible correct: high={row['low_price']}, low={row['high_price']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())