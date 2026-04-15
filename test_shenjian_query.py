#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date

async def main():
    test_date = date(2026, 4, 7)
    print("Connecting...")
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='postgres',
        password='postgres', database='stock_data_test'
    )
    print("Running query for Shenjian...")
    sql = """
    SELECT
        s.stock_id,
        s.stock_name,
        s.subject_key,
        s.pct_chg,
        s.limit_up,
        s.is_leader,
        s.rank_order,
        m.theme_name,
        m.is_main_theme,
        c.primary_cycle_stage,
        c.action_bias,
        c.is_fade
    FROM subject_stock_daily_snapshot s
    LEFT JOIN theme_mainline_judgement m
      ON m.trade_date = s.trade_date
     AND m.subject_key = s.subject_key
    LEFT JOIN theme_cycle_judgement c
      ON c.trade_date = s.trade_date
     AND c.subject_key = s.subject_key
    WHERE s.trade_date = $1::date
      AND (s.stock_id = '002361' OR s.stock_id = '002361.SZ')
    """
    rows = await conn.fetch(sql, test_date)
    print(f"Found {len(rows)} rows for Shenjian")
    for row in rows:
        print("Row:")
        for key, val in row.items():
            print(f"  {key}: {val}")

    # Also check theme_cycle_judgement_v2
    sql_v2 = """
    SELECT * FROM theme_cycle_judgement_v2
    WHERE trade_date = $1::date
      AND subject_key IN (SELECT subject_key FROM subject_stock_daily_snapshot
                          WHERE trade_date = $1::date
                          AND (stock_id = '002361' OR stock_id = '002361.SZ'))
    """
    rows_v2 = await conn.fetch(sql_v2, test_date)
    print(f"\nV2 judgment rows: {len(rows_v2)}")
    for row in rows_v2:
        print("V2 Row:")
        for key, val in row.items():
            print(f"  {key}: {val}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())