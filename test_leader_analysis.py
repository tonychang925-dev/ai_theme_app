#!/usr/bin/env python3
"""
测试龙头股票的强势股分析
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService

async def test_leader_stock():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    # 查找2026-04-10日的龙头股票
    query = """
    SELECT stock_id, stock_name, pct_chg, is_leader, rank_order, subject_key
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1 AND is_leader = TRUE
    ORDER BY rank_order ASC
    LIMIT 5
    """

    trade_date = date(2026, 4, 10)
    rows = await conn.fetch(query, trade_date)

    print(f"找到 {len(rows)} 个龙头股票")

    service = StrongStockAnalysisService()

    for row in rows:
        stock_id = row['stock_id']
        stock_name = row['stock_name']
        print(f"\n{'='*60}")
        print(f"分析龙头股票: {stock_name} ({stock_id})")
        print(f"  当日涨跌幅: {row['pct_chg']}%")
        print(f"  排名顺序: {row['rank_order']}")

        # 构建股票数据
        stock_data = dict(row)
        stock_data['trade_date'] = trade_date

        # 进行PDF框架分析
        analysis = await service.analyze_stock_by_pdf_framework(stock_id, trade_date, stock_data)

        print(f"  是否为强势股: {'✅ 是' if analysis['is_strong_stock'] else '❌ 否'}")
        print(f"  总体评分: {analysis['overall_score']}/100")

        # 打印龙头属性维度
        dragon_head = analysis['dimensions'].get('龙头属性', {})
        print(f"  龙头属性评分: {dragon_head.get('score', 0)}")
        print(f"  龙头级别: {dragon_head.get('dragon_head_level', 'N/A')}")
        print(f"  连续龙头: {dragon_head.get('consecutive_leader', False)}")

        # 检查是否符合二板定龙头
        if dragon_head.get('dragon_head_level', '').startswith('绝对龙头'):
            print(f"  ✅ 符合'二板定龙头'原则")
        else:
            print(f"  ⚠️  不符合'二板定龙头'原则")

        # 打印是否领涨维度
        lingzhang = analysis['dimensions'].get('是否领涨', {})
        print(f"  是否领涨评分: {lingzhang.get('score', 0)}")

        # 打印其他维度简要
        print(f"  其他维度评分:")
        for dim_name, dim_data in analysis['dimensions'].items():
            if dim_name not in ['龙头属性', '是否领涨']:
                print(f"    {dim_name}: {dim_data.get('score', 0)}分")

    await conn.close()
    await service.close()
    print("\n测试完成")

if __name__ == "__main__":
    asyncio.run(test_leader_stock())