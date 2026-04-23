#!/usr/bin/env python3
"""检查神剑股份主题的主线判断数据（统一口径：v2，LEGACY，建议改用 analyze_stock_w2s.py）。"""

import asyncio
import asyncpg
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_service.config import StockServiceConfig

async def check_mainline():
    print("[LEGACY] 建议改用: .venv/bin/python scripts/analyze_stock_w2s.py --stock-code 002361 --trade-date 2026-04-07")
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

    # 1. 获取主题映射（本地快照映射）
    theme_query = """
    SELECT DISTINCT
        s.subject_key,
        COALESCE(NULLIF(vw.theme_name, ''), s.subject_key) AS theme_name
    FROM subject_stock_daily_snapshot s
    LEFT JOIN vw_subject_theme_binding vw
      ON vw.subject_key = s.subject_key
    WHERE s.trade_date = $1
      AND split_part(s.stock_id, '.', 1) = $2
    ORDER BY s.subject_key
    """
    themes = await conn.fetch(theme_query, analysis_date, stock_id)

    print(f"找到 {len(themes)} 个主题:")
    for i, row in enumerate(themes, 1):
        print(f"  {i}. {row['theme_name']} (主题键: {row['subject_key']})")

    print()

    # 2. 检查每个主题的主线判断数据（v2 + evidence）
    print("📊 主题主线判断数据:")
    for row in themes:
        subject_key = row['subject_key']
        theme_name = row['theme_name']

        mainline_query = """
        SELECT
            COALESCE(v2.final_mainline_alive, FALSE) AS mainline_alive,
            COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
            COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
            COALESCE(v2.confidence_score, 0) AS confidence_score,
            COALESCE(v2.fade_risk_score, 0) AS fade_risk_score,
            COALESCE(e.event_count_3d, 0) AS event_count_3d,
            COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
            COALESCE(e.limit_up_count, 0) AS limit_up_count
        FROM theme_cycle_judgement_v2 v2
        LEFT JOIN theme_cycle_evidence_daily e
          ON e.trade_date = v2.trade_date
         AND e.subject_key = v2.subject_key
        WHERE v2.trade_date = $1 AND v2.subject_key = $2
        """

        mainline_result = await conn.fetchrow(mainline_query, analysis_date, subject_key)

        if mainline_result:
            print(f"  🎯 {theme_name}:")
            print(f"     主线存活: {mainline_result['mainline_alive']}")
            print(f"     周期状态: {mainline_result['final_cycle_state']}")
            print(f"     事件计数(3d): {mainline_result['event_count_3d']}")
            print(f"     事件连续性分数: {mainline_result['event_continuity_score']:.1f}")
            print(f"     置信度分数: {mainline_result['confidence_score']:.1f}")
            print(f"     主线强度分数: {mainline_result['mainline_strength_score']:.1f}")
            print(f"     退潮风险分数: {mainline_result['fade_risk_score']:.1f}")
            print(f"     涨停数量: {mainline_result['limit_up_count']}")
        else:
            print(f"  ❌ {theme_name}: 无主线判断数据")

    # 3. 检查事件统计数据（如果有相关表）
    print()
    print("📰 检查事件统计（如果有）:")
    # 假设有事件统计表，实际需要根据数据库结构调整

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_mainline())
