#!/usr/bin/env python3
"""检查神剑股份主题的主线判断数据"""

import asyncio
import asyncpg
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_service.config import StockServiceConfig

async def check_mainline():
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

    print("🔍 检查神剑股份主题的主线判断")
    print(f"日期: {analysis_date}, 股票: {stock_id}")
    print()

    # 1. 获取主题映射
    theme_query = """
    SELECT DISTINCT tsm.subject_key, tsm.theme_name, tsm.confidence
    FROM theme_stock_map tsm
    WHERE tsm.stock_id = $1
    ORDER BY tsm.confidence DESC
    """
    themes = await conn.fetch(theme_query, stock_id)

    print(f"找到 {len(themes)} 个主题:")
    for i, row in enumerate(themes, 1):
        print(f"  {i}. {row['theme_name']} (主题键: {row['subject_key']})")

    print()

    # 2. 检查每个主题的主线判断数据
    print("📊 主题主线判断数据:")
    for row in themes:
        subject_key = row['subject_key']
        theme_name = row['theme_name']

        # 检查theme_mainline_judgement表
        mainline_query = """
        SELECT
            is_main_theme, theme_tier,
            event_chain_score, event_chain_continuity_score,
            market_recognition_score, mainline_stability_score,
            limit_up_count, conclusion
        FROM theme_mainline_judgement
        WHERE trade_date = $1 AND subject_key = $2
        """

        mainline_result = await conn.fetchrow(mainline_query, analysis_date, subject_key)

        if mainline_result:
            print(f"  🎯 {theme_name}:")
            print(f"     主线主题: {mainline_result['is_main_theme']}")
            print(f"     主题层级: {mainline_result['theme_tier']}")
            print(f"     事件链分数: {mainline_result['event_chain_score']:.1f}")
            print(f"     事件连续性分数: {mainline_result['event_chain_continuity_score']:.1f}")
            print(f"     市场认可分数: {mainline_result['market_recognition_score']:.1f}")
            print(f"     主线稳定性分数: {mainline_result['mainline_stability_score']:.1f}")
            print(f"     涨停数量: {mainline_result['limit_up_count']}")
            print(f"     结论: {mainline_result['conclusion']}")
        else:
            print(f"  ❌ {theme_name}: 无主线判断数据")

    # 3. 检查事件统计数据（如果有相关表）
    print()
    print("📰 检查事件统计（如果有）:")
    # 假设有事件统计表，实际需要根据数据库结构调整

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_mainline())