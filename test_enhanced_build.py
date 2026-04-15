#!/usr/bin/env python3
"""
测试EnhancedCandidateBuilder.build_enhanced方法
验证神剑股份是否出现在候选列表中
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test_build():
    print("🔍 测试EnhancedCandidateBuilder.build_enhanced")
    print("=" * 60)

    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)
        next_date = date(2026, 4, 8)

        # 设置较小的max_formal以便调试
        result = await builder.build_enhanced(
            trade_date,
            next_trade_date=next_date,
            max_formal=50,
            max_observe=20
        )

        print(f"📊 扫描总数: {result.total_scanned}")
        print(f"📥 插入总数: {result.total_inserted}")
        print(f"📋 候选数量: {len(result.candidates)}")
        print(f"  - 正式候选: {len([c for c in result.candidates if c.get('pool_entry_type') == 'formal'])}")
        print(f"  - 观察候选: {len([c for c in result.candidates if c.get('pool_entry_type') == 'observe_only'])}")

        # 查找神剑股份
        shenjian_candidates = []
        for cand in result.candidates:
            stock_id = cand.get('stock_id', '')
            if '002361' in stock_id:
                shenjian_candidates.append(cand)

        if shenjian_candidates:
            print(f"\n✅ 神剑股份出现在候选列表中!")
            for cand in shenjian_candidates:
                print(f"  stock_id: {cand.get('stock_id')}")
                print(f"  stock_name: {cand.get('stock_name')}")
                print(f"  candidate_score: {cand.get('candidate_score')}")
                print(f"  pool_entry_type: {cand.get('pool_entry_type')}")
                print(f"  cycle_state: {cand.get('cycle_state')}")
                print(f"  fade_watch: {cand.get('fade_watch')}")
                print(f"  fade_confirmed: {cand.get('fade_confirmed')}")
        else:
            print(f"\n❌ 神剑股份未出现在候选列表中")

            # 尝试查找被拒绝的原因
            print(f"\n🔍 尝试查找神剑股份被拒绝的原因...")
            # 手动获取数据
            pool = await builder._ensure_pool()
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
                  AND split_part(s.stock_id, '.', 1) = '002361'
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

            if not rows:
                print("  数据库中没有找到神剑股份数据")
                return

            row = rows[0]
            subject_key = str(row.get('subject_key') or '')
            print(f"  subject_key: {subject_key}")

            # 获取周期特征
            cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
            print(f"  cycle_state: {cycle_features.cycle_state}")
            print(f"  fade_watch: {cycle_features.fade_watch}")
            print(f"  fade_confirmed: {cycle_features.fade_confirmed}")
            print(f"  mainline_alive: {cycle_features.mainline_alive}")

            # 尝试构建候选
            candidate = builder._to_enhanced_candidate(row, trade_date, next_date, cycle_features)
            if candidate is None:
                print("  _to_enhanced_candidate返回None")
                # 检查父类方法
                print("  检查父类方法...")
                corrected_row = dict(row)
                corrected_row["is_fade"] = cycle_features.fade_confirmed
                if cycle_features.cycle_state == "fade_watch":
                    corrected_row["primary_cycle_stage"] = "divergence"
                else:
                    corrected_row["primary_cycle_stage"] = cycle_features.cycle_state

                if (cycle_features.cycle_state == "divergence" or
                    cycle_features.cycle_state == "repair" or
                    cycle_features.cycle_state == "fade_watch"):
                    corrected_row["action_bias"] = "关注弱转强"
                elif cycle_features.fade_confirmed:
                    corrected_row["action_bias"] = "放弃"

                corrected_row["is_divergence"] = (cycle_features.cycle_state == "divergence" or
                                                  cycle_features.cycle_state == "fade_watch")
                corrected_row["is_rebound"] = cycle_features.cycle_state == "rebound"
                corrected_row["is_fermentation"] = cycle_features.cycle_state == "fermentation"

                parent_row = corrected_row.copy()
                recent_limit_up_count = int(row.get('recent_limit_up_count') or 0)
                if not cycle_features.cycle_state and recent_limit_up_count >= 2:
                    parent_row["primary_cycle_stage"] = "divergence"
                    parent_row["action_bias"] = "关注弱转强"
                    parent_row["is_divergence"] = True
                    parent_row["is_fade"] = False
                elif cycle_features.cycle_state == "fade_watch":
                    parent_row["primary_cycle_stage"] = "divergence"
                    parent_row["action_bias"] = "关注弱转强"
                    parent_row["is_divergence"] = True
                    parent_row["is_fade"] = False

                base_candidate = builder._to_candidate(parent_row, trade_date, next_date)
                if base_candidate is None:
                    print("  父类_to_candidate也返回None")
                else:
                    print(f"  父类_to_candidate成功: score={base_candidate.get('candidate_score')}")
            else:
                print(f"  _to_enhanced_candidate成功但未出现在结果中")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")

    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    await test_build()

if __name__ == "__main__":
    asyncio.run(main())