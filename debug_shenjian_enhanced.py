#!/usr/bin/env python3
"""
调试神剑股份在EnhancedCandidateBuilder中的处理
"""
import asyncio
import json
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def debug_shenjian():
    print("🔍 调试神剑股份在EnhancedCandidateBuilder中的处理")
    print("=" * 60)

    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)
        subject_key = "9062832"  # 神剑股份的主题key

        # 1. 获取周期特征
        print("1️⃣ 获取周期特征")
        cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
        print(f"  cycle_state: {cycle_features.cycle_state}")
        print(f"  fade_watch: {cycle_features.fade_watch}")
        print(f"  fade_confirmed: {cycle_features.fade_confirmed}")
        print(f"  mainline_alive: {cycle_features.mainline_alive}")
        print(f"  mainline_strength_score: {cycle_features.mainline_strength_score}")

        # 2. 获取神剑股份数据
        print(f"\n2️⃣ 获取神剑股份数据")
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
            print("❌ 未找到神剑股份数据")
            return

        row = rows[0]
        print(f"  stock_id: {row.get('stock_id')}")
        print(f"  stock_name: {row.get('stock_name')}")
        print(f"  pct_chg: {row.get('pct_chg')}")
        print(f"  prev_day_pct_chg: {row.get('prev_day_pct_chg')}")
        print(f"  recent_limit_up_count: {row.get('recent_limit_up_count')}")
        print(f"  is_leader: {row.get('is_leader')}")
        print(f"  limit_up: {row.get('limit_up')}")
        print(f"  rank_order: {row.get('rank_order')}")
        print(f"  primary_cycle_stage: {row.get('primary_cycle_stage')}")
        print(f"  action_bias: {row.get('action_bias')}")
        print(f"  is_divergence: {row.get('is_divergence')}")
        print(f"  is_rebound: {row.get('is_rebound')}")
        print(f"  is_fermentation: {row.get('is_fermentation')}")
        print(f"  is_fade: {row.get('is_fade')}")

        # 3. 计算评分
        print(f"\n3️⃣ 计算评分")
        is_leader = bool(row.get('is_leader') or False)
        limit_up = bool(row.get('limit_up') or False)
        recent_limit_up_count = int(row.get('recent_limit_up_count') or 0)
        rank_order = int(row.get('rank_order') or 999)

        strong_bg_score = builder.calculate_strong_background_score(
            is_leader, limit_up, recent_limit_up_count, rank_order
        )
        print(f"  strong_background_score: {strong_bg_score}")
        print(f"  STRONG_BACKGROUND_THRESHOLD: {builder.STRONG_BACKGROUND_THRESHOLD}")

        action_bias = str(row.get('action_bias') or "")
        stage = str(row.get('primary_cycle_stage') or "").lower()
        is_divergence = bool(row.get('is_divergence') or False)
        is_rebound = bool(row.get('is_rebound') or False)
        is_fermentation = bool(row.get('is_fermentation') or False)
        is_fade = bool(row.get('is_fade') or False)

        repair_score = builder.calculate_repair_window_score(
            action_bias, stage, is_divergence, is_rebound, is_fermentation,
            is_fade, cycle_features.fade_confirmed
        )
        print(f"  repair_window_score: {repair_score}")
        print(f"  REPAIR_WINDOW_THRESHOLD: {builder.REPAIR_WINDOW_THRESHOLD}")

        # 4. 确定准入类型
        print(f"\n4️⃣ 确定准入类型")
        entry_type = builder.determine_pool_entry_type(
            strong_bg_score, repair_score,
            cycle_features.mainline_alive, cycle_features.fade_confirmed
        )
        print(f"  pool_entry_type: {entry_type}")
        print(f"  mainline_alive: {cycle_features.mainline_alive}")
        print(f"  fade_confirmed: {cycle_features.fade_confirmed}")

        # 5. 尝试构建增强候选
        print(f"\n5️⃣ 构建增强候选")
        next_day = date(2026, 4, 8)
        candidate = builder._to_enhanced_candidate(row, trade_date, next_day, cycle_features)

        if candidate:
            print(f"✅ 候选构建成功!")
            print(f"  candidate_score: {candidate.get('candidate_score')}")
            print(f"  candidate_type: {candidate.get('candidate_type')}")
            print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
            print(f"  rule_version: {candidate.get('rule_version')}")

            evidence = json.loads(candidate.get('evidence_json', '{}'))
            enhanced_features = evidence.get('enhanced_features', {})
            print(f"  enhanced_features.strong_background_score: {enhanced_features.get('strong_background_score')}")
            print(f"  enhanced_features.repair_window_score: {enhanced_features.get('repair_window_score')}")
            print(f"  enhanced_features.cycle_state: {enhanced_features.get('cycle_state')}")
        else:
            print(f"❌ 候选构建失败 (返回None)")

            # 尝试使用父类方法
            print(f"\n 尝试父类方法 _to_candidate")
            # 创建修正后的row（模拟_to_enhanced_candidate中的逻辑）
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

            base_candidate = builder._to_candidate(corrected_row, trade_date, next_day)
            if base_candidate:
                print(f"  ✅ 父类方法成功: candidate_score={base_candidate.get('candidate_score')}")
            else:
                print(f"  ❌ 父类方法也失败")

    except Exception as e:
        print(f"❌ 调试错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    await debug_shenjian()

if __name__ == "__main__":
    asyncio.run(main())