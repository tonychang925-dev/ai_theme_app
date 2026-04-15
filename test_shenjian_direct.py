#!/usr/bin/env python3
"""
直接获取神剑股份数据并测试候选构建
"""
import asyncio
import asyncpg
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("直接测试神剑股份候选构建")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)

        # 直接查询数据库获取神剑股份数据
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            # 使用与_fetch_candidate_inputs相同的SQL，但过滤神剑股份
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
            WHERE b.stock_id LIKE '%002361%'
            """
            rows = await conn.fetch(sql, trade_date)
            print(f"找到 {len(rows)} 行神剑股份数据")
            if not rows:
                print("未找到神剑股份数据")
                return

            row = rows[0]
            print(f"神剑股份数据: stock_id={row.get('stock_id')}, subject_key={row.get('subject_key')}")
            print(f"  rank_order={row.get('rank_order')}, pct_chg={row.get('pct_chg')}")
            print(f"  recent_limit_up_count={row.get('recent_limit_up_count')}")
            print(f"  is_fade={row.get('is_fade')}, is_main_theme={row.get('is_main_theme')}")

            # 获取周期特征
            subject_key = str(row.get('subject_key', ''))
            cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
            print(f"周期特征: cycle_state={cycle_features.cycle_state}, fade_confirmed={cycle_features.fade_confirmed}")

            # 构建增强候选
            next_day = await builder.resolve_next_trade_date(trade_date)
            candidate = builder._to_enhanced_candidate(row, trade_date, next_day, cycle_features)
            if candidate is None:
                print("候选构建失败")
                return

            print(f"\n候选构建成功")
            print(f"候选分数: {candidate.get('candidate_score')}")
            print(f"pool_entry_type: '{candidate.get('pool_entry_type')}'")
            print(f"type: {type(candidate.get('pool_entry_type'))}")

            # 检查分类逻辑
            entry_type = candidate.get("pool_entry_type", "reject")
            print(f"\n分类测试:")
            print(f"  entry_type == 'formal': {entry_type == 'formal'}")
            print(f"  entry_type == 'observe_only': {entry_type == 'observe_only'}")

            # 检查增强特征
            evidence_json = candidate.get('evidence_json', '{}')
            import json
            evidence = json.loads(evidence_json)
            enhanced = evidence.get('enhanced_features', {})
            print(f"\n增强特征:")
            print(f"  strong_background_score: {enhanced.get('strong_background_score')}")
            print(f"  repair_window_score: {enhanced.get('repair_window_score')}")
            print(f"  mainline_alive: {enhanced.get('mainline_alive')}")
            print(f"  fade_confirmed: {enhanced.get('fade_confirmed')}")

            # 直接调用determine_pool_entry_type
            entry_type_direct = builder.determine_pool_entry_type(
                enhanced.get('strong_background_score', 0),
                enhanced.get('repair_window_score', 0),
                enhanced.get('mainline_alive', False),
                enhanced.get('fade_confirmed', False)
            )
            print(f"\ndetermine_pool_entry_type返回值: '{entry_type_direct}'")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())
