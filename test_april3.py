#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder, CycleFeatureInputs
import asyncpg

async def test():
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 3)
        # Fetch row
        conn = await asyncpg.connect(
            host='localhost', port=5432, database='stock_data_test',
            user='postgres', password='zxbzj~925')
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
        if not rows:
            print("No Shenjian row for April 3")
            return
        row = rows[0]
        print("Row data:")
        for key in ['stock_id', 'pct_chg', 'limit_up', 'is_leader', 'rank_order', 'recent_limit_up_count', 'primary_cycle_stage', 'is_fade', 'is_main_theme']:
            print(f"  {key}: {row[key]}")

        # Get cycle features via builder's fetch_cycle_features
        cycle_features = await builder.fetch_cycle_features(trade_date, str(row['subject_key']))
        print("\nCycle features:")
        print(f"  mainline_alive: {cycle_features.mainline_alive}")
        print(f"  mainline_strength_score: {cycle_features.mainline_strength_score}")
        print(f"  cycle_state: {cycle_features.cycle_state}")
        print(f"  fade_watch: {cycle_features.fade_watch}")
        print(f"  fade_confirmed: {cycle_features.fade_confirmed}")

        # Simulate _to_enhanced_candidate
        next_day = date(2026, 4, 4)
        candidate = builder._to_enhanced_candidate(row, trade_date, next_day, cycle_features)
        if candidate:
            print(f"\n✅ Candidate created (pool_entry_type: {candidate.get('pool_entry_type')})")
        else:
            print("\n❌ Candidate rejected")
        await conn.close()
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())