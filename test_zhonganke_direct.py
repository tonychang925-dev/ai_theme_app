#!/usr/bin/env python3
"""
直接测试中安科(600654)的_to_enhanced_candidate方法
"""
import asyncio
import asyncpg
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from stock_service.services.enhanced_candidate_builder import CycleFeatureInputs

async def test_zhonganke_direct():
    """直接测试中安科候选构建"""
    builder = EnhancedCandidateBuilder()

    trade_date = date(2026, 4, 10)
    next_trade_date = date(2026, 4, 13)  # 假设

    try:
        # 获取中安科的数据行
        pool = await builder._ensure_pool()
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
                  AND split_part(s.stock_id, '.', 1) = '600654'
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
                print("❌ 未找到中安科数据")
                return

            row = rows[0]
            print(f"找到中安科数据:")
            print(f"  stock_id: {row.get('stock_id')}")
            print(f"  subject_key: {row.get('subject_key')}")
            print(f"  pct_chg: {row.get('pct_chg')}")
            print(f"  prev_day_pct_chg: {row.get('prev_day_pct_chg')}")
            print(f"  recent_limit_up_count: {row.get('recent_limit_up_count')}")
            print(f"  rank_order: {row.get('rank_order')}")
            print(f"  limit_up: {row.get('limit_up')}")
            print(f"  is_leader: {row.get('is_leader')}")
            print(f"  primary_cycle_stage: {row.get('primary_cycle_stage')}")
            print(f"  action_bias: {row.get('action_bias')}")
            print(f"  is_divergence: {row.get('is_divergence')}")
            print(f"  is_rebound: {row.get('is_rebound')}")
            print(f"  is_fermentation: {row.get('is_fermentation')}")
            print(f"  is_fade: {row.get('is_fade')}")

            # 获取周期特征
            subject_key = str(row.get("subject_key") or "")
            print(f"\n获取周期特征 for subject_key: {subject_key}")
            cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
            print(f"周期特征:")
            print(f"  cycle_state: {cycle_features.cycle_state}")
            print(f"  mainline_alive: {cycle_features.mainline_alive}")
            print(f"  mainline_strength_score: {cycle_features.mainline_strength_score}")
            print(f"  fade_watch: {cycle_features.fade_watch}")
            print(f"  fade_confirmed: {cycle_features.fade_confirmed}")

            # 测试_to_enhanced_candidate
            print(f"\n测试_to_enhanced_candidate...")
            candidate = builder._to_enhanced_candidate(row, trade_date, next_trade_date, cycle_features)

            if candidate:
                print(f"✅ 成功构建候选!")
                print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                print(f"  support_strength: {candidate.get('support_strength')}")
                print(f"  cycle_state: {candidate.get('cycle_state')}")
                print(f"  支撑类型: {candidate.get('support_type')}")
                print(f"  弱势类型: {candidate.get('weak_type')}")
                print(f"  弱势强度: {candidate.get('weak_intensity')}")
                print(f"  主线强度分数: {candidate.get('mainline_strength_score')}")
                print(f"  退潮观察: {candidate.get('fade_watch')}")
                print(f"  退潮确认: {candidate.get('fade_confirmed')}")
            else:
                print(f"❌ 构建候选失败")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    """主测试函数"""
    print("开始直接测试中安科候选构建...")
    print("=" * 70)
    await test_zhonganke_direct()

if __name__ == "__main__":
    asyncio.run(main())