#!/usr/bin/env python3
"""查询候选池中的神剑股份"""

import asyncio
import asyncpg
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_service.config import StockServiceConfig

async def query_pool():
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
    next_date = date(2026, 4, 8)

    print("🔍 查询候选池中的神剑股份")
    print(f"日期: {analysis_date}, 下一个交易日: {next_date}")
    print()

    # 查询候选池
    query = """
    SELECT *
    FROM weak_to_strong_candidate_pool
    WHERE next_trade_date = $1 AND stock_id LIKE $2
    """

    # 尝试不同股票ID格式
    for sid in [stock_id, stock_id + ".SZ", "SZ" + stock_id]:
        rows = await conn.fetch(query, next_date, sid)
        if rows:
            print(f"✅ 找到神剑股份候选记录 (股票ID: {sid}):")
            for row in rows:
                print(f"  候选评分: {row.get('candidate_score', 'N/A')}")
                print(f"  准入类型: {row.get('pool_entry_type', 'N/A')}")
                print(f"  周期状态: {row.get('cycle_state', 'N/A')}")
                print(f"  主线存活: {row.get('mainline_strength_score', 'N/A')}")
                print(f"  退潮观察: {row.get('fade_watch', 'N/A')}")
                print(f"  退潮确认: {row.get('fade_confirmed', 'N/A')}")
                print(f"  规则版本: {row.get('rule_version', 'N/A')}")
            break
    else:
        print("❌ 未在候选池中找到神剑股份")

    # 检查所有候选股
    print()
    print("📊 候选池概览 (2026-04-08):")
    overview_query = """
    SELECT pool_entry_type, COUNT(*) as cnt,
           AVG(candidate_score) as avg_score
    FROM weak_to_strong_candidate_pool
    WHERE next_trade_date = $1
    GROUP BY pool_entry_type
    ORDER BY pool_entry_type
    """
    overview = await conn.fetch(overview_query, next_date)
    for row in overview:
        print(f"  准入类型 {row['pool_entry_type']}: {row['cnt']} 只, 平均评分 {row['avg_score']:.1f}")

    # 查看几个候选股的详细信息
    print()
    print("🔍 候选股示例:")
    sample_query = """
    SELECT stock_id, stock_name, candidate_score, pool_entry_type,
           cycle_state, mainline_strength_score
    FROM weak_to_strong_candidate_pool
    WHERE next_trade_date = $1
    ORDER BY candidate_score DESC
    LIMIT 5
    """
    samples = await conn.fetch(sample_query, next_date)
    for i, row in enumerate(samples, 1):
        print(f"  {i}. {row['stock_id']} {row['stock_name']}: 评分{row['candidate_score']:.1f}, 准入{row['pool_entry_type']}, 周期{row['cycle_state']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(query_pool())