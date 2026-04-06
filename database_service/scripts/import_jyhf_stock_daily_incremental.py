#!/usr/bin/env python3
"""
将按交易日采集的 JYHF 股票池快照导入数据库。

处理链：
- theme_data_complete/stock_daily/*_YYYY-MM-DD_stocks.jsonl -> subject_stock_daily_snapshot
- 可选：按 trade_date 刷新对应 subject 的当前 theme_stock_map
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.scripts.import_jyhf_stock_incremental import (
    _load_leader_rows,
    ensure_tables as ensure_current_stock_tables,
)


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
    parser = argparse.ArgumentParser(description="增量导入 JYHF 股票日快照")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则处理 trade-date 下所有文件")
    parser.add_argument("--batch-id", default=None, help="同步批次 ID")
    parser.add_argument("--trade-date", required=True, help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--data-root", default=str(PROJECT_ROOT / "theme_data_complete"), help="本地数据根目录")
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


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value):
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _is_limit_up(pct_chg: Optional[float]) -> bool:
    if pct_chg is None:
        return False
    return pct_chg >= 9.8


def _parse_trade_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_stock_daily_snapshot (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        selected_id BIGINT,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        rank_order INTEGER,
        close_price NUMERIC(12,4),
        pre_close NUMERIC(12,4),
        open_price NUMERIC(12,4),
        high_price NUMERIC(12,4),
        low_price NUMERIC(12,4),
        pct_chg NUMERIC(8,4),
        change_amount NUMERIC(12,4),
        volume NUMERIC(20,2),
        amount NUMERIC(20,2),
        limit_up BOOLEAN DEFAULT FALSE,
        is_leader BOOLEAN DEFAULT FALSE,
        raw_json JSONB,
        ingest_batch_id VARCHAR(80),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_stock_daily_snapshot UNIQUE (trade_date, subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ssds_trade_date ON subject_stock_daily_snapshot(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_ssds_subject_date ON subject_stock_daily_snapshot(subject_key, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_ssds_stock_date ON subject_stock_daily_snapshot(stock_id, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
    await ensure_current_stock_tables(manager)


def iter_stock_files(data_root: Path, trade_date: str, subject_keys: Optional[Sequence[str]]):
    stock_daily_dir = data_root / "stock_daily"
    wanted = {str(x) for x in subject_keys} if subject_keys is not None else None
    pattern = f"*_{trade_date}_stocks.jsonl"
    for path in sorted(stock_daily_dir.glob(pattern)):
        subject_key = path.name.split("_")[0]
        if wanted is not None and subject_key not in wanted:
            continue
        yield path


def build_rows(data_root: Path, trade_date: str, subject_keys: Optional[Sequence[str]], batch_id: str) -> Tuple[List[Tuple], List[str]]:
    rows: List[Tuple] = []
    touched_subjects: set[str] = set()
    trade_date_value = _parse_trade_date(trade_date)
    for path in iter_stock_files(data_root, trade_date, subject_keys):
        subject_key = path.name.split("_")[0]
        touched_subjects.add(subject_key)
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, list) or len(row) < 15:
                    continue
                pct_chg = _to_float(row[10] if len(row) > 10 else None)
                rows.append(
                    (
                        trade_date_value,
                        subject_key,
                        _to_int(row[1] if len(row) > 1 else None),
                        str(row[2]) if len(row) > 2 and row[2] is not None else None,
                        row[3] if len(row) > 3 else None,
                        idx,
                        _to_float(row[4] if len(row) > 4 else None),
                        _to_float(row[5] if len(row) > 5 else None),
                        _to_float(row[6] if len(row) > 6 else None),
                        _to_float(row[7] if len(row) > 7 else None),
                        _to_float(row[8] if len(row) > 8 else None),
                        pct_chg,
                        _to_float(row[11] if len(row) > 11 else None),
                        _to_float(row[12] if len(row) > 12 else None),
                        _to_float(row[13] if len(row) > 13 else None),
                        _is_limit_up(pct_chg),
                        idx == 1,
                        json.dumps(row, ensure_ascii=False),
                        batch_id,
                    )
                )
    return rows, sorted(touched_subjects)


async def load_rows(manager: PostgresDatabaseManager, rows: List[Tuple]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO subject_stock_daily_snapshot (
        trade_date, subject_key, selected_id, stock_id, stock_name, rank_order,
        close_price, pre_close, open_price, high_price, low_price,
        pct_chg, change_amount, volume, amount,
        limit_up, is_leader, raw_json, ingest_batch_id
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10, $11,
        $12, $13, $14, $15,
        $16, $17, $18::jsonb, $19
    )
    ON CONFLICT (trade_date, subject_key, stock_id)
    DO UPDATE SET
        selected_id = EXCLUDED.selected_id,
        stock_name = EXCLUDED.stock_name,
        rank_order = EXCLUDED.rank_order,
        close_price = EXCLUDED.close_price,
        pre_close = EXCLUDED.pre_close,
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        pct_chg = EXCLUDED.pct_chg,
        change_amount = EXCLUDED.change_amount,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        limit_up = EXCLUDED.limit_up,
        is_leader = EXCLUDED.is_leader,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, rows)
    return len(rows)


async def refresh_current_mapping(
    manager: PostgresDatabaseManager,
    subject_keys: Sequence[str],
    trade_date: str,
    batch_id: str,
) -> Tuple[int, int, int]:
    if not subject_keys:
        return 0, 0, 0

    delete_map_sql = """
    DELETE FROM subject_stock_map
    WHERE subject_key = ANY($1::varchar[])
      AND COALESCE(source_type, 'jyhf') IN ('jyhf_stock_daily', 'jyhf_children_leader')
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
    SELECT
        subject_key,
        stock_id,
        stock_name,
        pct_chg,
        rank_order,
        FALSE AS top,
        'derived from jyhf stock daily snapshot' AS reason,
        $2::text AS remark,
        'jyhf_stock_daily' AS source_type,
        0.90 AS confidence,
        jsonb_build_object(
            'evidence_source', 'subject_stock_daily_snapshot',
            'trade_date', trade_date,
            'rank_order', rank_order,
            'limit_up', limit_up,
            'is_leader_candidate', is_leader
        ) AS evidence_json
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $2::date
      AND subject_key = ANY($1::varchar[])
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
        COALESCE(ssm.source_type, 'jyhf_stock_daily') AS source_type,
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

    leader_rows = await _load_leader_rows(manager, subject_keys)

    async with manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(delete_map_sql, list(subject_keys))
            await conn.execute(insert_pool_sql, list(subject_keys), trade_date)
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
    batch_id = args.batch_id or f"jyhf_stock_daily_import_{args.trade_date}"
    data_root = Path(args.data_root).resolve()
    subject_keys = _load_subject_keys(args.subjects_file)

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        rows, touched_subjects = build_rows(data_root, args.trade_date, subject_keys, batch_id)
        count = await load_rows(manager, rows)
        map_count, staging_count, serving_count = await refresh_current_mapping(
            manager,
            touched_subjects,
            args.trade_date,
            batch_id,
        )
        print(
            f"[OK] imported stock daily snapshot trade_date={args.trade_date} "
            f"subjects={len(touched_subjects)} rows={count} "
            f"current_map={map_count} staging={staging_count} serving={serving_count} "
            f"batch_id={batch_id}"
        )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
