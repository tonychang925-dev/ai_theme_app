#!/usr/bin/env python3
"""
测试神剑股份涨停模式分析
"""
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService

async def test():
    stock_id = "002361"
    trade_date = date(2026, 4, 8)  # 4/8日是涨停日

    print(f"测试神剑股份涨停模式分析 - {trade_date}")
    print(f"股票: {stock_id}")
    print("=" * 70)

    # 获取股票数据
    import asyncpg
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    query = """
    SELECT stock_id, stock_name, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    ORDER BY rank_order ASC
    LIMIT 1
    """

    row = await conn.fetchrow(query, stock_id, trade_date)
    await conn.close()

    if not row:
        print("未找到股票数据")
        return

    stock_data = dict(row)
    stock_data['trade_date'] = trade_date

    print(f"股票数据:")
    print(f"  涨跌幅: {stock_data['pct_chg']}%")
    print(f"  是否涨停: {'✅是' if float(stock_data['pct_chg']) >= 9.9 else '❌否'}")
    print(f"  是否龙头: {stock_data['is_leader']}")
    print(f"  排名顺序: {stock_data['rank_order']}")
    print(f"  主题key: {stock_data['subject_key']}")

    # 强势股分析（包含涨停模式分析）
    strong_service = StrongStockAnalysisService()

    strong_analysis = await strong_service.analyze_stock_by_pdf_framework(
        stock_id,
        trade_date,
        stock_data
    )

    print(f"\n涨停模式分析结果:")
    if 'limit_up_pattern' in strong_analysis:
        pattern_data = strong_analysis['limit_up_pattern']
        print(f"  涨停模式: {pattern_data.get('pattern_type', 'N/A')}")
        print(f"  涨停次数: {pattern_data.get('limit_up_count', 0)}")
        print(f"  最长连续涨停: {pattern_data.get('max_consecutive_days', 0)}天")
        print(f"  涨停日期: {pattern_data.get('limit_up_dates', [])}")
        print(f"  分析周期: {pattern_data.get('analysis_period', 'N/A')}")
        print(f"  强度评分: {pattern_data.get('strength_score', 0)}")
        print(f"  分析原因: {pattern_data.get('reason', 'N/A')}")
        print(f"  是否有涨停模式: {'✅是' if pattern_data.get('has_limit_up_pattern', False) else '❌否'}")

    print(f"\n强势股分析结果:")
    print(f"  是否为强势股: {'✅ 是' if strong_analysis['is_strong_stock'] else '❌ 否'}")
    print(f"  总体评分: {strong_analysis['overall_score']}/100")

    # 打印涨停类型维度评分
    print(f"\n涨停类型维度:")
    limit_up_dim = strong_analysis['dimensions'].get('涨停类型', {})
    print(f"  评分: {limit_up_dim.get('score', 0)}")
    print(f"  类型: {limit_up_dim.get('limit_up_type', 'N/A')}")
    if limit_up_dim.get('reasons'):
        for reason in limit_up_dim['reasons']:
            print(f"    - {reason}")

    # 打印龙头属性维度
    print(f"\n龙头属性维度:")
    dragon_dim = strong_analysis['dimensions'].get('龙头属性', {})
    print(f"  评分: {dragon_dim.get('score', 0)}")
    print(f"  龙头等级: {dragon_dim.get('dragon_head_level', 'N/A')}")
    if dragon_dim.get('reasons'):
        for reason in dragon_dim['reasons']:
            print(f"    - {reason}")

    # 快速通道判定详情
    print(f"\n快速通道判定:")
    if strong_analysis['is_strong_stock'] and 'limit_up_pattern' in strong_analysis:
        pattern_data = strong_analysis['limit_up_pattern']
        max_consecutive = pattern_data.get('max_consecutive_days', 0)
        limit_up_count = pattern_data.get('limit_up_count', 0)

        if max_consecutive >= 2:
            print(f"  ✅ 连续{max_consecutive}天涨停，触发快速通道")
        elif limit_up_count >= 2:
            print(f"  ✅ {pattern_data.get('analysis_period', '5')}天内{limit_up_count}次涨停，触发快速通道")
        elif limit_up_dim.get('score', 0) >= 80 and limit_up_count >= 1:
            print(f"  ✅ 当日涨停且{pattern_data.get('analysis_period', '5')}天内{limit_up_count}次涨停，触发快速通道")
        else:
            print(f"  ⚠️  未触发快速通道，通过正常流程判定")

    await strong_service.close()

    return strong_analysis['is_strong_stock']

if __name__ == "__main__":
    is_strong = asyncio.run(test())
    print(f"\n结论: 神剑股份在4/8日{'是' if is_strong else '不是'}强势股")