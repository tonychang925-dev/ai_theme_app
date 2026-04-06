#!/usr/bin/env python3
"""
将 theme_data_complete/children/*.jsonl 导入 subject_children_staging。

用途：
- 固化 children 富关系快照
- 为 phase1 tree / children API 提供结构化补充真源
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


CHILDREN_DIR = PROJECT_ROOT / "theme_data_complete" / "children"


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_children_staging (
        id BIGSERIAL PRIMARY KEY,
        parent_subject_key VARCHAR(80),
        child_subject_key VARCHAR(80) NOT NULL,
        child_name VARCHAR(150),
        full_name TEXT,
        pct_chg NUMERIC(8,4),
        stock_count INTEGER,
        limit_up_count INTEGER,
        sort INTEGER,
        red BOOLEAN,
        amount NUMERIC(20,2),
        market_value NUMERIC(20,2),
        lead_stock_id VARCHAR(20),
        lead_stock_name VARCHAR(100),
        ancestors TEXT,
        depth INTEGER DEFAULT 0,
        source_type VARCHAR(50) DEFAULT 'jyhf_children',
        raw_json JSONB,
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_children_staging UNIQUE (parent_subject_key, child_subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_scs_parent ON subject_children_staging(parent_subject_key);
    CREATE INDEX IF NOT EXISTS idx_scs_child ON subject_children_staging(child_subject_key);
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


def _to_bool(value):
    if value in (None, "", "null"):
        return None
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except Exception:
        return bool(value)


def _walk_node(node, parent_subject_key, depth, rows, batch_id):
    if not isinstance(node, list) or len(node) < 14:
        return

    child_subject_key = str(node[0])
    child_name = node[1]
    full_name = node[2]
    pct_chg = _to_float(node[3])
    stock_count = _to_int(node[4])
    limit_up_count = _to_int(node[5])
    sort = _to_int(node[6])
    red = _to_bool(node[7])
    amount = _to_float(node[9])
    market_value = _to_float(node[10])
    lead_stock_id = node[11]
    lead_stock_name = node[12]
    ancestors = node[13]
    children = node[14] if len(node) > 14 and isinstance(node[14], list) else []

    rows.append(
        (
            parent_subject_key,
            child_subject_key,
            child_name,
            full_name,
            pct_chg,
            stock_count,
            limit_up_count,
            sort,
            red,
            amount,
            market_value,
            lead_stock_id,
            lead_stock_name,
            ancestors,
            depth,
            "jyhf_children",
            json.dumps(node, ensure_ascii=False),
            batch_id,
        )
    )

    for child in children:
        _walk_node(child, child_subject_key, depth + 1, rows, batch_id)


async def load_rows(manager: PostgresDatabaseManager, batch_id: str) -> int:
    rows = []

    for path in sorted(CHILDREN_DIR.glob("*_children.jsonl")):
        parent_subject_key = path.stem.replace("_children", "")
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                _walk_node(obj, parent_subject_key, 1, rows, batch_id)

    if not rows:
        return 0

    sql = """
    INSERT INTO subject_children_staging (
        parent_subject_key, child_subject_key, child_name, full_name,
        pct_chg, stock_count, limit_up_count, sort, red,
        amount, market_value, lead_stock_id, lead_stock_name,
        ancestors, depth, source_type, raw_json, ingest_batch_id
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7, $8, $9,
        $10, $11, $12, $13,
        $14, $15, $16, $17, $18
    )
    ON CONFLICT (parent_subject_key, child_subject_key)
    DO UPDATE SET
        child_name = EXCLUDED.child_name,
        full_name = EXCLUDED.full_name,
        pct_chg = EXCLUDED.pct_chg,
        stock_count = EXCLUDED.stock_count,
        limit_up_count = EXCLUDED.limit_up_count,
        sort = EXCLUDED.sort,
        red = EXCLUDED.red,
        amount = EXCLUDED.amount,
        market_value = EXCLUDED.market_value,
        lead_stock_id = EXCLUDED.lead_stock_id,
        lead_stock_name = EXCLUDED.lead_stock_name,
        ancestors = EXCLUDED.ancestors,
        depth = EXCLUDED.depth,
        source_type = EXCLUDED.source_type,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, rows)
    return len(rows)


async def main() -> int:
    if not CHILDREN_DIR.exists():
        print(f"[ERROR] children dir not found: {CHILDREN_DIR}")
        return 1

    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_subject_children")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, batch_id)
        print(f"[OK] loaded subject_children_staging rows={count} batch_id={batch_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
