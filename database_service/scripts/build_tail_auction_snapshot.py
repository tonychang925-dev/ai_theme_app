#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.config import StockServiceConfig
from stock_service.services.tushare_auction_snapshot_service import TushareAuctionSnapshotService


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
    parser = argparse.ArgumentParser(description="抓取并缓存 stk_auction_c 尾盘竞价快照")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN", ""), help="Tushare token")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新 raw snapshot")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _canonical_stock_id(value: str) -> str:
    raw = str(value or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


async def fetch_candidate_stock_ids(manager: PostgresDatabaseManager, trade_date: str) -> list[str]:
    sql = """
    SELECT DISTINCT stock_id
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1::date
    ORDER BY stock_id ASC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, _parse_trade_date(trade_date))
    stock_ids = []
    for row in rows:
        stock_id = _canonical_stock_id(row["stock_id"])
        if stock_id:
            stock_ids.append(stock_id)
    return stock_ids


async def main_async() -> int:
    args = parse_args()
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        stock_ids = await fetch_candidate_stock_ids(manager, args.trade_date)
    finally:
        await manager.disconnect()

    config = StockServiceConfig(project_root=PROJECT_ROOT, tushare_token=args.token)
    service = TushareAuctionSnapshotService(config)
    result = service.fetch_or_cache_stk_auction_c(
        args.trade_date,
        stock_ids,
        force_refresh=args.force_refresh,
    )

    print(f"[OK] trade_date={args.trade_date}")
    print(f"[OK] candidate_stock_ids={len(stock_ids)}")
    print(f"[OK] cache_hit={result.cache_hit}")
    print(f"[OK] snapshot_path={result.snapshot_path}")
    print(f"[OK] row_count={result.row_count}")
    for record in result.records[: args.top_k]:
        print(
            f"[ROW] stock={record.get('ts_code') or record.get('stock_id')} "
            f"close={float(record.get('close') or 0):.4f} "
            f"vol={float(record.get('vol') or 0):.0f} "
            f"amount={float(record.get('amount') or 0):.2f} "
            f"vwap={float(record.get('vwap') or 0):.4f}"
        )
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
