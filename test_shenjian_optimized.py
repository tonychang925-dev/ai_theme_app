#!/usr/bin/env python3
"""
优化测试脚本 - 神剑股份弱转强验证
1. 使用LIMIT简化查询
2. 正确提取字段
3. 验证4月7日选中，4月3日拒绝
"""
import asyncio
import json
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian(trade_date: date):
    """测试特定日期神剑股份的候选构建"""
    print(f"\n🔍 测试神剑股份 {trade_date}")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    try:
        # 简化查询：只获取神剑股份的数据
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
            print(f"❌ 未找到神剑股份在 {trade_date}")
            return False

        row = rows[0]
        print("📊 神剑股份数据:")
        print(f"  stock_id: {row.get('stock_id')}")
        print(f"  stock_name: {row.get('stock_name')}")
        print(f"  pct_chg: {row.get('pct_chg')}")
        print(f"  prev_day_pct_chg: {row.get('prev_day_pct_chg')}")
        print(f"  recent_limit_up_count: {row.get('recent_limit_up_count')}")
        print(f"  is_leader: {row.get('is_leader')}")
        print(f"  limit_up: {row.get('limit_up')}")
        print(f"  rank_order: {row.get('rank_order')}")
        print(f"  is_main_theme: {row.get('is_main_theme')}")
        print(f"  is_fade: {row.get('is_fade')}")
        print(f"  primary_cycle_stage: {row.get('primary_cycle_stage')}")
        print(f"  action_bias: {row.get('action_bias')}")
        print(f"  is_divergence: {row.get('is_divergence')}")
        print(f"  is_rebound: {row.get('is_rebound')}")
        print(f"  is_fermentation: {row.get('is_fermentation')}")

        # 手动检查硬门槛
        print("\n🔍 手动检查硬门槛:")
        pct_chg = float(row.get('pct_chg') or 0.0)
        prev_day_pct = float(row.get('prev_day_pct_chg') or 0.0)
        is_leader = bool(row.get('is_leader') or False)
        limit_up = bool(row.get('limit_up') or False)
        rank_order = int(row.get('rank_order') or 999)
        recent_limit_up_count = int(row.get('recent_limit_up_count') or 0)
        stage = str(row.get('primary_cycle_stage') or '').lower()
        action_bias = str(row.get('action_bias') or '')
        is_divergence = bool(row.get('is_divergence') or False)
        is_rebound = bool(row.get('is_rebound') or False)
        is_fermentation = bool(row.get('is_fermentation') or False)

        # 1. 强势背景
        strong_background = (
            is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
        )
        print(f"  1. 强势背景: {strong_background}")
        print(f"     recent_limit_up_count={recent_limit_up_count} >=2: {recent_limit_up_count >= 2}")

        # 2. 修复窗口
        repair_window = (
            ('弱转强' in action_bias) or
            stage in {'divergence', 'rebound', 'fermentation', '分歧', '回流', '发酵', '启动'} or
            is_divergence or is_rebound or is_fermentation or
            (recent_limit_up_count >= 2 and pct_chg < 0)
        )
        print(f"  2. 修复窗口: {repair_window}")
        print(f"     recent_limit_up_count >= 2 and pct_chg < 0: {recent_limit_up_count >= 2 and pct_chg < 0}")

        # 3. 支撑强度
        print(f"  3. 支撑强度: 测试analyze_strict_support...")
        support_result = await builder.analyze_strict_support("002361", pct_chg, trade_date)
        print(f"     has_support: {support_result['has_support']}")
        print(f"     support_strength: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
        print(f"     support_type: {support_result.get('support_type', '')}")
        print(f"     support_count: {support_result.get('support_count', 0)}")
        print(f"     >=30: {support_result.get('support_strength', 0.0) * 100 >= 30}")

        # 如果任一门槛失败，直接返回
        if not strong_background:
            print("❌ 强势背景不满足")
            return False
        if not repair_window:
            print("❌ 修复窗口不满足")
            return False
        if support_result.get('support_strength', 0.0) * 100 < 30:
            print("❌ 支撑强度不足")
            return False

        print("\n✅ 所有硬门槛满足，进行候选构建...")
        candidate = await builder._async_to_candidate(row, trade_date, trade_date)
        if candidate:
            print("🎉 候选构建成功!")
            print(f"  candidate_score: {candidate.get('candidate_score')}")
            print(f"  support_strength: {candidate.get('support_strength')}")
            print(f"  support_type: {candidate.get('support_type')}")
            print(f"  weak_type: {candidate.get('weak_type')}")
            print(f"  candidate_type: {candidate.get('candidate_type')}")

            # 从evidence_json提取字段
            evidence = json.loads(candidate.get('evidence_json', '{}'))
            breakdown = evidence.get('scores', {}).get('breakdown', {})
            print(f"  strong_background: {breakdown.get('strong_background')}")
            print(f"  repair_window: {breakdown.get('repair_window')}")

            rules = evidence.get('rules', {}).get('hard_rule_results', [])
            for rule in rules:
                print(f"  {rule.get('rule')}: {rule.get('passed')}")

            return True
        else:
            print("❌ 候选构建失败 (返回None)")
            print("   可能被其他逻辑过滤")
            return False

    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()

async def test_support_analysis():
    """单独测试支撑位分析"""
    print("\n📊 单独测试支撑位分析")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    try:
        support_result = await builder.analyze_strict_support("002361", -3.11, date(2026, 4, 7))
        print(f"支撑检测结果:")
        print(f"  has_support: {support_result['has_support']}")
        print(f"  support_type: {support_result.get('support_type', '')}")
        print(f"  support_strength: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
        print(f"  support_count: {support_result.get('support_count', 0)}")
        print(f"  support_types: {support_result.get('support_types', [])}")
        print(f"  combined_strength: {support_result.get('combined_strength', 0.0) * 100:.1f}/100")
        print(f"  primary_type: {support_result.get('primary_type', '')}")

        # 检查是否检测到多种支撑类型
        support_types = support_result.get('support_types', [])
        if len(support_types) > 1:
            print(f"✅ 检测到多种支撑类型: {[st.get('type', '') for st in support_types]}")
        else:
            print(f"⚠️  只检测到一种支撑类型")

    except Exception as e:
        print(f"❌ 支撑检测错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    print("🚀 神剑股份弱转强算法优化验证")
    print("=" * 60)

    # 1. 测试支撑位分析
    await test_support_analysis()

    # 2. 测试4月7日（应选中）
    print("\n" + "=" * 60)
    print("1️⃣ 测试2026-04-07 (应选中)")
    success_0407 = await test_shenjian(date(2026, 4, 7))

    # 3. 测试4月3日（应拒绝）
    print("\n" + "=" * 60)
    print("2️⃣ 测试2026-04-03 (应拒绝)")
    success_0403 = await test_shenjian(date(2026, 4, 3))

    # 总结
    print("\n" + "=" * 60)
    print("📋 验证结果总结:")
    print(f"  2026-04-07 (应选中): {'✅ 通过' if success_0407 else '❌ 失败'}")
    print(f"  2026-04-03 (应拒绝): {'✅ 正确拒绝' if not success_0403 else '❌ 错误选中'}")

    if success_0407 and not success_0403:
        print("\n🎉 弱转强算法验证成功！")
        print("   神剑股份在4月7日正确选中，4月3日正确拒绝。")
        return 0
    else:
        print("\n⚠️  算法验证失败，需要进一步调试。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)