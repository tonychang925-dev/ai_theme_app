#!/usr/bin/env python3
"""
调试神剑股份在4月10日的弱转强筛选问题
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_weak_to_strong_screening import EnhancedWeakToStrongScreener
from stock_service.services.kline_data_service import KlineDataService
from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService

async def debug_shenjian():
    stock_id = "002361"
    test_date = date(2026, 4, 10)

    print(f"调试神剑股份弱转强筛选 - {stock_id} - {test_date}")
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

    # 1. 检查当日数据
    print("1. 检查当日数据 (2026-04-10):")
    print("-" * 40)

    daily_query = """
    SELECT stock_id, stock_name, pct_chg, open_price, high_price, low_price, close_price,
           volume, amount, limit_up, is_leader, rank_order, subject_key
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    ORDER BY rank_order NULLS LAST
    """
    daily_rows = await conn.fetch(daily_query, stock_id, test_date)

    if not daily_rows:
        print(f"  ❌ 未找到{test_date}的数据")
        await conn.close()
        return

    row = daily_rows[0]
    print(f"  ✅ 找到当日数据:")
    print(f"     股票: {row['stock_id']} {row['stock_name']}")
    print(f"     涨跌幅: {row['pct_chg']:.1f}%")
    print(f"     开盘: {row['open_price']:.2f}, 收盘: {row['close_price']:.2f}")
    print(f"     最高: {row['high_price']:.2f}, 最低: {row['low_price']:.2f}")
    print(f"     主题: {row['subject_key']}")

    # 条件1: 当日弱势下跌 (<-2%)
    pct_chg = float(row['pct_chg'])
    is_weak_day = pct_chg < -2.0
    print(f"  {'✅' if is_weak_day else '❌'} 弱势下跌检查: {pct_chg:.1f}% (<-2.0%)")

    await conn.close()

    # 2. 检查涨停模式
    print(f"\n2. 检查涨停模式:")
    print("-" * 40)

    screener = EnhancedWeakToStrongScreener()
    await screener.connect()

    # 使用strong_stock_analysis_service检查涨停模式
    strong_analysis_service = StrongStockAnalysisService()

    limit_up_pattern = await strong_analysis_service._analyze_limit_up_pattern(
        stock_id, test_date, trading_days=7
    )

    print(f"  has_limit_up_pattern: {limit_up_pattern['has_limit_up_pattern']}")
    print(f"  limit_up_count: {limit_up_pattern['limit_up_count']}")
    print(f"  max_consecutive_days: {limit_up_pattern['max_consecutive_days']}")
    print(f"  pattern_type: {limit_up_pattern['pattern_type']}")

    has_strong_history = limit_up_pattern['has_limit_up_pattern']
    print(f"  {'✅' if has_strong_history else '❌'} 前期强势检查: {has_strong_history}")

    # 检查是否需要缺口支撑
    requires_gap = screener._requires_gap_support(limit_up_pattern)
    print(f"  是否需要缺口支撑: {requires_gap}")

    # 3. 检查支撑位
    print(f"\n3. 检查支撑位:")
    print("-" * 40)

    kline_service = KlineDataService()

    gap_analysis = await kline_service.analyze_gap_support(stock_id, test_date)

    print(f"  has_support: {gap_analysis.get('has_support', False)}")
    print(f"  support_strength: {gap_analysis.get('support_strength', 0.0):.1f}")
    print(f"  has_gap_support: {gap_analysis.get('is_gap_support', False)}")
    print(f"  support_type: {gap_analysis.get('support_type', 'unknown')}")
    print(f"  support_level: {gap_analysis.get('support_level', 0.0):.2f}")
    print(f"  gap_support_level: {gap_analysis.get('gap_support_level', 0.0):.2f}")

    has_gap_support = gap_analysis.get('is_gap_support', False)
    has_support = gap_analysis.get('has_support', False)
    support_strength = gap_analysis.get('support_strength', 0.0)

    # 根据逻辑判断是否有有效支撑
    has_valid_support = False
    support_type = ''

    if has_gap_support:
        has_valid_support = True
        support_type = 'gap'
        support_level = gap_analysis.get('gap_support_level', 0.0)
        print(f"  ✅ 检测到缺口支撑: {support_level:.2f}")
    elif has_support and support_strength >= 0.6:
        if requires_gap:
            print(f"  ⚠️  需要缺口支撑但未检测到（检测到{gap_analysis.get('support_type', 'unknown')}支撑，强度:{support_strength:.1f}）")
            has_valid_support = False
        else:
            has_valid_support = True
            support_type = gap_analysis.get('support_type', 'unknown')
            support_level = gap_analysis.get('support_level', 0.0)
            print(f"  ✅ 检测到{support_type}支撑: {support_level:.2f} (强度:{support_strength:.1f})")
    else:
        if requires_gap:
            print(f"  ⚠️  需要缺口支撑但未检测到（无有效支撑或强度不足）")
        else:
            print(f"  ⚠️  无有效支撑位或支撑强度不足 (has_support={has_support}, strength={support_strength:.1f})")

    print(f"  {'✅' if has_valid_support else '❌'} 支撑位检查: {has_valid_support}")

    # 4. 综合判断
    print(f"\n4. 综合判断:")
    print("-" * 40)

    is_weak_to_strong = is_weak_day and has_strong_history and has_valid_support
    print(f"  弱势下跌 (<-2%): {is_weak_day} (实际: {pct_chg:.1f}%)")
    print(f"  前期强势: {has_strong_history}")
    print(f"  到达支撑位: {has_valid_support}")
    print(f"\n  {'🎯 符合弱转强条件' if is_weak_to_strong else '❌ 不符合弱转强条件'}")

    # 如果不符合条件，具体分析失败原因
    if not is_weak_to_strong:
        print(f"\n详细失败原因:")
        if not is_weak_day:
            print(f"  - 跌幅{pct_chg:.1f}%不符合弱势下跌条件 (<-2.0%)")
        if not has_strong_history:
            print(f"  - 前期没有强势涨停模式")
        if not has_valid_support:
            print(f"  - 未到达有效支撑位")
            if requires_gap:
                print(f"    * 需要缺口支撑但未检测到")
            elif has_support and support_strength < 0.6:
                print(f"    * 检测到支撑但强度不足 ({support_strength:.1f} < 0.6)")
            elif not has_support:
                print(f"    * 未检测到任何支撑")

    await kline_service.close()
    await screener.close()

async def main():
    try:
        await debug_shenjian()
    except Exception as e:
        print(f"\n❌ 调试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())