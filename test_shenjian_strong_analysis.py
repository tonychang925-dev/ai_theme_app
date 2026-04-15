#!/usr/bin/env python3
"""
测试神剑股份在4/7日的强势股分析
"""
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService

async def test():
    stock_id = "002361"
    trade_date = date(2026, 4, 7)

    print(f"测试神剑股份强势股分析 - {trade_date}")
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
    print(f"  是否龙头: {stock_data['is_leader']}")
    print(f"  排名顺序: {stock_data['rank_order']}")
    print(f"  主题key: {stock_data['subject_key']}")

    # 强势股分析
    strong_service = StrongStockAnalysisService()

    strong_analysis = await strong_service.analyze_stock_by_pdf_framework(
        stock_id,
        trade_date,
        stock_data
    )

    print(f"\n强势股分析结果:")
    print(f"  是否为强势股: {'✅ 是' if strong_analysis['is_strong_stock'] else '❌ 否'}")
    print(f"  总体评分: {strong_analysis['overall_score']}/100")

    # 打印所有维度评分
    print(f"\n详细维度评分:")
    for dim_name, dim_data in strong_analysis['dimensions'].items():
        print(f"  {dim_name}: {dim_data.get('score', 0)}分")
        if dim_data.get('reasons'):
            for reason in dim_data['reasons'][:2]:
                print(f"    - {reason}")

    # 检查强势股条件
    is_strong = strong_analysis['is_strong_stock']
    overall_score = strong_analysis['overall_score']

    print(f"\n强势股判定:")
    print(f"  总体评分: {overall_score} {'(≥70)' if overall_score >= 70 else '(＜70)'}")
    print(f"  是否为正宗: {strong_analysis['dimensions'].get('是否正宗', {}).get('score', 0)} {'(≥60)' if strong_analysis['dimensions'].get('是否正宗', {}).get('score', 0) >= 60 else '(＜60)'}")
    print(f"  是否为领涨: {strong_analysis['dimensions'].get('是否领涨', {}).get('score', 0)} {'(≥60)' if strong_analysis['dimensions'].get('是否领涨', {}).get('score', 0) >= 60 else '(＜60)'}")
    print(f"  龙头属性: {strong_analysis['dimensions'].get('龙头属性', {}).get('score', 0)} {'(≥70)' if strong_analysis['dimensions'].get('龙头属性', {}).get('score', 0) >= 70 else '(＜70)'}")

    await strong_service.close()

    return is_strong

if __name__ == "__main__":
    is_strong = asyncio.run(test())
    print(f"\n结论: 神剑股份在4/7日{'是' if is_strong else '不是'}强势股")