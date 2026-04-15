#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

class ShenjianEnhancedCandidateBuilder(EnhancedCandidateBuilder):
    """Enhanced candidate builder that filters for Shenjian股份 only"""
    async def _fetch_candidate_inputs(self, trade_date):
        """Override to fetch only Shenjian rows"""
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
              AND (s.stock_id = '002361' OR s.stock_id = '002361.SZ')
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

async def main():
    test_date = date(2026, 4, 7)
    builder = ShenjianEnhancedCandidateBuilder()

    try:
        print(f"Building candidate pool for {test_date} (Shenjian only)...")
        result = await builder.build_enhanced(test_date, max_formal=80, max_observe=40)
        print(f"Total scanned: {result.total_scanned}")
        print(f"Total inserted: {result.total_inserted}")
        print(f"Candidates count: {len(result.candidates)}")

        for candidate in result.candidates:
            print(f"✅ 神剑股份入选候选池!")
            print(f"   股票: {candidate.get('stock_name')} ({candidate.get('stock_id')})")
            print(f"   主题: {candidate.get('subject_key')} ({candidate.get('theme_name')})")
            print(f"   周期状态: {candidate.get('cycle_state')}, 退潮确认: {candidate.get('fade_confirmed')}")
            print(f"   准入类型: {candidate.get('pool_entry_type', 'unknown')}")
            print(f"   支撑位类型: {candidate.get('support_type')}, 支撑强度: {candidate.get('support_strength')}")
            # Parse evidence_json
            evidence_json = candidate.get("evidence_json", "{}")
            import json
            evidence = json.loads(evidence_json) if isinstance(evidence_json, str) else evidence_json
            enhanced = evidence.get("enhanced_features", {})
            print(f"   强势背景评分: {enhanced.get('strong_background_score', 'N/A')}")
            print(f"   修复窗口评分: {enhanced.get('repair_window_score', 'N/A')}")
            print(f"   主线存活: {enhanced.get('mainline_alive', 'N/A')}")
            print(f"   主线强度评分: {enhanced.get('mainline_strength_score', 'N/A')}")
            print(f"   修复窗口阈值: {enhanced.get('thresholds', {}).get('repair_window', 'N/A')}")
            print(f"   观察阈值: {enhanced.get('thresholds', {}).get('observe', 'N/A')}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())