#!/usr/bin/env python3
"""
测试神剑股份4/8弱转强信号
"""
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.weak_to_strong_service import WeakToStrongService
from stock_service.services.kline_data_service import KlineDataService

async def test():
    stock_id = "002361"
    trade_date = date(2026, 4, 8)
    prev_date = date(2026, 4, 7)

    print(f"测试神剑股份弱转强信号")
    print(f"股票: {stock_id}")
    print(f"日期: {trade_date}")
    print(f"前一日: {prev_date}")
    print("=" * 70)

    # 1. 强势股分析
    strong_service = StrongStockAnalysisService()
    kline_service = KlineDataService()

    # 获取股票数据
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    import asyncpg
    conn = await asyncpg.connect(**config)

    query = """
    SELECT stock_id, stock_name, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    LIMIT 1
    """
    row = await conn.fetchrow(query, stock_id, trade_date)
    if not row:
        print("未找到当日数据")
        await conn.close()
        return

    stock_data = dict(row)
    stock_data['trade_date'] = trade_date

    # 前一日数据
    prev_row = await conn.fetchrow(query, stock_id, prev_date)
    prev_stock_data = dict(prev_row) if prev_row else None

    await conn.close()

    print(f"当日数据: 涨跌幅 {stock_data['pct_chg']}%, 是否龙头 {stock_data['is_leader']}, 排名 {stock_data['rank_order']}")
    if prev_stock_data:
        print(f"前一日数据: 涨跌幅 {prev_stock_data['pct_chg']}%, 是否龙头 {prev_stock_data['is_leader']}, 排名 {prev_stock_data['rank_order']}")

    # 强势股分析
    strong_analysis = await strong_service.analyze_stock_by_pdf_framework(stock_id, trade_date, stock_data)
    print(f"\n强势股分析结果:")
    print(f"  是否为强势股: {'✅ 是' if strong_analysis['is_strong_stock'] else '❌ 否'}")
    print(f"  总体评分: {strong_analysis['overall_score']}/100")
    print(f"  龙头属性评分: {strong_analysis['dimensions'].get('龙头属性', {}).get('score', 0)}")
    print(f"  是否领涨评分: {strong_analysis['dimensions'].get('是否领涨', {}).get('score', 0)}")

    # 2. K线缺口支撑分析
    gap_analysis = await kline_service.analyze_gap_support(stock_id, trade_date)
    print(f"\nK线缺口支撑分析:")
    print(f"  是否有缺口: {gap_analysis.get('has_gap', False)}")
    print(f"  是否有支撑: {gap_analysis.get('has_support', False)}")
    if gap_analysis.get('has_support'):
        print(f"  支撑类型: {gap_analysis.get('support_type', '')}")
        print(f"  支撑强度: {gap_analysis.get('support_strength', 0)}")

    # 3. 弱转强信号检测
    weak_service = WeakToStrongService()
    # 构建输入
    inputs = {
        'prev_day_pct_chg': float(prev_stock_data['pct_chg']) if prev_stock_data else None,
        'today_pct_chg': float(stock_data['pct_chg']),
        'prev_day_weak': prev_stock_data and float(prev_stock_data['pct_chg']) < -2.0,
        'today_strong': float(stock_data['pct_chg']) > 0 and float(stock_data['pct_chg']) > (float(prev_stock_data['pct_chg']) if prev_stock_data else 0) + 3.0,
        'gap_support_analysis': gap_analysis,
        'strong_stock_overall_score': strong_analysis['overall_score'],
        'is_strong_stock': strong_analysis['is_strong_stock']
    }
    print(f"\n弱转强信号检测输入:")
    print(f"  前一日涨跌幅: {inputs['prev_day_pct_chg']}%")
    print(f"  当日涨跌幅: {inputs['today_pct_chg']}%")
    print(f"  前一日弱势: {inputs['prev_day_weak']}")
    print(f"  当日转强: {inputs['today_strong']}")
    print(f"  强势股状态: {inputs['is_strong_stock']}")

    # 计算信号强度和置信度
    from real_weak_to_strong_screening_enhanced import RealDatabaseScreener
    screener = RealDatabaseScreener()
    signal_strength = screener._calculate_weak_to_strong_strength(
        inputs['prev_day_pct_chg'],
        inputs['today_pct_chg'],
        inputs['prev_day_weak'],
        inputs['today_strong'],
        gap_analysis,
        strong_analysis['overall_score'],
        None, None  # 无K线数据
    )
    confidence = screener._calculate_weak_to_strong_confidence(
        inputs['prev_day_pct_chg'],
        inputs['today_pct_chg'],
        gap_analysis,
        strong_analysis['overall_score'],
        strong_analysis['is_strong_stock']
    )
    print(f"\n弱转强信号计算结果:")
    print(f"  信号强度: {signal_strength:.1f}/100")
    print(f"  置信度: {confidence:.1f}%")

    # 判断是否为弱转强
    is_weak_to_strong = (
        strong_analysis['is_strong_stock'] and
        inputs['prev_day_weak'] and
        inputs['today_strong'] and
        signal_strength >= 60.0 and
        confidence >= 60.0
    )
    print(f"\n弱转强结论: {'✅ 是弱转强信号' if is_weak_to_strong else '❌ 非弱转强信号'}")

    await strong_service.close()
    await kline_service.close()
    print("\n测试完成")

if __name__ == "__main__":
    asyncio.run(test())