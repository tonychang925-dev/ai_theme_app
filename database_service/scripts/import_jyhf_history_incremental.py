#!/usr/bin/env python3
"""
按 subject_key 增量/精确同步久赢 history 到数据库。

处理链：
- theme_data_complete/history/*_history.jsonl -> subject_history_staging
- theme_data_complete/history/*_history.jsonl -> subject_rank_daily
- 刷新对应 subject_key 的 theme_history_event
- 为久赢 history 事件补写 synthetic news_event / event_theme_map
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.scripts.materialize_phase1_serving import ensure_tables as ensure_serving_tables

HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"


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


def parse_args():
    parser = argparse.ArgumentParser(description="增量同步久赢 history -> subject_history_staging / subject_rank_daily / theme_history_event")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则处理全部 history 文件")
    parser.add_argument("--batch-id", default=None, help="同步批次 ID")
    parser.add_argument(
        "--mode",
        choices=("full_refresh", "append"),
        default="full_refresh",
        help="full_refresh=按题材删除后重建；append=仅 upsert 新增/变更记录",
    )
    return parser.parse_args()


def _load_subject_keys(subjects_file: Optional[str]) -> Optional[List[str]]:
    if not subjects_file:
        return None
    content = Path(subjects_file).read_text(encoding="utf-8").strip()
    if not content:
        return []
    if subjects_file.endswith(".json"):
        return [str(x) for x in json.loads(content)]
    return [line.strip() for line in content.splitlines() if line.strip()]


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


def _to_date(value):
    if value in (None, "", "null"):
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
            return datetime.strptime(text.split("Z")[0], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
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

    CREATE TABLE IF NOT EXISTS subject_rank_daily (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        rank_date DATE NOT NULL,
        heat INTEGER,
        heat_name VARCHAR(50),
        pct_chg NUMERIC(8,4),
        his_pct_chg NUMERIC(8,4),
        red BOOLEAN DEFAULT FALSE,
        description TEXT,
        source_system VARCHAR(50) DEFAULT 'jyhf',
        theme_id INTEGER,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_rank UNIQUE (subject_key, rank_date)
    );
    CREATE INDEX IF NOT EXISTS idx_subject_rank_daily_date ON subject_rank_daily(rank_date DESC);
    CREATE INDEX IF NOT EXISTS idx_subject_rank_daily_subject ON subject_rank_daily(subject_key, rank_date DESC);
    CREATE INDEX IF NOT EXISTS idx_subject_rank_daily_theme_id ON subject_rank_daily(theme_id, rank_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
    await ensure_serving_tables(manager)


async def ensure_event_theme_columns(manager: PostgresDatabaseManager) -> None:
    ddl = """
    ALTER TABLE news_event
      ADD COLUMN IF NOT EXISTS theme_directive JSONB DEFAULT '{}'::jsonb;
    ALTER TABLE news_event
      ADD COLUMN IF NOT EXISTS theme_directive_processed BOOLEAN DEFAULT FALSE;
    ALTER TABLE news_event
      ADD COLUMN IF NOT EXISTS event_time TIMESTAMP;
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def ensure_jyhf_theme_master_rows(manager: PostgresDatabaseManager, subject_keys: Sequence[str]) -> None:
    sql = """
    WITH candidates AS (
        SELECT DISTINCT
            sns.subject_key,
            COALESCE(NULLIF(sns.subject_name, ''), sns.subject_key) AS subject_name
        FROM subject_node_staging sns
        WHERE sns.subject_key = ANY($1::varchar[])
    )
    INSERT INTO theme_master (
        name,
        code,
        description,
        status,
        theme_type,
        heat_score,
        confidence_score,
        source_system,
        source_id,
        created_by,
        created_at,
        updated_at,
        last_active_at
    )
    SELECT
        c.subject_name,
        ('JYHF_' || c.subject_key),
        ('久赢题材自动补建:' || c.subject_name),
        'active',
        'concept',
        50,
        1.0,
        'jyhf',
        c.subject_key,
        'jyhf_history_import',
        NOW(),
        NOW(),
        NOW()
    FROM candidates c
    WHERE NOT EXISTS (
        SELECT 1
        FROM theme_master tm
        WHERE tm.source_system = 'jyhf'
          AND tm.source_id = c.subject_key
    )
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql, list(subject_keys))


def iter_history_files(subject_keys: Optional[Sequence[str]]) -> Iterable[Path]:
    if subject_keys is None:
        yield from sorted(HISTORY_DIR.glob("*_history.jsonl"))
        return
    for subject_key in subject_keys:
        path = HISTORY_DIR / f"{subject_key}_history.jsonl"
        if path.exists():
            yield path


def extract_rows(path: Path, batch_id: str) -> Tuple[List[Tuple], List[Tuple]]:
    history_rows: List[Tuple] = []
    rank_rows: List[Tuple] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARN] skip invalid history line: file={path.name} line={line_no}")
                continue

            rows = obj.get("rows") if isinstance(obj, dict) and "rows" in obj else obj
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue

            for row in rows:
                subject_key = str(row.get("subjectId") or path.stem.replace("_history", ""))
                rank_date = _to_date(row.get("rankDate"))
                if not subject_key or rank_date is None:
                    continue
                subject_rank_id = _to_int(row.get("subjectRankId"))
                subject_name = row.get("subjectName")
                description = row.get("description")
                heat = _to_int(row.get("heat"))
                heat_name = row.get("heatName")
                pct_chg = _to_float(row.get("pctChg"))
                his_pct_chg = _to_float(row.get("hisPctChg"))
                red = bool(row.get("red"))
                sort = _to_int(row.get("sort"))

                history_rows.append(
                    (
                        subject_key,
                        subject_rank_id,
                        rank_date,
                        subject_name,
                        description,
                        heat,
                        heat_name,
                        pct_chg,
                        his_pct_chg,
                        red,
                        sort,
                        "jyhf_history",
                        json.dumps(row, ensure_ascii=False),
                        batch_id,
                    )
                )
                rank_rows.append(
                    (
                        subject_key,
                        rank_date,
                        heat,
                        heat_name,
                        pct_chg,
                        his_pct_chg,
                        red,
                        description,
                        "jyhf",
                    )
                )
    return history_rows, rank_rows


async def sync_subjects(manager: PostgresDatabaseManager, subject_keys: Sequence[str], batch_id: str, mode: str) -> Tuple[int, int]:
    history_rows: List[Tuple] = []
    rank_rows: List[Tuple] = []

    for path in iter_history_files(subject_keys):
        h_rows, r_rows = extract_rows(path, batch_id)
        history_rows.extend(h_rows)
        rank_rows.extend(r_rows)

    history_sql = """
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
        source_type = EXCLUDED.source_type,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    rank_sql = """
    INSERT INTO subject_rank_daily (
        subject_key, rank_date, heat, heat_name, pct_chg, his_pct_chg,
        red, description, source_system, created_at, updated_at
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, NOW(), NOW()
    )
    ON CONFLICT (subject_key, rank_date)
    DO UPDATE SET
        heat = EXCLUDED.heat,
        heat_name = EXCLUDED.heat_name,
        pct_chg = EXCLUDED.pct_chg,
        his_pct_chg = EXCLUDED.his_pct_chg,
        red = EXCLUDED.red,
        description = EXCLUDED.description,
        source_system = EXCLUDED.source_system,
        updated_at = NOW()
    """
    refresh_sql = """
    INSERT INTO theme_history_event (
        subject_key, theme_id, theme_name, subject_rank_id, event_id,
        rank_date, driver_summary, description, heat, heat_name, pct_chg, his_pct_chg,
        source_type, source_ref, trace_id, evidence_json, effective_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        subject_rank_id,
        event_id,
        rank_date,
        LEFT(COALESCE(description, ''), 500) AS driver_summary,
        description,
        heat,
        heat_name,
        pct_chg,
        his_pct_chg,
        source_type,
        source_ref,
        NULL::VARCHAR(120),
        jsonb_build_object(
            'source_type', source_type,
            'source_ref', source_ref,
            'event_id', event_id,
            'subject_rank_id', subject_rank_id
        ),
        COALESCE(rank_date::timestamp, NOW())
    FROM vw_theme_history_candidate
    WHERE source_ref IS NOT NULL
      AND subject_key = ANY($1::varchar[])
      AND source_type IN ('jyhf_history', 'jyhf_rank_daily')
    ON CONFLICT (subject_key, source_type, source_ref)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        subject_rank_id = EXCLUDED.subject_rank_id,
        event_id = EXCLUDED.event_id,
        rank_date = EXCLUDED.rank_date,
        driver_summary = EXCLUDED.driver_summary,
        description = EXCLUDED.description,
        heat = EXCLUDED.heat,
        heat_name = EXCLUDED.heat_name,
        pct_chg = EXCLUDED.pct_chg,
        his_pct_chg = EXCLUDED.his_pct_chg,
        trace_id = EXCLUDED.trace_id,
        evidence_json = EXCLUDED.evidence_json,
        effective_at = EXCLUDED.effective_at,
        updated_at = NOW()
    """

    history_event_news_sql = """
    WITH candidates AS (
        SELECT
            h.subject_key,
            tm.id AS theme_id,
            COALESCE(tm.name, h.subject_name, h.subject_key) AS theme_name,
            h.rank_date,
            h.description,
            h.source_type,
            COALESCE(h.subject_rank_id::text, h.id::text) AS source_ref,
            COALESCE(
                NULLIF(h.raw_json->>'createTime', '')::timestamp,
                NULLIF(h.raw_json->>'updateTime', '')::timestamp,
                h.rank_date::timestamp
            ) AS event_ts,
            jsonb_build_object(
                'jyhf_subject_key', h.subject_key,
                'jyhf_source_type', h.source_type,
                'jyhf_source_ref', COALESCE(h.subject_rank_id::text, h.id::text),
                'jyhf_batch_id', $2::text
            ) AS marker
        FROM subject_history_staging h
        LEFT JOIN theme_master tm
          ON tm.source_system = 'jyhf'
         AND tm.source_id = h.subject_key
        WHERE h.subject_key = ANY($1::varchar[])
          AND h.source_type = 'jyhf_history'
          AND tm.id IS NOT NULL
          AND COALESCE(h.subject_rank_id::text, h.id::text) IS NOT NULL
          AND COALESCE(NULLIF(h.description, ''), '') <> ''
    )
    INSERT INTO news_event (
        news_id,
        event_type,
        confidence,
        summary,
        created_at,
        event_time,
        theme_directive,
        theme_directive_processed
    )
    SELECT
        NULL::integer,
        'jyhf_history',
        1.0,
        LEFT(c.description, 1000),
        c.event_ts,
        c.event_ts,
        c.marker,
        TRUE
    FROM candidates c
    WHERE NOT EXISTS (
        SELECT 1
        FROM news_event ne
        WHERE ne.theme_directive->>'jyhf_subject_key' = c.subject_key
          AND ne.theme_directive->>'jyhf_source_type' = c.source_type
          AND ne.theme_directive->>'jyhf_source_ref' = c.source_ref
    )
    """

    history_event_news_update_sql = """
    WITH candidates AS (
        SELECT
            h.subject_key,
            h.description,
            h.source_type,
            COALESCE(h.subject_rank_id::text, h.id::text) AS source_ref,
            COALESCE(
                NULLIF(h.raw_json->>'createTime', '')::timestamp,
                NULLIF(h.raw_json->>'updateTime', '')::timestamp,
                h.rank_date::timestamp
            ) AS event_ts
        FROM subject_history_staging h
        WHERE h.subject_key = ANY($1::varchar[])
          AND h.source_type = 'jyhf_history'
          AND COALESCE(NULLIF(h.description, ''), '') <> ''
    )
    UPDATE news_event ne
    SET
        summary = LEFT(c.description, 1000),
        created_at = c.event_ts,
        event_time = c.event_ts
    FROM candidates c
    WHERE ne.theme_directive->>'jyhf_subject_key' = c.subject_key
      AND ne.theme_directive->>'jyhf_source_type' = c.source_type
      AND ne.theme_directive->>'jyhf_source_ref' = c.source_ref
    """

    history_event_map_sql = """
    WITH candidates AS (
        SELECT
            h.subject_key,
            tm.id AS theme_id,
            h.source_type,
            COALESCE(h.subject_rank_id::text, h.id::text) AS source_ref
        FROM subject_history_staging h
        LEFT JOIN theme_master tm
          ON tm.source_system = 'jyhf'
         AND tm.source_id = h.subject_key
        WHERE h.subject_key = ANY($1::varchar[])
          AND h.source_type = 'jyhf_history'
          AND tm.id IS NOT NULL
          AND COALESCE(h.subject_rank_id::text, h.id::text) IS NOT NULL
          AND COALESCE(NULLIF(h.description, ''), '') <> ''
    )
    INSERT INTO event_theme_map (
        event_id,
        theme_id,
        confidence,
        created_at
    )
    SELECT
        ne.id,
        c.theme_id,
        1.0,
        NOW()
    FROM candidates c
    JOIN news_event ne
      ON ne.theme_directive->>'jyhf_subject_key' = c.subject_key
     AND ne.theme_directive->>'jyhf_source_type' = c.source_type
     AND ne.theme_directive->>'jyhf_source_ref' = c.source_ref
    ON CONFLICT (event_id, theme_id)
    DO UPDATE SET confidence = EXCLUDED.confidence
    """

    async with manager.pool.acquire() as conn:
        async with conn.transaction():
            if mode == "full_refresh":
                await conn.execute(
                    """
                    DELETE FROM event_theme_map etm
                    USING news_event ne
                    WHERE etm.event_id = ne.id
                      AND ne.theme_directive->>'jyhf_subject_key' = ANY($1::varchar[])
                      AND ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
                    """,
                    list(subject_keys),
                )
                await conn.execute(
                    """
                    DELETE FROM news_event ne
                    WHERE ne.theme_directive->>'jyhf_subject_key' = ANY($1::varchar[])
                      AND ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
                    """,
                    list(subject_keys),
                )
                await conn.execute(
                    "DELETE FROM theme_history_event WHERE subject_key = ANY($1::varchar[]) AND source_type IN ('jyhf_history','jyhf_rank_daily')",
                    list(subject_keys),
                )
                await conn.execute(
                    "DELETE FROM subject_history_staging WHERE subject_key = ANY($1::varchar[])",
                    list(subject_keys),
                )
                await conn.execute(
                    "DELETE FROM subject_rank_daily WHERE subject_key = ANY($1::varchar[]) AND source_system = 'jyhf'",
                    list(subject_keys),
                )
            if history_rows:
                await conn.executemany(history_sql, history_rows)
            if rank_rows:
                await conn.executemany(rank_sql, rank_rows)
            await conn.execute(refresh_sql, list(subject_keys))
            await conn.execute(history_event_news_sql, list(subject_keys), batch_id)
            await conn.execute(history_event_news_update_sql, list(subject_keys))
            await conn.execute(history_event_map_sql, list(subject_keys))
    return len(history_rows), len(rank_rows)


async def main() -> int:
    if not HISTORY_DIR.exists():
        print(f"[ERROR] history dir not found: {HISTORY_DIR}")
        return 1

    args = parse_args()
    batch_id = args.batch_id or f"jyhf_history_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    subject_keys = _load_subject_keys(args.subjects_file)
    if subject_keys is None:
        subject_keys = sorted({path.stem.replace("_history", "") for path in HISTORY_DIR.glob("*_history.jsonl")})

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        await ensure_event_theme_columns(manager)
        await ensure_jyhf_theme_master_rows(manager, subject_keys)
        history_count, rank_count = await sync_subjects(manager, subject_keys, batch_id, args.mode)
        print(
            f"[OK] synced history incrementally subjects={len(subject_keys)} "
            f"history_rows={history_count} rank_rows={rank_count} batch_id={batch_id} mode={args.mode}"
        )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
