#!/usr/bin/env python3
"""
直接测试神剑股份弱转强条件（绕过主题限制）
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService

async def test_shenjian_direct():
    stock_id = "002361"
    trade_date = date(2026, 4, 7)

    print(f"直接测试神剑股份弱转强条件 - {trade_date}")
    print("=" * 70)

    # 连接数据库
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    # 获取股票当日数据
    query = """
    SELECT stock_id, stock_name, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    """
    row = await conn.fetchrow(query, stock_id, trade_date)

    if not row:
        print("未找到股票数据")
        await conn.close()
        return

    stock_data = dict(row)
    stock_data['trade_date'] = trade_date

    print(f"股票数据:")
    print(f"  涨跌幅: {stock_data['pct_chg']:.1f}%")
    print(f"  开盘价: {stock_data['open_price']:.2f}")
    print(f"  最高价: {stock_data['high_price']:.2f}")
    print(f"  最低价: {stock_data['low_price']:.2f}")
    print(f"  收盘价: {stock_data['close_price']:.2f}")
    print(f"  主题key: {stock_data['subject_key']}")

    # 条件1: 当日弱势下跌（<-2%）
    pct_chg = float(stock_data['pct_chg'])
    condition1 = pct_chg < -2.0
    print(f"\n条件1 - 当日弱势下跌 (<-2%): {'✅满足' if condition1 else '❌不满足'} ({pct_chg:.1f}%)")

    if not condition1:
        print("  跳过进一步分析")
        await conn.close()
        return

    # 条件2: 检查前期是否强势股（分析涨停模式）
    strong_service = StrongStockAnalysisService()
    limit_up_pattern = await strong_service._analyze_limit_up_pattern(
        stock_id, trade_date, trading_days=7
    )

    has_strong_history = limit_up_pattern['has_limit_up_pattern']
    limit_up_count = limit_up_pattern['limit_up_count']
    max_consecutive = limit_up_pattern['max_consecutive_days']
    pattern_type = limit_up_pattern['pattern_type']

    condition2 = has_strong_history
    print(f"\n条件2 - 前期强势表现:")
    print(f"  涨停模式: {pattern_type}")
    print(f"  涨停次数: {limit_up_count}")
    print(f"  最长连续涨停: {max_consecutive}天")
    print(f"  是否有涨停模式: {'✅满足' if condition2 else '❌不满足'}")

    if not condition2:
        print("  跳过进一步分析")
        await strong_service.close()
        await conn.close()
        return

    # 条件3: 检查缺口支撑（技术形态分析）
    kline_service = KlineDataService()
    gap_analysis = await kline_service.analyze_gap_support(stock_id, trade_date)

    print(f"\n条件3 - 缺口支撑分析:")
    for key, value in gap_analysis.items():
        if key == 'technical_signals':
            if value:
                print(f"  {key}:")
                for signal in value:
                    print(f"    - {signal}")
        else:
            print(f"  {key}: {value}")

    # 检查是否有缺口支撑
    has_gap_support = gap_analysis.get('is_gap_support', False)
    gap_support_level = gap_analysis.get('gap_support_level', 0)

    # 如果没有检测到缺口支撑，手动检查历史缺口
    if not has_gap_support:
        print(f"\n  ⚠️  算法未检测到缺口支撑，手动检查历史缺口...")

        # 获取更多历史数据（10天）
        history_query = """
        SELECT trade_date, open_price, high_price, low_price, close_price, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date <= $2 AND trade_date >= $2 - INTERVAL '10 days'
        ORDER BY trade_date
        """
        history_rows = await conn.fetch(history_query, stock_id, trade_date)

        # 查找缺口
        gaps = []
        for i in range(1, len(history_rows)):
            prev = history_rows[i-1]
            curr = history_rows[i]

            prev_close = float(prev['close_price'])
            curr_open = float(curr['open_price'])

            # 检查向上缺口
            if curr_open > prev_close * 1.001:  # 0.1%阈值
                gap_size = (curr_open - prev_close) / prev_close * 100
                gap_info = {
                    'date': curr['trade_date'],
                    'type': 'up',
                    'gap_range': (prev_close, curr_open),
                    'size_pct': gap_size
                }
                gaps.append(gap_info)
                print(f"    发现向上缺口: {prev['trade_date']}收盘{prev_close:.2f} → {curr['trade_date']}开盘{curr_open:.2f} (缺口{curr_open-prev_close:.2f}, {gap_size:.2f}%)")

        # 检查当前价格是否回补了关键缺口（选择最早且显著的缺口作为关键支撑位）
        current_low = float(stock_data['low_price'])
        if gaps:
            # 选择最早且显著的缺口作为关键支撑位
            # 优先选择最早出现的缺口（通常是突破缺口），且缺口大小 > 0.5%
            significant_gaps = [g for g in gaps if g['size_pct'] > 0.5]
            if significant_gaps:
                # 按日期排序，选择最早的显著缺口
                significant_gaps.sort(key=lambda x: x['date'])
                key_gap = significant_gaps[0]
            else:
                # 如果没有显著缺口，选择最早的缺口
                gaps.sort(key=lambda x: x['date'])
                key_gap = gaps[0]

            gap_lower, gap_upper = key_gap['gap_range']
            print(f"    关键缺口: [{gap_lower:.2f}, {gap_upper:.2f}] date={key_gap['date']}, size={key_gap['size_pct']:.2f}%")

            # 只有价格跌破关键缺口下沿才算到达支撑位
            if current_low <= gap_lower:
                print(f"    ✅ 价格已回补关键缺口（当前最低{current_low:.2f} ≤ 缺口下沿{gap_lower:.2f}）")
                has_gap_support = True
                gap_support_level = gap_lower
            else:
                print(f"    ⚠️  价格未回补关键缺口（当前最低{current_low:.2f} > 缺口下沿{gap_lower:.2f}）")
                has_gap_support = False
        else:
            print(f"    未发现缺口")

    condition3 = has_gap_support
    print(f"\n条件3 - 到达支撑位: {'✅满足' if condition3 else '❌不满足'}")

    # 弱转强条件：前期强势 + 当日弱势下跌 + 到达支撑位
    is_weak_to_strong = condition1 and condition2 and condition3

    print(f"\n{'='*70}")
    print(f"弱转强判定结果:")
    print(f"  条件1（当日弱势下跌）: {'✅' if condition1 else '❌'}")
    print(f"  条件2（前期强势）: {'✅' if condition2 else '❌'}")
    print(f"  条件3（到达支撑位）: {'✅' if condition3 else '❌'}")
    print(f"  综合判定: {'🎯 弱转强候选股！' if is_weak_to_strong else '❌ 不满足弱转强条件'}")

    await strong_service.close()
    await kline_service.close()
    await conn.close()

    return is_weak_to_strong

if __name__ == "__main__":
    result = asyncio.run(test_shenjian_direct())
    print(f"\n结论: 神剑股份在4/7日{'是' if result else '不是'}弱转强候选股")