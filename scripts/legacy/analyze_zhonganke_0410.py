#!/usr/bin/env python3
"""
分析中安科（600654）在2026-04-10的弱转强候选情况
用户描述：4/10日下跌到4/8日的支撑位附近，同时是算力题材，属于主线，而且该主线并没有退潮
4/13日强势涨停，可以通过4/13日盘前竞价确认！

LEGACY 脚本：
请优先使用统一入口 scripts/analyze_stock_w2s.py
"""

import asyncio
import asyncpg
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.config import StockServiceConfig


async def analyze_zhonganke():
    """分析中安科"""
    print("[LEGACY] 建议改用: .venv/bin/python scripts/analyze_stock_w2s.py --stock-code 600654 --trade-date 2026-04-10")
    config = StockServiceConfig()

    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password
    )

    stock_id = "600654"  # 中安科，可能后缀是.SH？
    analysis_date = date(2026, 4, 10)

    print("🧪 中安科（600654）弱转强分析 - 2026-04-10")
    print("=" * 70)
    print(f"日期: {analysis_date}, 股票: {stock_id}")
    print()

    # 1. 检查主题映射（本地快照映射）
    stock_ids = ["600654", "600654.SH"]
    themes = []

    for sid in stock_ids:
        theme_query = """
        SELECT DISTINCT
            s.subject_key,
            COALESCE(NULLIF(vw.theme_name, ''), s.subject_key) AS theme_name,
            1.0::numeric AS confidence
        FROM subject_stock_daily_snapshot s
        LEFT JOIN vw_subject_theme_binding vw
          ON vw.subject_key = s.subject_key
        WHERE s.trade_date = $1
          AND split_part(s.stock_id, '.', 1) = split_part($2::text, '.', 1)
        ORDER BY s.subject_key
        """
        rows = await conn.fetch(theme_query, analysis_date, sid)
        if rows:
            themes = rows
            stock_id = sid
            break

    print("📊 中安科所属主题:")
    if themes:
        for row in themes:
            print(f"  主题键: {row['subject_key']}, 主题名: {row['theme_name']}, 置信度: {row['confidence']}")
    else:
        print("  ❌ 未找到主题映射，尝试搜索算力相关主题...")
        # 搜索主题名包含"算力"的主题
        search_query = """
        SELECT subject_key, theme_name
        FROM theme_master
        WHERE theme_name LIKE '%算力%' OR theme_name LIKE '%计算%' OR theme_name LIKE '%AI%'
        LIMIT 5
        """
        search_results = await conn.fetch(search_query)
        if search_results:
            print("  可能的算力相关主题:")
            for row in search_results:
                print(f"    主题键: {row['subject_key']}, 主题名: {row['theme_name']}")
        else:
            print("  无算力主题找到")

    # 2. 检查主题周期状态
    print("\n📊 主题周期状态（2026-04-10）:")
    any_mainline = False
    any_non_fade = False

    for row in themes:
        subject_key = row['subject_key']
        theme_name = row['theme_name']

        # 优先V2表
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

            print(f"  {theme_name} (V2):")
            print(f"    主线存活: {mainline_alive}, 周期状态: {cycle_state}")
            print(f"    退潮观察: {fade_watch}, 退潮确认: {fade_confirmed}")

            if mainline_alive:
                any_mainline = True
            if not fade_confirmed and cycle_state != 'fade':
                any_non_fade = True
        else:
            print(f"  {theme_name}: 无V2周期判定数据")

    # 3. 检查弱转强候选池
    print("\n🔍 检查弱转强候选池（2026-04-10）:")
    candidate_query = """
    SELECT * FROM weak_to_strong_candidate_pool
    WHERE stock_id LIKE $1 AND trade_date = $2
    """
    # 尝试不同股票ID格式
    candidate = None
    for sid in [stock_id, stock_id + ".SH", "SH" + stock_id]:
        cand = await conn.fetchrow(candidate_query, sid, analysis_date)
        if cand:
            candidate = cand
            break

    if candidate:
        print(f"  ✅ 找到候选记录:")
        print(f"     准入类型: {candidate.get('pool_entry_type', 'N/A')}")
        print(f"     候选评分: {candidate.get('candidate_score', 'N/A')}")
        print(f"     周期状态: {candidate.get('cycle_state', 'N/A')}")
        print(f"     规则版本: {candidate.get('rule_version', 'N/A')}")
    else:
        print(f"  ❌ 未在候选池中找到中安科")

    # 4. 检查当日价格数据（4月10日）
    print("\n📈 4月10日价格数据:")
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

    # 5. 检查前一日价格数据（4月9日？但用户提到4月8日支撑位）
    print("\n📈 前几日价格数据（检查支撑位）:")
    # 获取4月8日和4月9日数据
    prev_dates = [date(2026, 4, 9), date(2026, 4, 8)]
    for prev_date in prev_dates:
        prev_query = """
        SELECT trade_date, pct_chg, low_price, close_price
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        """
        prev_result = await conn.fetchrow(prev_query, stock_id, prev_date)

        if prev_result:
            prev_pct_chg = float(prev_result['pct_chg']) if prev_result['pct_chg'] else 0
            prev_low = float(prev_result['low_price']) if prev_result['low_price'] else 0
            prev_close = float(prev_result['close_price']) if prev_result['close_price'] else 0

            print(f"  {prev_date}:")
            print(f"    涨跌幅: {prev_pct_chg:.2f}%, 最低价: {prev_low:.2f}, 收盘价: {prev_close:.2f}")
        else:
            print(f"  {prev_date}: 无数据")

    # 6. 检查4月13日涨停情况（验证）
    print("\n🎯 验证4月13日涨停情况:")
    verify_date = date(2026, 4, 13)
    verify_query = """
    SELECT limit_up, pct_chg, high_price, low_price, close_price
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    """
    verify_result = await conn.fetchrow(verify_query, stock_id, verify_date)

    if verify_result:
        limit_up = verify_result['limit_up']
        pct_chg = float(verify_result['pct_chg']) if verify_result['pct_chg'] else 0

        print(f"  4月13日:")
        print(f"    是否涨停: {limit_up}")
        print(f"    涨跌幅: {pct_chg:.2f}%")
        if limit_up:
            print(f"    ✅ 验证成功：4月13日强势涨停")
        else:
            print(f"    ❌ 验证失败：4月13日未涨停")
    else:
        print(f"  无4月13日数据")

    # 7. 综合判断
    print("\n🎯 综合判断:")
    print(f"  是否有主线主题: {'是' if any_mainline else '否'}")
    print(f"  是否有非退潮主题: {'是' if any_non_fade else '否'}")
    print(f"  在候选池中: {'是' if candidate else '否'}")

    # 用户描述条件：
    # 1. 4/10日下跌到4/8日的支撑位附近
    # 2. 是算力题材，属于主线
    # 3. 该主线并没有退潮
    print("\n📋 用户描述条件验证:")

    # 条件1: 检查是否下跌到支撑位（简化：比较4/10最低价和4/8日价格）
    if price_result and prev_dates[1]:  # 4月8日数据
        # 获取4月8日数据
        support_query = """
        SELECT low_price, close_price
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        """
        support_result = await conn.fetchrow(support_query, stock_id, date(2026, 4, 8))

        if support_result:
            support_low = float(support_result['low_price']) if support_result['low_price'] else 0
            support_close = float(support_result['close_price']) if support_result['close_price'] else 0

            # 4月10日最低价
            current_low = low_price

            # 计算距离支撑位的距离（以4月8日最低价为支撑）
            distance_pct = abs(current_low - support_low) / support_low if support_low > 0 else 0

            print(f"  条件1 - 下跌到4/8日支撑位附近:")
            print(f"    4/8日最低价（支撑位）: {support_low:.2f}")
            print(f"    4/10日最低价: {current_low:.2f}")
            print(f"    距离支撑位: {distance_pct:.2%}")

            is_near_support = distance_pct <= 0.03  # 3%以内认为是附近
            print(f"    是否在支撑位附近（≤3%）: {'✅ 是' if is_near_support else '❌ 否'}")
        else:
            print(f"  条件1 - 无法验证：无4/8日数据")
            is_near_support = False
    else:
        print(f"  条件1 - 无法验证：缺少价格数据")
        is_near_support = False

    # 条件2和3: 算力题材，属于主线，主线没有退潮
    print(f"  条件2 - 算力题材，属于主线: {'✅ 是' if any_mainline else '❌ 否'}")
    print(f"  条件3 - 主线没有退潮: {'✅ 是' if any_non_fade else '❌ 否'}")

    await conn.close()

    print("\n" + "=" * 70)
    print("分析完成")

if __name__ == "__main__":
    asyncio.run(analyze_zhonganke())
