#!/usr/bin/env python3
"""
分析神剑股份在2026-04-07的主题归属和主线周期状态
按照用户提供的思路分析：
1. 明确神剑股份属于哪些题材（本地快照映射）
2. 判断题材是否是主线
3. 判断主线所处的阶段
4. 只要不是退潮阶段，该股票如果是强势股
5. 判断前一日是否弱势
6. 如果弱势且下跌到明显的支撑位，则股票入选

LEGACY 脚本：
请优先使用统一入口 scripts/analyze_stock_w2s.py
"""

import asyncio
import asyncpg
from datetime import date, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.config import StockServiceConfig


async def analyze_shenjian_themes():
    """分析神剑股份的主题和周期状态"""
    print("[LEGACY] 建议改用: .venv/bin/python scripts/analyze_stock_w2s.py --stock-code 002361 --trade-date 2026-04-07")
    config = StockServiceConfig()

    print("🧪 神剑股份弱转强分析 - 2026-04-07")
    print("=" * 70)

    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password
    )

    stock_id = "002361"
    analysis_date = date(2026, 4, 7)

    print(f"📅 分析日期: {analysis_date}")
    print(f"📊 股票: {stock_id} 神剑股份")
    print()

    # 1. 获取神剑股份所属所有主题（本地快照映射）
    print("🔍 步骤1: 获取神剑股份所属所有主题")
    theme_query = """
    SELECT DISTINCT
        s.subject_key,
        ''::text AS theme_id,
        COALESCE(NULLIF(vw.theme_name, ''), s.subject_key) AS theme_name,
        1.0::numeric AS confidence
    FROM subject_stock_daily_snapshot s
    LEFT JOIN vw_subject_theme_binding vw
      ON vw.subject_key = s.subject_key
    WHERE s.trade_date = $1
      AND split_part(s.stock_id, '.', 1) = $2
    ORDER BY s.subject_key
    """
    theme_rows = await conn.fetch(theme_query, analysis_date, stock_id)

    if not theme_rows:
        print("❌ 未找到主题映射")
        await conn.close()
        return

    print(f"  找到 {len(theme_rows)} 个主题:")
    for i, row in enumerate(theme_rows, 1):
        print(f"  {i}. 主题ID: {row['theme_id']}, 主题名称: {row['theme_name']}, 主题键: {row['subject_key']}, 置信度: {row['confidence']}")

    # 2. 分析每个主题的主线周期状态
    print("\n🔍 步骤2: 分析每个主题的主线周期状态")
    valid_themes = []

    for row in theme_rows:
        subject_key = row['subject_key']
        theme_name = row['theme_name']

        # 检查theme_cycle_judgement_v2表
        v2_query = """
        SELECT
            final_mainline_alive,
            mainline_strength_score,
            final_cycle_state,
            fade_watch,
            fade_confirmed,
            previous_cycle_state
        FROM theme_cycle_judgement_v2
        WHERE trade_date = $1 AND subject_key = $2
        """

        v2_result = await conn.fetchrow(v2_query, analysis_date, subject_key)

        if v2_result:
            print(f"  📊 主题 '{theme_name}' (V2表数据):")
            print(f"     主线存活: {v2_result['final_mainline_alive']}")
            print(f"     主线强度评分: {v2_result['mainline_strength_score']:.1f}")
            print(f"     周期状态: {v2_result['final_cycle_state']}")
            print(f"     退潮观察: {v2_result['fade_watch']}")
            print(f"     退潮确认: {v2_result['fade_confirmed']}")
            print(f"     前一周期状态: {v2_result['previous_cycle_state']}")

            # 判断是否是主线且未退潮
            is_mainline = v2_result['final_mainline_alive']
            is_fade_confirmed = v2_result['fade_confirmed']
            cycle_state = v2_result['final_cycle_state']

            if is_mainline and not is_fade_confirmed:
                print(f"     ✅ 是主线且未退潮确认")
                valid_themes.append({
                    'subject_key': subject_key,
                    'theme_name': theme_name,
                    'mainline_alive': True,
                    'cycle_state': cycle_state,
                    'strength_score': v2_result['mainline_strength_score']
                })
            else:
                print(f"     ⚠️  不是主线或已退潮确认")
        else:
            print(f"  📊 主题 '{theme_name}': 无V2周期判定数据")

    # 3. 如果没有任何有效主线主题，分析是否仍然可能入选
    print("\n🔍 步骤3: 分析股票本身特性")

    # 3.1 检查是否是强势股
    print("  3.1 检查是否是强势股")

    # 查询近期涨停模式
    limit_up_query = """
    WITH recent_days AS (
        SELECT DISTINCT trade_date
        FROM subject_stock_daily_snapshot
        WHERE split_part(stock_id, '.', 1) = $2
          AND trade_date <= $1
        ORDER BY trade_date DESC
        LIMIT 10
    ),
    limit_up_data AS (
        SELECT
            ss.trade_date,
            ss.limit_up,
            ss.pct_chg
        FROM subject_stock_daily_snapshot ss
        JOIN recent_days rd ON ss.trade_date = rd.trade_date
        WHERE split_part(ss.stock_id, '.', 1) = $2
        ORDER BY ss.trade_date DESC
    )
    SELECT
        COUNT(*) as total_days,
        SUM(CASE WHEN limit_up = TRUE THEN 1 ELSE 0 END) as limit_up_count,
        MAX(CASE WHEN limit_up = TRUE THEN 1 ELSE 0 END) as has_limit_up
    FROM limit_up_data
    """

    limit_up_result = await conn.fetchrow(limit_up_query, analysis_date, stock_id)

    if limit_up_result:
        limit_up_count = limit_up_result['limit_up_count'] or 0
        print(f"     最近10个交易日涨停次数: {limit_up_count}")

        # 更严格的强势股标准：至少连续2天涨停，或3次及以上涨停
        # 需要查询连续涨停天数
        consecutive_query = """
        WITH daily_data AS (
            SELECT
                trade_date,
                limit_up,
                LAG(limit_up) OVER (ORDER BY trade_date DESC) as prev_limit_up
            FROM subject_stock_daily_snapshot
            WHERE split_part(stock_id, '.', 1) = $1 AND trade_date <= $2
            ORDER BY trade_date DESC
            LIMIT 10
        )
        SELECT
            MAX(CASE
                WHEN limit_up = TRUE AND prev_limit_up = TRUE THEN 1
                ELSE 0
            END) as has_consecutive
        FROM daily_data
        """

        consecutive_result = await conn.fetchrow(consecutive_query, stock_id, analysis_date)
        has_consecutive = consecutive_result and consecutive_result['has_consecutive'] == 1

        is_strong_stock = (limit_up_count >= 3) or has_consecutive
        print(f"     是否有连续涨停: {'是' if has_consecutive else '否'}")
        print(f"     是否强势股（≥3次涨停或连续涨停）: {'✅ 是' if is_strong_stock else '❌ 否'}")
    else:
        print(f"     无近期数据")
        is_strong_stock = False

    # 3.2 检查前一日是否弱势下跌
    print("\n  3.2 检查前一日是否弱势下跌")

    prev_date_query = """
    SELECT MAX(trade_date) AS prev_trade_date
    FROM subject_stock_daily_snapshot
    WHERE split_part(stock_id, '.', 1) = $1
      AND trade_date < $2
    """

    prev_date = await conn.fetchval(prev_date_query, stock_id, analysis_date)

    if prev_date:
        prev_day_query = """
        SELECT pct_chg, close_price
        FROM subject_stock_daily_snapshot
        WHERE split_part(stock_id, '.', 1) = $1 AND trade_date = $2
        """

        prev_day_result = await conn.fetchrow(prev_day_query, stock_id, prev_date)

        if prev_day_result and prev_day_result['pct_chg'] is not None:
            prev_pct_chg = float(prev_day_result['pct_chg'])
            is_prev_weak = prev_pct_chg < -1.5
            print(f"     前一日 ({prev_date}): 涨跌幅 {prev_pct_chg:.2f}%")
            print(f"     是否弱势下跌 (<-1.5%): {'✅ 是' if is_prev_weak else '❌ 否'}")
        else:
            print(f"     无前一日数据")
            is_prev_weak = False
    else:
        print(f"     无前一个交易日")
        is_prev_weak = False

    # 3.3 检查是否下跌到支撑位
    print("\n  3.3 检查是否下跌到支撑位")

    # 获取当日价格数据
    day_query = """
    SELECT low_price, close_price, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE split_part(stock_id, '.', 1) = $1 AND trade_date = $2
    """

    day_result = await conn.fetchrow(day_query, stock_id, analysis_date)

    if day_result:
        low_price = float(day_result['low_price'])
        close_price = float(day_result['close_price'])
        pct_chg = float(day_result['pct_chg'])

        print(f"     当日数据: 最低价 {low_price:.2f}, 收盘价 {close_price:.2f}, 涨跌幅 {pct_chg:.2f}%")

        # 简单支撑检查：检查是否有明显的支撑位（缺口、前低等）
        # 这里简化处理，实际应该调用支撑分析服务
        support_check_query = """
        WITH historical_prices AS (
            SELECT
                trade_date,
                low_price,
                high_price,
                close_price
            FROM subject_stock_daily_snapshot
            WHERE split_part(stock_id, '.', 1) = $1 AND trade_date < $2
            ORDER BY trade_date DESC
            LIMIT 20
        )
        SELECT
            MIN(low_price) as recent_min,
            MAX(high_price) as recent_max,
            AVG(close_price) as recent_avg
        FROM historical_prices
        """

        support_result = await conn.fetchrow(support_check_query, stock_id, analysis_date)

        if support_result:
            recent_min = float(support_result['recent_min']) if support_result['recent_min'] else 0
            recent_max = float(support_result['recent_max']) if support_result['recent_max'] else 0
            recent_avg = float(support_result['recent_avg']) if support_result['recent_avg'] else 0

            # 检查是否接近近期低点（支撑）
            support_threshold = 0.02  # 2%范围内
            if recent_min > 0:
                distance_to_support = abs(low_price - recent_min) / recent_min
                has_support = distance_to_support <= support_threshold

                print(f"     近期最低点: {recent_min:.2f}")
                print(f"     距离支撑位: {distance_to_support:.2%}")
                print(f"     是否到达支撑位 (±2%): {'✅ 是' if has_support else '❌ 否'}")
            else:
                print(f"     无历史价格数据")
                has_support = False
        else:
            print(f"     无支撑分析数据")
            has_support = False
    else:
        print(f"     无当日数据")
        has_support = False

    # 4. 综合判断
    print("\n🔍 步骤4: 综合判断")
    print("=" * 50)

    # 判断条件：
    # 1. 有有效主线主题（或即使没有，但股票本身强势）
    # 2. 是强势股
    # 3. 前一日弱势下跌
    # 4. 到达支撑位

    has_valid_theme = len(valid_themes) > 0

    print(f"  条件1 - 有有效主线主题: {'✅ 是' if has_valid_theme else '❌ 否'}")
    if has_valid_theme:
        for theme in valid_themes:
            print(f"    主题: {theme['theme_name']}, 周期状态: {theme['cycle_state']}, 强度: {theme['strength_score']:.1f}")

    print(f"  条件2 - 是强势股: {'✅ 是' if is_strong_stock else '❌ 否'}")
    print(f"  条件3 - 前一日弱势下跌: {'✅ 是' if is_prev_weak else '❌ 否'}")
    print(f"  条件4 - 到达支撑位: {'✅ 是' if has_support else '❌ 否'}")

    # 弱转强入选逻辑：
    # 如果有主线主题：需要全部条件满足
    # 如果没有主线主题：需要是强势股 + 前一日弱势下跌 + 到达支撑位
    if has_valid_theme:
        should_select = is_strong_stock and is_prev_weak and has_support
        reason = "有主线主题，且满足强势股、前日弱势、到达支撑位条件"
    else:
        should_select = is_strong_stock and is_prev_weak and has_support
        reason = "无主线主题，但满足强势股、前日弱势、到达支撑位条件"

    print("\n🎯 弱转强入选判断:")
    if should_select:
        print(f"  ✅ 应入选弱转强候选池")
        print(f"     理由: {reason}")
    else:
        print(f"  ❌ 不应入选弱转强候选池")

        # 输出未满足的条件
        missing_conditions = []
        if not has_valid_theme:
            missing_conditions.append("无有效主线主题")
        if not is_strong_stock:
            missing_conditions.append("不是强势股")
        if not is_prev_weak:
            missing_conditions.append("前一日未弱势下跌")
        if not has_support:
            missing_conditions.append("未到达支撑位")

        print(f"     未满足条件: {', '.join(missing_conditions)}")

    # 5. 与增强构建器结果对比
    print("\n🔍 步骤5: 与增强构建器结果对比")

    # 查询weak_to_strong_candidate_pool表
    candidate_query = """
    SELECT * FROM weak_to_strong_candidate_pool
    WHERE stock_id = $1 AND trade_date = $2
    """

    candidate_result = await conn.fetchrow(candidate_query, stock_id, analysis_date)

    if candidate_result:
        print(f"  ✅ 在弱转强候选池中找到神剑股份")
        print(f"     准入类型: {candidate_result.get('pool_entry_type', 'N/A')}")
        print(f"     候选评分: {candidate_result.get('candidate_score', 'N/A')}")
        print(f"     周期状态: {candidate_result.get('cycle_state', 'N/A')}")
    else:
        print(f"  ❌ 未在弱转强候选池中找到神剑股份")

    await conn.close()

    print("\n" + "=" * 70)
    print("分析完成!")

    return should_select


async def main():
    success = await analyze_shenjian_themes()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
