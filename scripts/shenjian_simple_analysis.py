#!/usr/bin/env python3
"""
神剑股份简单分析 - 检查4月7日弱转强入选情况
"""

import asyncio
import asyncpg
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.config import StockServiceConfig


async def main():
    config = StockServiceConfig()

    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password
    )

    stock_id = "002361"
    analysis_date = date(2026, 4, 7)

    print("🧪 神剑股份弱转强简单分析")
    print("=" * 70)
    print(f"日期: {analysis_date}, 股票: {stock_id}")
    print()

    # 1. 检查主题映射
    theme_query = """
    SELECT DISTINCT tsm.subject_key, tsm.theme_name, tsm.confidence
    FROM theme_stock_map tsm
    WHERE tsm.stock_id = $1
    ORDER BY tsm.confidence DESC
    """
    themes = await conn.fetch(theme_query, stock_id)

    print("📊 神剑股份所属主题:")
    for row in themes:
        print(f"  主题键: {row['subject_key']}, 主题名: {row['theme_name']}")

    # 2. 检查每个主题的周期状态（优先V2表）
    print("\n📊 主题周期状态:")
    all_fade = True
    any_mainline = False

    for row in themes:
        subject_key = row['subject_key']
        theme_name = row['theme_name']

        # 先检查V2表
        v2_query = """
        SELECT final_mainline_alive, final_cycle_state, fade_watch, fade_confirmed
        FROM theme_cycle_judgement_v2
        WHERE trade_date = $1 AND subject_key = $2
        """
        v2_result = await conn.fetchrow(v2_query, analysis_date, subject_key)

        if v2_result:
            mainline_alive = v2_result['final_mainline_alive']
            cycle_state = v2_result['final_cycle_state']
            fade_watch = v2_result['fade_watch']
            fade_confirmed = v2_result['fade_confirmed']

            print(f"  {theme_name}:")
            print(f"    主线存活: {mainline_alive}, 周期状态: {cycle_state}")
            print(f"    退潮观察: {fade_watch}, 退潮确认: {fade_confirmed}")

            if mainline_alive:
                any_mainline = True
            if not fade_confirmed:
                all_fade = False
        else:
            # 检查原表
            orig_query = """
            SELECT is_main_theme, primary_cycle_stage, is_fade
            FROM theme_cycle_judgement
            WHERE trade_date = $1 AND subject_key = $2
            """
            orig_result = await conn.fetchrow(orig_query, analysis_date, subject_key)

            if orig_result:
                is_main_theme = orig_result['is_main_theme']
                cycle_stage = orig_result['primary_cycle_stage']
                is_fade = orig_result['is_fade']

                print(f"  {theme_name}:")
                print(f"    主线主题: {is_main_theme}, 周期阶段: {cycle_stage}, 退潮: {is_fade}")

                if is_main_theme:
                    any_mainline = True
                if not is_fade:
                    all_fade = False
            else:
                print(f"  {theme_name}: 无周期判定数据")

    # 3. 检查神剑股份在弱转强候选池中是否存在
    print("\n🔍 检查弱转强候选池:")
    candidate_query = """
    SELECT * FROM weak_to_strong_candidate_pool
    WHERE stock_id = $1 AND trade_date = $2
    """
    candidate = await conn.fetchrow(candidate_query, stock_id + ".SZ", analysis_date)

    if candidate:
        print(f"  ✅ 找到候选记录:")
        print(f"     准入类型: {candidate.get('pool_entry_type', 'N/A')}")
        print(f"     候选评分: {candidate.get('candidate_score', 'N/A')}")
        print(f"     周期状态: {candidate.get('cycle_state', 'N/A')}")
        print(f"     规则版本: {candidate.get('rule_version', 'N/A')}")
    else:
        # 尝试不带.SZ后缀
        candidate = await conn.fetchrow(candidate_query, stock_id, analysis_date)
        if candidate:
            print(f"  ✅ 找到候选记录（不带.SZ后缀）:")
            print(f"     准入类型: {candidate.get('pool_entry_type', 'N/A')}")
            print(f"     候选评分: {candidate.get('candidate_score', 'N/A')}")
        else:
            print(f"  ❌ 未在候选池中找到神剑股份")

    # 4. 检查当日价格数据
    print("\n📈 当日价格数据:")
    price_query = """
    SELECT pct_chg, low_price, close_price, volume, amount
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    """
    price_result = await conn.fetchrow(price_query, stock_id, analysis_date)

    if price_result:
        pct_chg = float(price_result['pct_chg']) if price_result['pct_chg'] else 0
        low_price = float(price_result['low_price']) if price_result['low_price'] else 0
        close_price = float(price_result['close_price']) if price_result['close_price'] else 0

        print(f"  涨跌幅: {pct_chg:.2f}%")
        print(f"  最低价: {low_price:.2f}")
        print(f"  收盘价: {close_price:.2f}")
        print(f"  是否弱势下跌 (<-2.0%): {'是' if pct_chg < -2.0 else '否'}")
    else:
        print(f"  无当日价格数据")

    # 5. 检查前一日价格数据
    print("\n📈 前一日价格数据:")
    # 查找前一个交易日
    prev_date_query = """
    SELECT trade_date, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date < $2
    ORDER BY trade_date DESC
    LIMIT 1
    """
    prev_result = await conn.fetchrow(prev_date_query, stock_id, analysis_date)

    if prev_result:
        prev_date = prev_result['trade_date']
        prev_pct_chg = float(prev_result['pct_chg']) if prev_result['pct_chg'] else 0
        print(f"  前一日日期: {prev_date}")
        print(f"  前一日涨跌幅: {prev_pct_chg:.2f}%")
        print(f"  是否弱势下跌 (<-1.5%): {'是' if prev_pct_chg < -1.5 else '否'}")
    else:
        print(f"  无前一日数据")

    # 6. 综合判断
    print("\n🎯 综合判断:")
    print(f"  是否有主线主题: {'是' if any_mainline else '否'}")
    print(f"  是否所有主题都退潮: {'是' if all_fade else '否'}")
    print(f"  在候选池中: {'是' if candidate else '否'}")

    # 根据用户思路判断
    # "只要不是退潮阶段，该股票如果是强势股，就要判断前一日是否弱势"
    # 这里我们简化：如果所有主题都退潮（fade），则不应入选
    # 但如果有任一主题不是退潮，且股票是强势股，前一日弱势，则可能入选

    print("\n📋 用户思路分析:")
    if all_fade:
        print("  所有主题都处于退潮阶段（fade）→ 不应入选弱转强候选池")
    else:
        print("  有主题未处于退潮阶段 → 需要检查是否是强势股和前一日是否弱势")

    # 检查是否是强势股（简化：近期是否有涨停）
    limit_up_query = """
    SELECT COUNT(*) as limit_up_count
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $3
    AND limit_up = TRUE
    """
    # 检查最近5个交易日
    start_date = analysis_date - timedelta(days=10)
    limit_up_result = await conn.fetchrow(limit_up_query, stock_id, analysis_date, start_date)

    if limit_up_result:
        limit_up_count = limit_up_result['limit_up_count'] or 0
        print(f"  最近10个交易日涨停次数: {limit_up_count}")
        is_strong = limit_up_count >= 2
        print(f"  是否强势股（≥2次涨停）: {'是' if is_strong else '否'}")
    else:
        is_strong = False
        print(f"  无法判断强势股")

    await conn.close()

    print("\n" + "=" * 70)
    print("分析完成")

if __name__ == "__main__":
    asyncio.run(main())