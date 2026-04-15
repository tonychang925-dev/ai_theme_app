#!/usr/bin/env python3
"""
分析4月10日的63个弱转强候选股质量
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def analyze_candidates():
    test_date = date(2026, 4, 10)
    prev_date = date(2026, 4, 9)  # 前一天

    print(f"分析4月10日弱转强候选股质量")
    print(f"分析日期: {test_date}, 前一日: {prev_date}")
    print("=" * 80)

    # 连接数据库
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    # 从测试输出中获取候选股列表（简化版，实际应该从测试结果读取）
    # 先查询4月10日所有弱势下跌的股票
    query = """
    SELECT DISTINCT ON (ss.stock_id)
        ss.stock_id,
        ss.stock_name,
        ss.pct_chg,
        ss.close_price,
        ss.low_price,
        ss.subject_key as theme_key
    FROM subject_stock_daily_snapshot ss
    WHERE ss.trade_date = $1 AND ss.pct_chg < -2.0
    ORDER BY ss.stock_id, ss.rank_order NULLS LAST
    """
    weak_stocks = await conn.fetch(query, test_date)

    print(f"4月10日弱势下跌 (<-2%) 股票总数: {len(weak_stocks)}")

    # 分析每个弱势下跌股票
    candidates = []
    for i, stock in enumerate(weak_stocks):
        stock_id = stock['stock_id']
        stock_name = stock['stock_name']
        pct_chg = float(stock['pct_chg'])
        theme_key = stock['theme_key']

        # 1. 检查前一天（4月9日）是否也是弱势下跌
        prev_query = """
        SELECT pct_chg, close_price, low_price
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order NULLS LAST
        LIMIT 1
        """
        prev_data = await conn.fetchrow(prev_query, stock_id, prev_date)

        prev_weak = False
        prev_pct_chg = 0
        if prev_data:
            prev_pct_chg = float(prev_data['pct_chg']) if prev_data['pct_chg'] else 0
            prev_weak = prev_pct_chg < -2.0

        # 2. 检查涨停模式（最近7天）
        limit_up_query = """
        SELECT COUNT(*) as limit_up_count,
               MAX(CASE WHEN pct_chg >= 9.8 THEN 1 ELSE 0 END) as has_limit_up
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1
          AND trade_date >= $2 - INTERVAL '7 days'
          AND trade_date < $2
        """
        limit_up_data = await conn.fetchrow(limit_up_query, stock_id, test_date)

        limit_up_count = limit_up_data['limit_up_count'] if limit_up_data else 0
        has_limit_up = limit_up_data['has_limit_up'] == 1 if limit_up_data else False

        # 3. 检查连续涨停
        consecutive_query = """
        WITH ranked AS (
            SELECT trade_date, pct_chg,
                   ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
              AND trade_date >= $2 - INTERVAL '7 days'
              AND trade_date < $2
            ORDER BY trade_date DESC
        )
        SELECT MAX(consecutive_count) as max_consecutive
        FROM (
            SELECT COUNT(*) as consecutive_count
            FROM ranked
            WHERE pct_chg >= 9.8
            GROUP BY rn - ROW_NUMBER() OVER (ORDER BY trade_date)
        ) t
        """
        consecutive_data = await conn.fetchrow(consecutive_query, stock_id, test_date)

        max_consecutive = consecutive_data['max_consecutive'] if consecutive_data else 0

        # 4. 判断是否是强势股
        # 标准1: 有涨停
        # 标准2: 连续涨停 >= 2天 或 涨停次数 >= 2次
        is_strong = has_limit_up and (max_consecutive >= 2 or limit_up_count >= 2)

        # 5. 分析支撑位（简化版，检查是否接近前一日低点）
        current_low = float(stock['low_price']) if stock['low_price'] else 0
        prev_low = float(prev_data['low_price']) if prev_data and prev_data['low_price'] else 0

        has_support = False
        support_distance = 0
        if prev_low > 0 and current_low > 0:
            support_distance_pct = abs(current_low - prev_low) / prev_low * 100
            # 严格标准：3%以内
            has_support = support_distance_pct < 3.0
            support_distance = support_distance_pct

        # 综合判断：弱转强候选股
        # 条件：当日弱势下跌 + 前一天也弱势下跌 + 是强势股 + 到达支撑位
        is_candidate = (pct_chg < -2.0 and prev_weak and is_strong and has_support)

        if is_candidate:
            candidates.append({
                'stock_id': stock_id,
                'stock_name': stock_name,
                'pct_chg': pct_chg,
                'prev_pct_chg': prev_pct_chg,
                'limit_up_count': limit_up_count,
                'max_consecutive': max_consecutive,
                'is_strong': is_strong,
                'has_support': has_support,
                'support_distance': support_distance,
                'theme_key': theme_key
            })

    print(f"\n严格筛选后的候选股数量: {len(candidates)}")

    if candidates:
        print(f"\n严格筛选后的候选股列表:")
        print("-" * 80)
        for i, cand in enumerate(candidates, 1):
            print(f"{i:2d}. {cand['stock_id']} {cand['stock_name']}")
            print(f"    今日跌幅: {cand['pct_chg']:.1f}%, 昨日跌幅: {cand['prev_pct_chg']:.1f}%")
            print(f"    涨停次数: {cand['limit_up_count']}, 最大连续: {cand['max_consecutive']}")
            print(f"    支撑距离: {cand['support_distance']:.1f}%, 主题: {cand['theme_key']}")
            print()

    # 分析主题分布
    print(f"\n主题分布分析:")
    print("-" * 80)
    theme_counts = {}
    for cand in candidates:
        theme = cand['theme_key']
        theme_counts[theme] = theme_counts.get(theme, 0) + 1

    sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
    for theme, count in sorted_themes[:10]:  # 显示前10个主题
        print(f"  主题 {theme}: {count}只股票")

    # 分析涨停模式分布
    print(f"\n涨停模式分析:")
    print("-" * 80)
    consecutive_dist = {}
    for cand in candidates:
        consecutive = cand['max_consecutive']
        consecutive_dist[consecutive] = consecutive_dist.get(consecutive, 0) + 1

    for consecutive, count in sorted(consecutive_dist.items()):
        print(f"  连续{consecutive}天涨停: {count}只股票")

    # 分析支撑距离分布
    print(f"\n支撑距离分析:")
    print("-" * 80)
    distance_ranges = {'<1%': 0, '1-2%': 0, '2-3%': 0, '>=3%': 0}
    for cand in candidates:
        distance = cand['support_distance']
        if distance < 1.0:
            distance_ranges['<1%'] += 1
        elif distance < 2.0:
            distance_ranges['1-2%'] += 1
        elif distance < 3.0:
            distance_ranges['2-3%'] += 1
        else:
            distance_ranges['>=3%'] += 1

    for range_name, count in distance_ranges.items():
        print(f"  支撑距离{range_name}: {count}只股票")

    await conn.close()

async def main():
    try:
        await analyze_candidates()
    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())