#!/usr/bin/env python3
"""
将 theme_data_complete/lists/full_theme_list.jsonl 导入 subject_node_staging。

用途：
- 固定 subject_key 题材节点主档
- 为 phase1 的 rank/history/tree 提供统一节点元数据
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


LIST_SYNC_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
LIST_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.jsonl"


def resolve_list_file() -> Path:
    if LIST_SYNC_FILE.exists():
        return LIST_SYNC_FILE
    return LIST_FILE


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_node_staging (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        subject_name VARCHAR(150) NOT NULL,
        node_level INTEGER,
        parent_subject_key VARCHAR(80),
        ancestors TEXT,
        reason TEXT,
        first_letter VARCHAR(32),
        importance INTEGER,
        sort INTEGER,
        pct_chg NUMERIC(8,4),
        status VARCHAR(20),
        source_type VARCHAR(50) DEFAULT 'jyhf_full_theme_list',
        raw_json JSONB,
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_node_staging UNIQUE (subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_sns_parent ON subject_node_staging(parent_subject_key);
    CREATE INDEX IF NOT EXISTS idx_sns_level ON subject_node_staging(node_level);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


def _to_int(value):
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


async def load_rows(manager: PostgresDatabaseManager, batch_id: str) -> int:
    rows = []
    subject_keys = []
    skipped = 0
    list_file = resolve_list_file()

    with list_file.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            level = obj.get("level")
            if level is None:
                # tolerate malformed key in source like "låevel"
                level = obj.get("låevel")
            subject_id = obj.get("subjectId")
            if subject_id in (None, ""):
                skipped += 1
                continue
            subject_key = str(subject_id)
            subject_keys.append(subject_key)
            parent_id = obj.get("parentId")
            parent_subject_key = None if parent_id in (None, "", 0, "0") else str(parent_id)
            rows.append(
                (
                    subject_key,
                    obj.get("name") or str(subject_id),
                    _to_int(level),
                    parent_subject_key,
                    obj.get("ancestors"),
                    obj.get("reason"),
                    obj.get("firstLetter"),
                    _to_int(obj.get("importance")),
                    _to_int(obj.get("sort")),
                    _to_float(obj.get("pctChg")),
                    str(obj.get("status")) if obj.get("status") is not None else None,
                    "jyhf_full_theme_list",
                    json.dumps(obj, ensure_ascii=False),
                    batch_id,
                )
            )

    sql = """
    INSERT INTO subject_node_staging (
        subject_key, subject_name, node_level, parent_subject_key, ancestors,
        reason, first_letter, importance, sort, pct_chg, status,
        source_type, raw_json, ingest_batch_id
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9, $10, $11,
        $12, $13, $14
    )
    ON CONFLICT (subject_key)
    DO UPDATE SET
        subject_name = EXCLUDED.subject_name,
        node_level = EXCLUDED.node_level,
        parent_subject_key = EXCLUDED.parent_subject_key,
        ancestors = EXCLUDED.ancestors,
        reason = EXCLUDED.reason,
        first_letter = EXCLUDED.first_letter,
        importance = EXCLUDED.importance,
        sort = EXCLUDED.sort,
        pct_chg = EXCLUDED.pct_chg,
        status = EXCLUDED.status,
        source_type = EXCLUDED.source_type,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """

    if rows:
        async with manager.pool.acquire() as conn:
            await conn.executemany(sql, rows)
            await conn.execute(
                """
                DELETE FROM subject_node_staging
                WHERE source_type = 'jyhf_full_theme_list'
                  AND NOT (subject_key = ANY($1::varchar[]))
                """,
                subject_keys,
            )

    if skipped:
        print(f"[WARN] skipped subject_node rows={skipped}")
    return len(rows)


async def main() -> int:
    list_file = resolve_list_file()
    if not list_file.exists():
        print(f"[ERROR] list file not found: {list_file}")
        return 1

    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_subject_node")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, batch_id)
        print(f"[OK] loaded subject_node_staging rows={count} batch_id={batch_id} source={list_file.name}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
