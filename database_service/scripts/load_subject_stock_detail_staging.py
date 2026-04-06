#!/usr/bin/env python3
"""
将 theme_data_complete/stock_details/*.json 导入 subject_stock_detail_staging。

用途：
- 固化股票详情真源
- 为 phase1 的 theme_stock_map 证据增强与股票详情补充提供标准化层
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


DETAIL_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_details"


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS subject_stock_detail_staging (
        id BIGSERIAL PRIMARY KEY,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        first_letter VARCHAR(20),
        remark TEXT,
        detail_html TEXT,
        price NUMERIC(12,4),
        pct_chg NUMERIC(8,4),
        amount NUMERIC(20,2),
        market_value NUMERIC(20,2),
        high NUMERIC(12,4),
        low NUMERIC(12,4),
        source_type VARCHAR(50) DEFAULT 'jyhf_stock_detail',
        raw_json JSONB,
        ingest_batch_id VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_subject_stock_detail_staging UNIQUE (stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ssds_name ON subject_stock_detail_staging(stock_name);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _clean_text(value):
    if value is None:
        return None
    return str(value).replace("\x00", "").replace("\\u0000", "")


def _clean_obj(value):
    if isinstance(value, dict):
        return {k: _clean_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_obj(v) for v in value]
    if isinstance(value, str):
        return _clean_text(value)
    return value


async def load_rows(manager: PostgresDatabaseManager, batch_id: str) -> int:
    rows = []
    invalid_files = 0

    for path in sorted(DETAIL_DIR.glob("*_detail.json")):
        if path.name.startswith("."):
            invalid_files += 1
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            invalid_files += 1
            print(f"[WARN] skip invalid stock detail file={path.name}")
            continue
        obj = _clean_obj(obj)
        data = obj.get("data") or {}
        stock_id = data.get("stockId") or path.stem.replace("_detail", "")
        rows.append(
            (
                str(stock_id),
                _clean_text(data.get("name")),
                _clean_text(data.get("firstLetter")),
                _clean_text(data.get("remark")),
                _clean_text(data.get("detail")),
                _to_float(data.get("price")),
                _to_float(data.get("pctChg")),
                _to_float(data.get("amount")),
                _to_float(data.get("marketValue")),
                _to_float(data.get("high")),
                _to_float(data.get("low")),
                "jyhf_stock_detail",
                _clean_text(json.dumps(obj, ensure_ascii=False)),
                batch_id,
            )
        )

    if not rows:
        return 0

    if invalid_files:
        print(f"[WARN] skipped invalid stock detail files={invalid_files}")

    sql = """
    INSERT INTO subject_stock_detail_staging (
        stock_id, stock_name, first_letter, remark, detail_html,
        price, pct_chg, amount, market_value, high, low,
        source_type, raw_json, ingest_batch_id
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9, $10, $11,
        $12, $13, $14
    )
    ON CONFLICT (stock_id)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        first_letter = EXCLUDED.first_letter,
        remark = EXCLUDED.remark,
        detail_html = EXCLUDED.detail_html,
        price = EXCLUDED.price,
        pct_chg = EXCLUDED.pct_chg,
        amount = EXCLUDED.amount,
        market_value = EXCLUDED.market_value,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        source_type = EXCLUDED.source_type,
        raw_json = EXCLUDED.raw_json,
        ingest_batch_id = EXCLUDED.ingest_batch_id,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, rows)
    return len(rows)


async def main() -> int:
    if not DETAIL_DIR.exists():
        print(f"[ERROR] stock detail dir not found: {DETAIL_DIR}")
        return 1

    batch_id = os.getenv("PHASE1_BATCH_ID", "p2_phase1_stock_detail")
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        count = await load_rows(manager, batch_id)
        print(f"[OK] loaded subject_stock_detail_staging rows={count} batch_id={batch_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
