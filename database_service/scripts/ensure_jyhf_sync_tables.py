#!/usr/bin/env python3
"""
创建久赢恒丰增量同步状态表。

目标：
- 记录批次级状态
- 记录文件级 manifest
- 记录 subject 级最后同步状态
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


DDL = """
CREATE TABLE IF NOT EXISTS jyhf_sync_batch (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(64) NOT NULL UNIQUE,
    sync_scope VARCHAR(32) DEFAULT 'incremental',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    subject_count INTEGER DEFAULT 0,
    changed_subject_count INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    changed_file_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    manifest_path TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jyhf_sync_file_manifest (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(64) NOT NULL,
    file_path TEXT NOT NULL,
    data_type VARCHAR(32) NOT NULL,
    subject_key VARCHAR(80),
    file_hash VARCHAR(128),
    file_size BIGINT,
    source_updated_at TIMESTAMP,
    sync_status VARCHAR(20) DEFAULT 'pending',
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_jyhf_sync_file UNIQUE (batch_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_jyhf_sync_file_batch
ON jyhf_sync_file_manifest(batch_id);

CREATE INDEX IF NOT EXISTS idx_jyhf_sync_file_subject
ON jyhf_sync_file_manifest(subject_key);

CREATE INDEX IF NOT EXISTS idx_jyhf_sync_file_type
ON jyhf_sync_file_manifest(data_type);

CREATE TABLE IF NOT EXISTS jyhf_sync_subject_state (
    id BIGSERIAL PRIMARY KEY,
    subject_key VARCHAR(80) NOT NULL UNIQUE,
    last_batch_id VARCHAR(64),
    last_success_at TIMESTAMP,
    last_file_hash VARCHAR(128),
    last_data_types JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(20) DEFAULT 'pending',
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jyhf_sync_subject_status
ON jyhf_sync_subject_state(status);
"""


async def main() -> int:
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            await conn.execute(DDL)
        print("[OK] ensured jyhf sync tables")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
