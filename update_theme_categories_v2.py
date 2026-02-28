#!/usr/bin/env python3
"""
更新 theme_master 中的分类编码（category1_code/category2_code）
基于 tags 中的 full_name 字段解析 L1/L2 名称，匹配 financial_categories
修复 tags 字符串解析问题
"""

import os
import sys
import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_postgres_config():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    database = os.getenv("POSTGRES_DATABASE", "stock_data_test")
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=host,
        postgres_port=port,
        postgres_database=database,
        postgres_username=user,
        postgres_password=password,
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5
    )

async def build_name_to_code_mapping(conn) -> Dict[str, str]:
    """从 financial_categories 构建名称到 category_code 的映射（L1/L2）"""
    rows = await conn.fetch("""
        SELECT category_code, category_name, category_level
        FROM financial_categories
        WHERE category_level IN (1,2)
    """)
    mapping = {}
    for r in rows:
        name = r['category_name'].strip()
        code = r['category_code']
        mapping[name] = code
    logger.info(f"加载 {len(mapping)} 个名称映射")
    # 打印前几个映射供检查
    sample = list(mapping.items())[:5]
    logger.info(f"示例映射: {sample}")
    return mapping

async def update_theme_categories(conn, name_to_code: Dict[str, str]):
    """更新 theme_master 中的分类编码"""
    themes = await conn.fetch("""
        SELECT code, tags
        FROM theme_master
        WHERE source_system = 'jyhf'
          AND (category1_code IS NULL OR category2_code IS NULL)
    """)
    logger.info(f"待更新题材数: {len(themes)}")

    updated = 0
    matched_l1 = 0
    matched_l2 = 0

    for theme in themes:
        code = theme['code']
        tags_str = theme['tags']
        # 解析 tags（可能是字符串或字典）
        if tags_str:
            if isinstance(tags_str, str):
                try:
                    tags = json.loads(tags_str)
                except json.JSONDecodeError:
                    logger.warning(f"题材 {code} 的 tags 解析失败: {tags_str}")
                    continue
            else:
                tags = tags_str
        else:
            tags = {}

        full_name = tags.get('full_name')
        if not full_name:
            logger.debug(f"题材 {code} 无 full_name 信息，跳过")
            continue

        # 拆分 full_name
        parts = full_name.split('-')
        # 清洗名称
        l1_name = parts[0].strip() if len(parts) >= 1 else None
        l2_name = parts[1].strip() if len(parts) >= 2 else None

        cat1_code = name_to_code.get(l1_name) if l1_name else None
        cat2_code = name_to_code.get(l2_name) if l2_name else None

        if cat1_code:
            matched_l1 += 1
        if cat2_code:
            matched_l2 += 1

        if cat1_code is not None or cat2_code is not None:
            await conn.execute("""
                UPDATE theme_master
                SET category1_code = COALESCE($1, category1_code),
                    category2_code = COALESCE($2, category2_code)
                WHERE code = $3
            """, cat1_code, cat2_code, code)
            updated += 1
        else:
            logger.info(f"题材 {code} 未能匹配: l1_name='{l1_name}', l2_name='{l2_name}'")

    logger.info(f"L1 匹配次数: {matched_l1}, L2 匹配次数: {matched_l2}, 更新题材数: {updated}")

async def main():
    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            name_to_code = await build_name_to_code_mapping(conn)
            await update_theme_categories(conn, name_to_code)
    finally:
        await manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())