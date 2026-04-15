#!/usr/bin/env python3
"""检查数据库表结构"""

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

    # 检查有哪些包含theme的表
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

    # 检查theme_stock_map表结构
    print("\n检查theme_stock_map表结构:")
    try:
        desc_query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'theme_stock_map'
        ORDER BY ordinal_position
        """
        columns = await conn.fetch(desc_query)
        for col in columns:
            print(f"  {col['column_name']}: {col['data_type']}")
    except:
        print("  theme_stock_map表不存在或无法查询")

    # 检查神剑股份是否存在任何主题映射
    print("\n检查神剑股份主题映射:")

    # 尝试不同股票ID格式
    stock_ids = ["002361.SZ", "002361", "SZ002361"]

    for stock_id in stock_ids:
        query = f"SELECT COUNT(*) as cnt FROM theme_stock_map WHERE stock_id = '{stock_id}'"
        try:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM theme_stock_map WHERE stock_id = '{stock_id}'")
            print(f"  股票ID '{stock_id}': {count} 条记录")
        except:
            print(f"  股票ID '{stock_id}': 查询失败")

    # 检查主题表样本数据
    print("\n主题表样本数据:")
    sample_query = "SELECT subject_key, theme_name FROM theme_stock_map LIMIT 5"
    try:
        samples = await conn.fetch(sample_query)
        for row in samples:
            print(f"  主题键: {row['subject_key']}, 主题名: {row['theme_name']}")
    except:
        print("  无法获取样本数据")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_tables())