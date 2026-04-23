#!/usr/bin/env python3
"""检查主题链路关键表结构（v2统一口径）。"""

import asyncio
import asyncpg
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.config import StockServiceConfig

async def check_tables():
    config = StockServiceConfig()

    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password
    )

    # 1) 检查有哪些包含theme的表
    table_query = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE '%theme%'
    ORDER BY table_name
    """

    tables = await conn.fetch(table_query)
    print("包含'theme'的表:")
    for row in tables:
        print(f"  {row['table_name']}")

    # 2) 检查 v2 关键表结构
    print("\n检查 v2 关键表结构:")
    key_tables = [
        "subject_stock_daily_snapshot",
        "vw_subject_theme_binding",
        "theme_cycle_evidence_daily",
        "theme_cycle_judgement_v2",
    ]
    for table_name in key_tables:
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = 'public'
                AND table_name = $1
            )
            """,
            table_name,
        )
        print(f"  {table_name}: {'✅ 存在' if exists else '❌ 不存在'}")
        if not exists:
            continue
        cols = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
            ORDER BY ordinal_position
            LIMIT 10
            """,
            table_name,
        )
        for col in cols:
            print(f"    - {col['column_name']}: {col['data_type']}")

    # 3) 检查本地快照映射（神剑股份）
    print("\n检查神剑股份本地映射（subject_stock_daily_snapshot + vw_subject_theme_binding）:")
    stock_ids = ["002361.SZ", "002361", "SZ002361"]
    for stock_id in stock_ids:
        rows = await conn.fetch(
            """
            SELECT DISTINCT
              s.subject_key,
              COALESCE(NULLIF(vw.theme_name, ''), s.subject_key) AS theme_name
            FROM subject_stock_daily_snapshot s
            LEFT JOIN vw_subject_theme_binding vw
              ON vw.subject_key = s.subject_key
            WHERE split_part(s.stock_id, '.', 1) = split_part($1::text, '.', 1)
            ORDER BY s.subject_key
            LIMIT 8
            """,
            stock_id,
        )
        print(f"  股票ID '{stock_id}': {len(rows)} 个主题")
        for row in rows:
            print(f"    - {row['subject_key']}: {row['theme_name']}")

    # 4) 检查 v2 主线状态样本
    print("\nV2 主线状态样本:")
    samples = await conn.fetch(
        """
        SELECT
          trade_date,
          subject_key,
          COALESCE(NULLIF(theme_name, ''), subject_key) AS theme_name,
          final_mainline_alive,
          final_cycle_state,
          mainline_strength_score,
          fade_confirmed
        FROM theme_cycle_judgement_v2
        ORDER BY trade_date DESC, mainline_strength_score DESC
        LIMIT 5
        """
    )
    for row in samples:
        print(
            f"  {row['trade_date']} {row['subject_key']} {row['theme_name']} "
            f"alive={row['final_mainline_alive']} state={row['final_cycle_state']} "
            f"strength={float(row['mainline_strength_score'] or 0):.1f} "
            f"fade_confirmed={row['fade_confirmed']}"
        )

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_tables())
