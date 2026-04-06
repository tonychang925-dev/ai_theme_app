#!/usr/bin/env python3
"""
执行 P2.phase1 的最小数据库对象：
- theme_hierarchy_staging
- 6 个 phase1 视图
"""

import asyncio
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


async def main() -> int:
    sql_path = PROJECT_ROOT / "database_service" / "create_phase1_views.sql"
    if not sql_path.exists():
        print(f"[ERROR] sql file not found: {sql_path}")
        return 1

    sql = sql_path.read_text(encoding="utf-8")
    drop_sql = """
    DROP VIEW IF EXISTS vw_theme_history_candidate CASCADE;
    DROP VIEW IF EXISTS vw_theme_tree_candidate CASCADE;
    DROP VIEW IF EXISTS vw_theme_stock_map_candidate CASCADE;
    DROP VIEW IF EXISTS vw_theme_detail_joined CASCADE;
    DROP VIEW IF EXISTS vw_theme_rank_current CASCADE;
    DROP VIEW IF EXISTS vw_subject_theme_binding CASCADE;
    """
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            await conn.execute(drop_sql)
            await conn.execute(sql)
        print("[OK] applied phase1 views and staging table")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
