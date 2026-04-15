#!/usr/bin/env python3
"""
测试神剑股份弱转强条件验证
"""
import asyncio
import asyncpg
from datetime import date, timedelta
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService

async def test():
    stock_id = "002361"
    test_date = date(2026, 4, 7)  # 弱转强日

    print(f"测试神剑股份弱转强条件验证 - {test_date}")
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

    # 获取当日数据
    query = """
    SELECT stock_id, stock_name, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    LIMIT 1
    """

    row = await conn.fetchrow(query, stock_id, test_date)

    if not row:
        print("未找到神剑股份当日数据")
        await conn.close()
        return

    print(f"神剑股份当日数据:")
    print(f"  涨跌幅: {row['pct_chg']}%")
    print(f"  是否涨停: {'✅是' if float(row['pct_chg']) >= 9.9 else '❌否'}")
    print(f"  主题key: {row['subject_key']}")
    print(f"  开盘价: {row['open_price']}")
    print(f"  最高价: {row['high_price']}")
    print(f"  最低价: {row['low_price']}")
    print(f"  收盘价: {row['close_price']}")

    # 检查数据质量问题
    high = float(row['high_price'])
    low = float(row['low_price'])
    if high < low:
        print(f"  ⚠️  数据异常: high_price ({high}) < low_price ({low})")

    # 涨停模式分析
    strong_service = StrongStockAnalysisService()
    stock_data = dict(row)
    stock_data['trade_date'] = test_date

    # 分析涨停模式（7个交易日）
    limit_up_pattern = await strong_service._analyze_limit_up_pattern(stock_id, test_date, trading_days=7)

    print(f"\n涨停模式分析结果（7个交易日）:")
    print(f"  涨停模式: {limit_up_pattern.get('pattern_type', 'N/A')}")
    print(f"  涨停次数: {limit_up_pattern.get('limit_up_count', 0)}")
    print(f"  最长连续涨停: {limit_up_pattern.get('max_consecutive_days', 0)}天")
    print(f"  涨停日期: {limit_up_pattern.get('limit_up_dates', [])}")
    print(f"  分析周期: {limit_up_pattern.get('analysis_period', 'N/A')}")
    print(f"  是否有涨停模式: {'✅是' if limit_up_pattern.get('has_limit_up_pattern', False) else '❌否'}")

    # 检查更长时间范围（30个交易日）查看是否有历史涨停
    limit_up_pattern_30 = await strong_service._analyze_limit_up_pattern(stock_id, test_date, trading_days=30)
    print(f"\n涨停模式分析结果（30个交易日）:")
    print(f"  涨停次数: {limit_up_pattern_30.get('limit_up_count', 0)}")
    print(f"  最长连续涨停: {limit_up_pattern_30.get('max_consecutive_days', 0)}天")
    print(f"  涨停日期: {limit_up_pattern_30.get('limit_up_dates', [])}")

    # 缺口支撑分析
    kline_service = KlineDataService()
    gap_analysis = await kline_service.analyze_gap_support(stock_id, test_date)

    print(f"\n缺口支撑分析结果:")
    print(f"  是否有缺口: {'✅是' if gap_analysis.get('has_gap', False) else '❌否'}")
    print(f"  缺口类型: {gap_analysis.get('gap_type', 'N/A')}")
    print(f"  是否有缺口支撑: {'✅是' if gap_analysis.get('is_gap_support', False) else '❌否'}")
    print(f"  缺口支撑位: {gap_analysis.get('gap_support_level', 0)}")

    if gap_analysis.get('technical_signals'):
        print(f"  技术信号:")
        for signal in gap_analysis['technical_signals'][:5]:  # 只显示前5个
            print(f"    - {signal}")

    # 弱转强条件检查
    print(f"\n弱转强条件检查:")
    condition1 = float(row['pct_chg']) < -2.0
    print(f"  1. 当日弱势下跌 (<-2%): {row['pct_chg']}% → {'✅是' if condition1 else '❌否'}")

    condition2 = limit_up_pattern.get('has_limit_up_pattern', False) or limit_up_pattern_30.get('has_limit_up_pattern', False)
    print(f"  2. 前期强势（有涨停模式）: {'✅是' if condition2 else '❌否'}")

    condition3 = gap_analysis.get('is_gap_support', False)
    print(f"  3. 到达支撑位（缺口支撑）: {'✅是' if condition3 else '❌否'}")

    if condition1 and condition2 and condition3:
        print(f"\n🎯 神剑股份满足弱转强所有条件！")
    else:
        print(f"\n❌ 神剑股份不满足弱转强条件")
        missing = []
        if not condition1: missing.append("当日弱势下跌")
        if not condition2: missing.append("前期强势")
        if not condition3: missing.append("到达支撑位")
        print(f"  缺失条件: {', '.join(missing)}")

    # 检查数据库中有哪些交易日数据
    print(f"\n检查神剑股份的历史交易日（最近30天）:")
    history_query = """
    SELECT trade_date, pct_chg, is_leader, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date <= $2
    ORDER BY trade_date DESC
    LIMIT 30
    """
    history_rows = await conn.fetch(history_query, stock_id, test_date)

    if history_rows:
        print(f"  最近{len(history_rows)}个交易日:")
        for h in history_rows[:10]:  # 显示最近10个
            pct = float(h['pct_chg'])
            is_limit = pct >= 9.9
            print(f"    {h['trade_date']}: {pct:6.2f}% {'✅涨停' if is_limit else ''}")
    else:
        print(f"  无历史数据")

    await conn.close()
    await strong_service.close()
    await kline_service.close()

if __name__ == "__main__":
    asyncio.run(test())
