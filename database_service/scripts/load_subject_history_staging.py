#!/usr/bin/env python3
"""
导入 theme_data_complete/history 下的久赢历史真源到 subject_history_staging。
"""

import asyncio
import json
import os
import sys
from datetime import date, datetime
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


HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_history_staging (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        subject_rank_id BIGINT,
        rank_date DATE,
        subject_name VARCHAR(150),
        description TEXT,
        heat INTEGER,
        heat_name VARCHAR(50),
        pct_chg NUMERIC(8,4),
        his_pct_chg NUMERIC(8,4),
        red BOOLEAN DEFAULT FALSE,
        sort INTEGER,
        source_type VARCHAR(50) DEFAULT 'jyhf_history',
        raw_json JSONB,
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_history_rank UNIQUE (subject_key, subject_rank_id)
    );
    CREATE INDEX IF NOT EXISTS idx_shs_subject_date ON subject_history_staging(subject_key, rank_date DESC);
    CREATE INDEX IF NOT EXISTS idx_shs_rank_id ON subject_history_staging(subject_rank_id);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


def _to_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


async def load_rows(manager: PostgresDatabaseManager, batch_id: str) -> int:
    sql = """
    INSERT INTO subject_history_staging (
        subject_key, subject_rank_id, rank_date, subject_name, description,
        heat, heat_name, pct_chg, his_pct_chg, red, sort,
        source_type, raw_json, ingest_batch_id
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9, $10, $11,
        $12, $13, $14
    )
    ON CONFLICT (subject_key, subject_rank_id)
    DO UPDATE SET
        rank_date = EXCLUDED.rank_date,
        subject_name = EXCLUDED.subject_name,
        description = EXCLUDED.description,
        heat = EXCLUDED.heat,
        heat_name = EXCLUDED.heat_name,
        pct_chg = EXCLUDED.pct_chg,
        his_pct_chg = EXCLUDED.his_pct_chg,
        red = EXCLUDED.red,
        sort = EXCLUDED.sort,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """

    rows = []
    invalid_files = 0
    invalid_lines = 0

    for path in sorted(HISTORY_DIR.glob("*_history.jsonl")):
        # Skip editor temp files like .~59919_history.jsonl.
        if path.name.startswith("."):
            invalid_files += 1
            continue

        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    invalid_lines += 1
                    print(f"[WARN] skip invalid history line: file={path.name} line={line_no}")
                    continue
                subject_key = str(obj.get("subjectId") or path.stem.replace("_history", ""))
                rows.append(
                    (
                        subject_key,
                        _to_int(obj.get("subjectRankId")),
                        _to_date(obj.get("rankDate")),
                        obj.get("subjectName"),
                        obj.get("description"),
                        _to_int(obj.get("heat")),
                        obj.get("heatName"),
                        _to_float(obj.get("pctChg")),
                        _to_float(obj.get("hisPctChg")),
                        bool(obj.get("red")),
                        _to_int(obj.get("sort")),
                        "jyhf_history",
                        json.dumps(obj, ensure_ascii=False),
                        batch_id,
                    )
                )

    if invalid_files:
        print(f"[WARN] skipped invalid history files={invalid_files}")
    if invalid_lines:
        print(f"[WARN] skipped invalid history lines={invalid_lines}")

    if not rows:
        return 0

    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, rows)
    return len(rows)


async def main() -> int:
    if not HISTORY_DIR.exists():
        print(f"[ERROR] history dir not found: {HISTORY_DIR}")
        return 1

    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_subject_history")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, batch_id)
        print(f"[OK] loaded subject_history_staging rows={count} batch_id={batch_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
