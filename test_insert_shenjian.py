#!/usr/bin/env python3
"""
测试神剑股份候选插入数据库
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("测试神剑股份候选插入数据库")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)

        # 直接查询数据库获取神剑股份数据
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
            WHERE b.stock_id LIKE '%002361%'
            """
            rows = await conn.fetch(sql, trade_date)
            print(f"找到 {len(rows)} 行神剑股份数据")
            if not rows:
                print("未找到神剑股份数据")
                return

            row = rows[0]
            print(f"神剑股份数据: stock_id={row.get('stock_id')}")

            # 获取周期特征
            subject_key = str(row.get('subject_key', ''))
            cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
            print(f"周期特征: cycle_state={cycle_features.cycle_state}")

            # 构建增强候选
            next_day = await builder.resolve_next_trade_date(trade_date)
            candidate = builder._to_enhanced_candidate(row, trade_date, next_day, cycle_features)
            if candidate is None:
                print("候选构建失败")
                return

            print(f"候选构建成功，分数: {candidate.get('candidate_score')}")
            print(f"pool_entry_type: {candidate.get('pool_entry_type')}")

            # 插入数据库
            inserted = await builder._replace_enhanced_candidates(next_day, [candidate])
            print(f"插入 {inserted} 条记录到数据库")

            # 验证插入
            check_sql = "SELECT COUNT(*) FROM weak_to_strong_candidate_pool WHERE stock_id LIKE '%002361%' AND next_trade_date = $1"
            count = await conn.fetchval(check_sql, next_day)
            print(f"验证: 数据库中有 {count} 条神剑股份记录")

            if count > 0:
                # 获取记录详情
                detail_sql = "SELECT stock_id, candidate_score, pool_entry_type FROM weak_to_strong_candidate_pool WHERE stock_id LIKE '%002361%'"
                details = await conn.fetch(detail_sql)
                for detail in details:
                    print(f"  记录: {detail}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())
