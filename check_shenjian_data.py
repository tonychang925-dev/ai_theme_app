#!/usr/bin/env python3
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
    conn = await asyncpg.connect(**config)

    stock_id = "002361"
    start_date = date(2026, 4, 1)
    end_date = date(2026, 4, 10)

    query = """
    SELECT trade_date, pct_chg, open_price, high_price, low_price, close_price, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date >= $2 AND trade_date <= $3
    ORDER BY trade_date ASC
    """

    rows = await conn.fetch(query, stock_id, start_date, end_date)

    print(f"神剑股份 ({stock_id}) 2026-04-01 至 2026-04-10 数据:")
    print("日期        涨跌幅(%)  开盘价   最高价   最低价   收盘价   涨停")
    for r in rows:
        trade_date = r['trade_date']
        pct_chg = r['pct_chg']
        open_price = r['open_price']
        high_price = r['high_price']
        low_price = r['low_price']
        close_price = r['close_price']
        limit_up = r['limit_up']
        print(f"{trade_date}  {pct_chg:6.1f}    {open_price:7.2f} {high_price:7.2f} {low_price:7.2f} {close_price:7.2f}  {limit_up}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())