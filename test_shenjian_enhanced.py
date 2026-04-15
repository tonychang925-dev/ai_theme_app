#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
import asyncpg

class ShenjianTestBuilder(EnhancedCandidateBuilder):
    async def _fetch_candidate_inputs(self, trade_date):
        # Return only Shenjian row
        pool = await self._ensure_pool()
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
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return rows

async def test():
    builder = ShenjianTestBuilder()
    try:
        trade_date = date(2026, 4, 7)
        print(f"Building enhanced candidates for {trade_date}...")
        result = await builder.build_enhanced(trade_date, max_formal=10, max_observe=5)
        print(f"Total scanned: {result.total_scanned}")
        print(f"Total inserted: {result.total_inserted}")
        if result.candidates:
            candidate = result.candidates[0]
            print(f"✅ Shenjian candidate created!")
            print(f"  stock_id: {candidate.get('stock_id')}")
            print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
            print(f"  candidate_score: {candidate.get('candidate_score')}")
            print(f"  cycle_state: {candidate.get('cycle_state')}")
            print(f"  fade_confirmed: {candidate.get('fade_confirmed')}")
        else:
            print("❌ No candidates produced")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())