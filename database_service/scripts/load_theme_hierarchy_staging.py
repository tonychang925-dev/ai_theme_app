#!/usr/bin/env python3
"""
将 theme_data_complete/lists/theme_hierarchy.jsonl 导入 theme_hierarchy_staging。

用途：
- 作为 P2.phase1 视图整合层的最小可执行入口
- 为 vw_theme_tree_candidate 提供标准 parent-child 真源
"""

import asyncio
import json
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


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_hierarchy_staging (
        id BIGSERIAL PRIMARY KEY,
        parent_subject_key VARCHAR(80) NOT NULL,
        child_subject_key VARCHAR(80) NOT NULL,
        child_name VARCHAR(150),
        source_type VARCHAR(50) DEFAULT 'jyhf_hierarchy',
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_hierarchy_staging UNIQUE (parent_subject_key, child_subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_ths_parent ON theme_hierarchy_staging(parent_subject_key);
    CREATE INDEX IF NOT EXISTS idx_ths_child ON theme_hierarchy_staging(child_subject_key);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def load_rows(manager: PostgresDatabaseManager, path: Path, batch_id: str) -> int:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            parent_subject_key = str(obj["parent_id"])
            child_subject_key = str(obj["child_id"])
            child_name = obj.get("child_name")
            rows.append((parent_subject_key, child_subject_key, child_name, "jyhf_hierarchy", batch_id))

    if not rows:
        return 0

    sql = """
    INSERT INTO theme_hierarchy_staging (
        parent_subject_key, child_subject_key, child_name, source_type, ingest_batch_id
    ) VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (parent_subject_key, child_subject_key)
    DO UPDATE SET
        child_name = EXCLUDED.child_name,
        source_type = EXCLUDED.source_type,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, rows)
    return len(rows)


async def main() -> int:
    hierarchy_file = PROJECT_ROOT / "theme_data_complete" / "lists" / "theme_hierarchy.jsonl"
    if not hierarchy_file.exists():
        print(f"[ERROR] hierarchy file not found: {hierarchy_file}")
        return 1

    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_theme_hierarchy")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, hierarchy_file, batch_id)
        print(f"[OK] loaded theme_hierarchy_staging rows={count} batch_id={batch_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
