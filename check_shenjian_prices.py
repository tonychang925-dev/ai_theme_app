#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date

async def test():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='stock_data_test',
        user='postgres',
        password='zxbzj~925'
    )

    # Get Shenjian data for April 3 and April 7
    stock_id = '002361'
    dates = [date(2026, 4, 3), date(2026, 4, 7)]

    for date_str in dates:
        print(f'\n=== {date_str} ===')
        row = await conn.fetchrow('''
            SELECT stock_id, trade_date, open_price, high_price, low_price,
                   close_price, pre_close, pct_chg, limit_up, is_leader,
                   rank_order
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date = $2
            LIMIT 1
        ''', stock_id, date_str)

        if row:
            print(f'stock_id: {row["stock_id"]}')
            print(f'open: {row["open_price"]}, high: {row["high_price"]}, low: {row["low_price"]}, close: {row["close_price"]}')
            print(f'pre_close: {row["pre_close"]}, pct_chg: {row["pct_chg"]}')
            print(f'limit_up: {row["limit_up"]}, is_leader: {row["is_leader"]}, rank_order: {row["rank_order"]}')
        else:
            print('No data')

    # Get previous days data for support analysis
    print('\n=== Previous days for support analysis ===')
    prev_rows = await conn.fetch('''
        SELECT trade_date, open_price, high_price, low_price, close_price, pre_close, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date <= $2
        ORDER BY trade_date DESC
        LIMIT 10
    ''', stock_id, date(2026, 4, 7))

    for row in prev_rows:
        print(f'{row["trade_date"]}: open={row["open_price"]}, high={row["high_price"]}, low={row["low_price"]}, close={row["close_price"]}, pct_chg={row["pct_chg"]}')

    await conn.close()

if __name__ == "__main__":
    asyncio.run(test())