#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date

async def test():
    # Connect to the database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='stock_data_test',
        user='postgres',
        password='zxbzj~925'
    )

    trade_date = date(2026, 4, 7)

    sql = """
    WITH stock_base AS (
        SELECT DISTINCT ON (split_part(s.stock_id, '.', 1), s.subject_key)
            split_part(s.stock_id, '.', 1) AS stock_code,
            s.stock_id,
            s.stock_name,
            s.subject_key,
            COALESCE(NULLIF(m.theme_name, ''), NULLIF(c.theme_name, ''), s.subject_key) AS theme_name,
            s.rank_order,
            s.pct_chg,
            s.limit_up,
            s.is_leader,
            c.primary_cycle_stage,
            c.action_bias,
            c.is_divergence,
            c.is_rebound,
            c.is_fermentation,
            c.is_fade,
            m.is_main_theme
        FROM subject_stock_daily_snapshot s
        LEFT JOIN theme_mainline_judgement m
          ON m.trade_date = s.trade_date
         AND m.subject_key = s.subject_key
        LEFT JOIN theme_cycle_judgement c
          ON c.trade_date = s.trade_date
         AND c.subject_key = s.subject_key
        WHERE s.trade_date = $1::date
          AND (s.stock_id = '002361' OR s.stock_id LIKE '002361.%')
    )
    SELECT
        b.*,
        (
            SELECT COUNT(*)
            FROM subject_stock_daily_snapshot h
            WHERE split_part(h.stock_id, '.', 1) = b.stock_code
              AND h.trade_date <= $1::date
              AND h.trade_date > ($1::date - INTERVAL '30 days')
              AND COALESCE(h.limit_up, FALSE) = TRUE
        ) AS recent_limit_up_count,
        (
            SELECT h.pct_chg
            FROM subject_stock_daily_snapshot h
            WHERE split_part(h.stock_id, '.', 1) = b.stock_code
              AND h.trade_date < $1::date
            ORDER BY h.trade_date DESC
            LIMIT 1
        ) AS prev_day_pct_chg,
        (
            SELECT h.limit_up
            FROM subject_stock_daily_snapshot h
            WHERE split_part(h.stock_id, '.', 1) = b.stock_code
              AND h.trade_date < $1::date
            ORDER BY h.trade_date DESC
            LIMIT 1
        ) AS prev_day_limit_up
    FROM stock_base b
    """

    rows = await conn.fetch(sql, trade_date)
    print(f"Found {len(rows)} rows for Shenjian")
    for row in rows:
        print("Row data:")
        for key, value in row.items():
            print(f"  {key}: {value}")
        break

    # Also fetch cycle features from v2
    sql_v2 = """
    SELECT
        final_mainline_alive,
        mainline_strength_score,
        final_cycle_state,
        fade_watch,
        fade_confirmed,
        previous_cycle_state
    FROM theme_cycle_judgement_v2
    WHERE trade_date = $1 AND subject_key = $2
    """
    subject_key = rows[0]['subject_key'] if rows else '9062832'
    row_v2 = await conn.fetchrow(sql_v2, trade_date, subject_key)
    if row_v2:
        print("\nCycle features from v2:")
        for key in ['final_mainline_alive', 'mainline_strength_score', 'final_cycle_state', 'fade_watch', 'fade_confirmed']:
            print(f"  {key}: {row_v2[key]}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(test())