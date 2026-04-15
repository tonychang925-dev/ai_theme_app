#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from unittest.mock import AsyncMock
import asyncpg
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()

    # Mock the _fetch_candidate_inputs to return only Shenjian row
    async def mock_fetch(trade_date):
        # Return a single row mimicking the real row from SQL
        # We'll create a asyncpg.Record-like object using a dict
        # For simplicity, use a dict and convert to Record via asyncpg
        # We'll just use a dict and the code will treat it as asyncpg.Record
        # Actually the code expects asyncpg.Record, but dict works because row.get() is called.
        # Let's create a connection and fetch a single row to get proper Record
        pool = await asyncpg.create_pool(
            host='localhost', port=5432, user='postgres',
            password='postgres', database='stock_data_test',
            min_size=1, max_size=1
        )
        async with pool.acquire() as conn:
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
                  AND s.stock_id = '002361'
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
            await pool.close()
            return rows
    builder._fetch_candidate_inputs = mock_fetch

    try:
        print(f"Building candidate pool for {test_date}...")
        result = await builder.build_enhanced(test_date, max_formal=80, max_observe=40)
        print(f"Total scanned: {result.total_scanned}")
        print(f"Total inserted: {result.total_inserted}")
        print(f"Candidates count: {len(result.candidates)}")
        found = False
        for candidate in result.candidates:
            if candidate.get("stock_id") == "002361" or candidate.get("stock_id") == "002361.SZ":
                found = True
                print(f"✅ 神剑股份入选候选池!")
                print(f"   股票: {candidate.get('stock_name')} ({candidate.get('stock_id')})")
                print(f"   主题: {candidate.get('subject_key')} ({candidate.get('theme_name')})")
                print(f"   周期状态: {candidate.get('cycle_state')}, 退潮确认: {candidate.get('fade_confirmed')}")
                print(f"   准入类型: {candidate.get('pool_entry_type', 'unknown')}")
                print(f"   支撑位类型: {candidate.get('support_type')}, 支撑强度: {candidate.get('support_strength')}")
                print(f"   强势背景评分: {candidate.get('evidence_json', {}).get('enhanced_features', {}).get('strong_background_score', 'N/A')}")
                print(f"   修复窗口评分: {candidate.get('evidence_json', {}).get('enhanced_features', {}).get('repair_window_score', 'N/A')}")
                break
        if not found:
            print(f"❌ 神剑股份未入选候选池")
            # Print all candidates for debugging
            for i, candidate in enumerate(result.candidates, 1):
                print(f"{i}. {candidate.get('stock_id')} {candidate.get('stock_name')} - {candidate.get('theme_name')} - {candidate.get('pool_entry_type')}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())