#!/usr/bin/env python3
import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='stock_data_test',
        user='postgres',
        password='zxbzj~925'
    )
    print("Connected")
    rows = await conn.fetch("SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date = '2026-04-07'")
    print(f"Count: {rows[0]['count']}")
    await conn.close()

asyncio.run(test())