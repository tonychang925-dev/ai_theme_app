#!/usr/bin/env python3
"""修复 2026-06-01 Layer C 强势股污染记录。

流程：
1. 备份 2026-06-01 的 strong_stock_watch_history / strong_stock_watch_pool
2. 删除这一天的池与历史
3. 用修正后的 get_strong_watch_seed_rows 重新跑 6/1 recap

仅用于本地/测试库回填，不要在生产库直接执行。
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from uuid import uuid4

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, SPS_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
    BuildStrongStockTrackingUseCase,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_write_gateway_adapter import (
    StockWriteGatewayAdapter,
)


TARGET_DATE = date(2026, 6, 1)
SNAPSHOT_VERSION = "layer_c_fix_20260601.v1"


async def main() -> None:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    read_port = StockReadGatewayAdapter(db_gateway=gw)
    write_port = StockWriteGatewayAdapter(db_gateway=gw)

    use_case = BuildStrongStockTrackingUseCase(
        read_ports=read_port,
        write_ports=write_port,
    )

    async with gw._client.pool.acquire() as conn:
        hist_backup = await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strong_stock_watch_history_backup_20260601_fix AS
            SELECT *
            FROM strong_stock_watch_history
            WHERE trade_date = $1::date
            """,
            TARGET_DATE,
        )
        pool_backup = await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strong_stock_watch_pool_backup_20260601_fix AS
            SELECT *
            FROM strong_stock_watch_pool
            WHERE last_trade_date = $1::date
            """,
            TARGET_DATE,
        )
        print(f"backup history: {hist_backup}")
        print(f"backup pool: {pool_backup}")

        deleted_hist = await conn.execute(
            "DELETE FROM strong_stock_watch_history WHERE trade_date = $1::date",
            TARGET_DATE,
        )
        deleted_pool = await conn.execute(
            "DELETE FROM strong_stock_watch_pool WHERE last_trade_date = $1::date",
            TARGET_DATE,
        )
        print(f"deleted history: {deleted_hist}")
        print(f"deleted pool: {deleted_pool}")

    result = await use_case.execute(trade_date=TARGET_DATE, window_days=7, lookback_days=8)
    print(
        "rebuild result:",
        {
            "status": result.status,
            "affected_rows": result.affected_rows,
            "metrics": result.metrics,
        },
    )

    async with gw._client.pool.acquire() as conn:
        hist_count = await conn.fetchval(
            "SELECT COUNT(*) FROM strong_stock_watch_history WHERE trade_date = $1::date",
            TARGET_DATE,
        )
        pool_count = await conn.fetchval(
            "SELECT COUNT(*) FROM strong_stock_watch_pool WHERE last_trade_date = $1::date",
            TARGET_DATE,
        )
        print(f"final history count: {hist_count}")
        print(f"final pool count: {pool_count}")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
