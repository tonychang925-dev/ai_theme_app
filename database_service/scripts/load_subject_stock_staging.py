#!/usr/bin/env python3
"""
将 subject_stock_map 规范化导入 subject_stock_staging。
用于 phase1 视图整合和后续 theme_stock_map serving 回填。
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


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_stock_staging (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        relation_type_candidate VARCHAR(20),
        top BOOLEAN DEFAULT FALSE,
        sort INTEGER,
        reason TEXT,
        remark TEXT,
        confidence NUMERIC(4,2),
        source_type VARCHAR(50) DEFAULT 'jyhf_stock_map',
        evidence_json JSONB,
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_stock_staging UNIQUE (subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_sss_subject ON subject_stock_staging(subject_key);
    CREATE INDEX IF NOT EXISTS idx_sss_stock ON subject_stock_staging(stock_id);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def load_rows(manager: PostgresDatabaseManager, batch_id: str) -> int:
    sql = """
    INSERT INTO subject_stock_staging (
        subject_key, stock_id, stock_name, relation_type_candidate,
        top, sort, reason, remark, confidence, source_type, evidence_json, ingest_batch_id
    )
    SELECT
        ssm.subject_key,
        ssm.stock_id,
        COALESCE(ssm.name, s.name) AS stock_name,
        CASE
            WHEN ssm.top = TRUE THEN 'leader'
            WHEN COALESCE(ssm.sort, 9999) <= 3 THEN 'core'
            ELSE 'member'
        END AS relation_type_candidate,
        ssm.top,
        ssm.sort,
        ssm.reason,
        ssm.remark,
        ssm.confidence,
        COALESCE(ssm.source_type, 'jyhf_stock_map') AS source_type,
        ssm.evidence_json,
        $1
    FROM subject_stock_map ssm
    LEFT JOIN stocks s
      ON s.stock_id = ssm.stock_id
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        relation_type_candidate = EXCLUDED.relation_type_candidate,
        top = EXCLUDED.top,
        sort = EXCLUDED.sort,
        reason = EXCLUDED.reason,
        remark = EXCLUDED.remark,
        confidence = EXCLUDED.confidence,
        source_type = EXCLUDED.source_type,
        evidence_json = EXCLUDED.evidence_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        result = await conn.execute(sql, batch_id)
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def main() -> int:
    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_subject_stock")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, batch_id)
        print(f"[OK] loaded subject_stock_staging rows={count} batch_id={batch_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
