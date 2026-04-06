#!/usr/bin/env python3
"""
按 subject_key 增量/精确同步久赢股票映射链。

处理链：
- theme_data_complete/stock_details/*_stocks.jsonl -> subject_stock_map
- subject_children_staging(lead_stock) -> subject_stock_map
- subject_stock_map -> subject_stock_staging
- vw_theme_stock_map_candidate -> theme_stock_map
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.scripts.load_subject_stock_staging import ensure_table as ensure_stock_staging_table
from database_service.scripts.materialize_phase1_serving import ensure_tables as ensure_serving_tables


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
    parser = argparse.ArgumentParser(description="增量同步久赢 stock -> subject_stock_map/subject_stock_staging/theme_stock_map")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则处理全部")
    parser.add_argument("--batch-id", default=None, help="同步批次 ID")
    parser.add_argument("--data-root", default=str(PROJECT_ROOT / "theme_data_complete"), help="久赢本地数据根目录")
    return parser.parse_args()


def _load_subject_keys(subjects_file: Optional[str]) -> Optional[List[str]]:
    if not subjects_file:
        return None
    content = Path(subjects_file).read_text(encoding="utf-8").strip()
    if not content:
        return []
    if subjects_file.endswith(".json"):
        import json
        return [str(x) for x in json.loads(content)]
    return [line.strip() for line in content.splitlines() if line.strip()]


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_stock_map (
        id BIGSERIAL PRIMARY KEY,
        selected_id BIGINT,
        subject_key VARCHAR(80) NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        name VARCHAR(100),
        pct_chg NUMERIC(8,4),
        sort INTEGER,
        top BOOLEAN DEFAULT FALSE,
        reason TEXT,
        remark TEXT,
        source_type VARCHAR(20) DEFAULT 'jyhf',
        confidence NUMERIC(4,2) DEFAULT 1.0,
        start_date DATE,
        end_date DATE,
        evidence_json JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_stock UNIQUE (subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ssm_selected_id ON subject_stock_map(selected_id);
    CREATE INDEX IF NOT EXISTS idx_ssm_stock ON subject_stock_map(stock_id);
    CREATE INDEX IF NOT EXISTS idx_ssm_subject ON subject_stock_map(subject_key);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
    await ensure_stock_staging_table(manager)
    await ensure_serving_tables(manager)


async def _resolve_subject_keys(manager: PostgresDatabaseManager, subject_keys: Optional[Sequence[str]], data_root: Path) -> List[str]:
    if subject_keys is not None:
        return [str(x) for x in subject_keys]
    stock_dir = data_root / "stock_details"
    return sorted({p.name.split("_")[0] for p in stock_dir.glob("*_stocks.jsonl")})


def _load_stock_pool_rows(data_root: Path, subject_keys: Sequence[str]) -> List[Tuple]:
    stock_dir = data_root / "stock_details"
    wanted = {str(x) for x in subject_keys}
    rows: List[Tuple] = []
    for path in stock_dir.glob("*_stocks.jsonl"):
        subject_key = path.name.split("_")[0]
        if subject_key not in wanted:
            continue
        seen_stock_ids = set()
        for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if not isinstance(record, list) or len(record) < 4:
                continue
            stock_id = str(record[2]).strip() if record[2] is not None else ""
            if not stock_id or stock_id in seen_stock_ids:
                continue
            seen_stock_ids.add(stock_id)
            stock_name = record[3]
            pct_chg = record[10] if len(record) > 10 and isinstance(record[10], (int, float)) else None
            evidence_json = json.dumps(
                {
                    "evidence_source": "jyhf_stock_list_file",
                    "file_name": path.name,
                    "subject_key": subject_key,
                    "row_index": idx,
                },
                ensure_ascii=False,
            )
            rows.append(
                (
                    subject_key,
                    stock_id,
                    stock_name,
                    pct_chg,
                    idx,
                    False,
                    "derived from jyhf *_stocks.jsonl full stock pool",
                    None,
                    "jyhf_stock_list",
                    0.80,
                    evidence_json,
                )
            )
    return rows


async def _load_leader_rows(manager: PostgresDatabaseManager, subject_keys: Sequence[str]) -> List[Tuple]:
    sql = """
    SELECT DISTINCT ON (child_subject_key, lead_stock_id)
        child_subject_key AS subject_key,
        lead_stock_id AS stock_id,
        COALESCE(lead_stock_name, s.name) AS stock_name,
        scs.pct_chg,
        1 AS sort,
        TRUE AS top,
        'derived from subject_children_staging lead stock' AS reason,
        child_name AS remark,
        'jyhf_children_leader' AS source_type,
        0.95 AS confidence,
        jsonb_build_object(
            'evidence_source', 'subject_children_staging',
            'parent_subject_key', parent_subject_key,
            'child_subject_key', child_subject_key,
            'child_name', child_name,
            'lead_stock_id', lead_stock_id,
            'lead_stock_name', lead_stock_name,
            'stock_count', stock_count,
            'pct_chg', scs.pct_chg,
            'source_type', source_type
        )::text AS evidence_json
    FROM subject_children_staging scs
    LEFT JOIN stocks s
      ON s.stock_id = scs.lead_stock_id
    WHERE lead_stock_id IS NOT NULL
      AND child_subject_key = ANY($1::varchar[])
    ORDER BY child_subject_key, lead_stock_id, depth ASC, sort ASC NULLS LAST
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, list(subject_keys))
    return [
        (
            str(r["subject_key"]),
            str(r["stock_id"]),
            r["stock_name"],
            r["pct_chg"],
            r["sort"],
            r["top"],
            r["reason"],
            r["remark"],
            r["source_type"],
            r["confidence"],
            r["evidence_json"],
        )
        for r in rows
    ]


