#!/usr/bin/env python3
"""
测试_fetch_candidate_inputs的SQL是否有限制
"""
import asyncio
import asyncpg
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("测试_fetch_candidate_inputs的SQL")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)

        # 获取SQL并手动执行
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            # 直接执行_fetch_candidate_inputs中的SQL
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
                ORDER BY split_part(s.stock_id, '.', 1), s.subject_key, s.rank_order ASC
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
            -- 去掉主线过滤条件：WHERE COALESCE(b.is_main_theme, FALSE) = TRUE
            -- 允许支线题材进入候选池，但保留其他筛选逻辑
            -- 按重要性排序：1. 排名靠前，2. 近期涨停次数多，3. 涨幅大（负值小）
            ORDER BY b.rank_order ASC NULLS LAST,
                     recent_limit_up_count DESC,
                     b.pct_chg ASC  -- 负值越小（跌幅越大）越重要
            LIMIT 100
            """

            print("执行SQL...")
            rows = await conn.fetch(sql, trade_date)
            print(f"返回行数: {len(rows)}")

            # 检查前几行
            print("\n前5行:")
            for i, row in enumerate(rows[:5]):
                print(f"{i}: stock_id={row.get('stock_id')}, rank_order={row.get('rank_order')}, recent_limit_up_count={row.get('recent_limit_up_count')}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())