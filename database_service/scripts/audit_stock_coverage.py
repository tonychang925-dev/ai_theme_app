#!/usr/bin/env python3
"""
审计久赢股票真源与本地数据库覆盖差异。

输出三类关键信息：
1. 题材股票列表 *_stocks.jsonl 覆盖的全部股票数
2. 本地个股详情 *_detail.json 覆盖的股票数
3. 数据库 stocks / subject_stock_detail_staging / subject_stock_map 的覆盖差异
"""

import asyncio
import json
import os
import re
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


STOCK_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_details"


def collect_subject_list_stock_ids() -> set[str]:
    stock_ids: set[str] = set()
    for path in STOCK_DIR.glob("*_stocks.jsonl"):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, list) and len(row) >= 3:
                stock_ids.add(str(row[2]).strip())
            elif isinstance(row, dict):
                stock_id = row.get("stock_id") or row.get("stockId") or row.get("code") or row.get("symbol")
                if stock_id:
                    stock_ids.add(str(stock_id).strip())
    stock_ids.discard("")
    return stock_ids


def collect_detail_stock_ids() -> set[str]:
    stock_ids: set[str] = set()
    for path in STOCK_DIR.glob("*_detail.json"):
        match = re.match(r"(.+?)_detail\.json$", path.name)
        if not match:
            continue
        stock_ids.add(match.group(1))
    stock_ids.discard("")
    return stock_ids


async def collect_db_stats() -> dict:
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                select
                  (select count(*) from stocks) as stocks_rows,
                  (select count(distinct stock_id) from stocks) as stocks_distinct,
                  (select count(*) from subject_stock_detail_staging) as ssds_rows,
                  (select count(distinct stock_id) from subject_stock_detail_staging) as ssds_distinct,
                  (select count(*) from subject_stock_map) as ssm_rows,
                  (select count(distinct stock_id) from subject_stock_map) as ssm_distinct,
                  (select count(*) from theme_stock_map) as tsm_rows,
                  (select count(distinct stock_id) from theme_stock_map) as tsm_distinct
                """
            )
            missing = await conn.fetch(
                """
                select distinct m.stock_id, m.name
                from subject_stock_map m
                left join stocks s on s.stock_id = m.stock_id
                where coalesce(m.stock_id, '') <> ''
                  and s.stock_id is null
                order by m.stock_id
                limit 50
                """
            )
            return {
                "db": dict(stats),
                "missing_mapped_stock_sample": [dict(r) for r in missing],
            }
    finally:
        await manager.disconnect()


async def main() -> int:
    if not STOCK_DIR.exists():
        print(f"[ERROR] stock dir not found: {STOCK_DIR}")
        return 1

    subject_list_ids = collect_subject_list_stock_ids()
    detail_ids = collect_detail_stock_ids()
    db_stats = await collect_db_stats()

    report = {
        "subject_list_stock_count": len(subject_list_ids),
        "detail_file_stock_count": len(detail_ids),
        "missing_detail_count": len(subject_list_ids - detail_ids),
        "missing_detail_sample": sorted(subject_list_ids - detail_ids)[:50],
        "extra_detail_count": len(detail_ids - subject_list_ids),
        "extra_detail_sample": sorted(detail_ids - subject_list_ids)[:50],
        **db_stats,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
