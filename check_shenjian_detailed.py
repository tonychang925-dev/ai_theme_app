#!/usr/bin/env python3
"""
检查神剑股份详细数据
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
    dates = [date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 10)]

    for d in dates:
        query = """
        SELECT stock_id, stock_name, trade_date, pct_chg, is_leader, rank_order, subject_key
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        LIMIT 1
        """
        row = await conn.fetchrow(query, stock_id, d)
        if row:
            print(f"{d}: 涨跌幅 {row['pct_chg']}%, 是否龙头 {row['is_leader']}, 排名 {row['rank_order']}, 主题 {row['subject_key']}")
        else:
            print(f"{d}: 无数据")

    # 检查主题是否为主线
    subject_key = "9062832"
    for d in dates:
        query = """
        SELECT is_main_theme
        FROM theme_mainline_judgement
        WHERE subject_key = $1 AND trade_date = $2
        LIMIT 1
        """
        row = await conn.fetchrow(query, subject_key, d)
        if row:
            print(f"主题 {subject_key} 在 {d} 是否为主线: {row['is_main_theme']}")
        else:
            print(f"主题 {subject_key} 在 {d}: 无主线判断")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())