async def sync_subjects(
    manager: PostgresDatabaseManager,
    subject_keys: Sequence[str],
    batch_id: str,
    data_root: Path,
) -> Tuple[int, int, int]:
    if not subject_keys:
        return 0, 0, 0

    delete_map_sql = """
    DELETE FROM subject_stock_map
    WHERE subject_key = ANY($1::varchar[])
      AND COALESCE(source_type, 'jyhf') IN ('jyhf', 'jyhf_children', 'jyhf_stock_list', 'jyhf_children_leader')
    """
    insert_pool_sql = """
    INSERT INTO subject_stock_map (
        subject_key,
        stock_id,
        name,
        pct_chg,
        sort,
        top,
        reason,
        remark,
        source_type,
        confidence,
        evidence_json
    )
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb)
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        pct_chg = EXCLUDED.pct_chg,
        sort = EXCLUDED.sort,
        top = EXCLUDED.top,
        reason = EXCLUDED.reason,
        remark = EXCLUDED.remark,
        source_type = EXCLUDED.source_type,
        confidence = EXCLUDED.confidence,
        evidence_json = EXCLUDED.evidence_json,
        updated_at = NOW()
    """
    insert_leader_sql = """
    INSERT INTO subject_stock_map (
        subject_key,
        stock_id,
        name,
        pct_chg,
        sort,
        top,
        reason,
        remark,
        source_type,
        confidence,
        evidence_json
    )
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb)
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        name = COALESCE(EXCLUDED.name, subject_stock_map.name),
        pct_chg = COALESCE(EXCLUDED.pct_chg, subject_stock_map.pct_chg),
        sort = LEAST(COALESCE(subject_stock_map.sort, 999999), COALESCE(EXCLUDED.sort, 999999)),
        top = subject_stock_map.top OR EXCLUDED.top,
        reason = COALESCE(EXCLUDED.reason, subject_stock_map.reason),
        remark = COALESCE(EXCLUDED.remark, subject_stock_map.remark),
        source_type = CASE
            WHEN EXCLUDED.top THEN EXCLUDED.source_type
            ELSE subject_stock_map.source_type
        END,
        confidence = GREATEST(COALESCE(subject_stock_map.confidence, 0), COALESCE(EXCLUDED.confidence, 0)),
        evidence_json = COALESCE(EXCLUDED.evidence_json, subject_stock_map.evidence_json),
        updated_at = NOW()
    """
    delete_staging_sql = """
    DELETE FROM subject_stock_staging
    WHERE subject_key = ANY($1::varchar[])
    """
    insert_staging_sql = """
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
        $2
    FROM subject_stock_map ssm
    LEFT JOIN stocks s
      ON s.stock_id = ssm.stock_id
    WHERE ssm.subject_key = ANY($1::varchar[])
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
    delete_serving_sql = """
    DELETE FROM theme_stock_map
    WHERE subject_key = ANY($1::varchar[])
    """
    insert_serving_sql = """
    INSERT INTO theme_stock_map (
        subject_key, theme_id, theme_name, stock_id, stock_name,
        relation_type, evidence_source, confidence, source_type,
        reason, remark, evidence_json, effective_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        stock_id,
        stock_name,
        relation_type_candidate AS relation_type,
        source_type AS evidence_source,
        confidence,
        source_type,
        reason,
        remark,
        evidence_json,
        NOW() AS effective_at
    FROM (
        SELECT
            c.*,
            ROW_NUMBER() OVER (
                PARTITION BY c.subject_key, c.stock_id
                ORDER BY
                    CASE WHEN c.theme_id IS NOT NULL THEN 0 ELSE 1 END,
                    CASE c.relation_type_candidate
                        WHEN 'leader' THEN 0
                        WHEN 'core' THEN 1
                        ELSE 2
                    END,
                    c.source_type
            ) AS rn
        FROM vw_theme_stock_map_candidate c
        WHERE c.subject_key = ANY($1::varchar[])
    ) dedup
    WHERE rn = 1
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        stock_name = EXCLUDED.stock_name,
        relation_type = EXCLUDED.relation_type,
        evidence_source = EXCLUDED.evidence_source,
        confidence = EXCLUDED.confidence,
        source_type = EXCLUDED.source_type,
        reason = EXCLUDED.reason,
        remark = EXCLUDED.remark,
        evidence_json = EXCLUDED.evidence_json,
        effective_at = EXCLUDED.effective_at,
        updated_at = NOW()
    """

    pool_rows = _load_stock_pool_rows(data_root, subject_keys)
    leader_rows = await _load_leader_rows(manager, subject_keys)

    async with manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(delete_map_sql, list(subject_keys))
            if pool_rows:
                await conn.executemany(insert_pool_sql, pool_rows)
            if leader_rows:
                await conn.executemany(insert_leader_sql, leader_rows)

            await conn.execute(delete_staging_sql, list(subject_keys))
            await conn.execute(insert_staging_sql, list(subject_keys), batch_id)

            await conn.execute(delete_serving_sql, list(subject_keys))
            await conn.execute(insert_serving_sql, list(subject_keys))

    async with manager.pool.acquire() as conn:
        map_count = await conn.fetchval(
            "SELECT COUNT(*) FROM subject_stock_map WHERE subject_key = ANY($1::varchar[])",
            list(subject_keys),
        )
        staging_count = await conn.fetchval(
            "SELECT COUNT(*) FROM subject_stock_staging WHERE subject_key = ANY($1::varchar[])",
            list(subject_keys),
        )
        serving_count = await conn.fetchval(
            "SELECT COUNT(*) FROM theme_stock_map WHERE subject_key = ANY($1::varchar[])",
            list(subject_keys),
        )

    return int(map_count or 0), int(staging_count or 0), int(serving_count or 0)


async def main() -> int:
    args = parse_args()
    batch_id = args.batch_id or "jyhf_stock_incremental"
    data_root = Path(args.data_root).resolve()

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        subject_keys = await _resolve_subject_keys(manager, _load_subject_keys(args.subjects_file), data_root)
        map_count, staging_count, serving_count = await sync_subjects(manager, subject_keys, batch_id, data_root)
        print(
            f"[OK] synced stock incrementally subjects={len(subject_keys)} "
            f"map_rows={map_count} staging_rows={staging_count} serving_rows={serving_count} batch_id={batch_id}"
        )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
