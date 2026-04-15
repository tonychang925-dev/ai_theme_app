#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date

async def test():
    # 数据库连接参数 - 需要根据实际情况调整
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='admin',
        password='admin',
        database='stock_data_test'
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
    print(f"总行数: {len(rows)}")

    # 查找神剑股份
    for i, row in enumerate(rows):
        stock_id = row.get('stock_id', '')
        if '002361' in stock_id:
            print(f"找到神剑股份 at index {i}")
            print(f"  stock_id: {row.get('stock_id')}")
            print(f"  stock_name: {row.get('stock_name')}")
            print(f"  subject_key: {row.get('subject_key')}")
            print(f"  pct_chg: {row.get('pct_chg')}")
            print(f"  limit_up: {row.get('limit_up')}")
            print(f"  is_leader: {row.get('is_leader')}")
            print(f"  is_main_theme: {row.get('is_main_theme')}")
            print(f"  primary_cycle_stage: {row.get('primary_cycle_stage')}")
            print(f"  action_bias: {row.get('action_bias')}")
            print(f"  is_fade: {row.get('is_fade')}")
            print(f"  recent_limit_up_count: {row.get('recent_limit_up_count')}")
            print(f"  prev_day_pct_chg: {row.get('prev_day_pct_chg')}")
            break
    else:
        print("未找到神剑股份")
        # 打印前5行
        for i, row in enumerate(rows[:5]):
            print(f"行{i}: stock_id={row.get('stock_id')}, subject_key={row.get('subject_key')}, pct_chg={row.get('pct_chg')}")

    await conn.close()

asyncio.run(test())