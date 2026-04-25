from __future__ import annotations

import pytest

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

pytest.importorskip("asyncpg")

from database_service.managers.postgres_manager import PostgresDatabaseManager


@pytest.mark.asyncio
async def test_upsert_stock_daily_snapshot_rows_blocks_strategy_projection_source() -> None:
    manager = PostgresDatabaseManager(
        DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            redis=RedisConfig(enabled=False),
        )
    )

    with pytest.raises(ValueError, match="blocked non-truth writes to stock_daily_snapshot"):
        await manager.upsert_stock_daily_snapshot_rows(
            [
                {
                    "trade_date": "2026-04-07",
                    "stock_id": "002361.SZ",
                    "stock_name": "神剑股份",
                    "source_name": "stock_processing_service",
                    "labels": {"final_cycle_state": "repair"},
                }
            ]
        )


@pytest.mark.asyncio
async def test_upsert_stock_daily_snapshot_rows_blocks_missing_source_name() -> None:
    manager = PostgresDatabaseManager(
        DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            redis=RedisConfig(enabled=False),
        )
    )

    with pytest.raises(ValueError, match="blocked non-truth writes to stock_daily_snapshot"):
        await manager.upsert_stock_daily_snapshot_rows(
            [
                {
                    "trade_date": "2026-04-07",
                    "stock_id": "002361.SZ",
                    "stock_name": "神剑股份",
                }
            ]
        )


@pytest.mark.asyncio
async def test_upsert_stock_daily_snapshot_rows_blocks_non_tushare_source() -> None:
    manager = PostgresDatabaseManager(
        DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            redis=RedisConfig(enabled=False),
        )
    )

    with pytest.raises(ValueError, match="blocked non-truth writes to stock_daily_snapshot"):
        await manager.upsert_stock_daily_snapshot_rows(
            [
                {
                    "trade_date": "2026-04-07",
                    "stock_id": "002361.SZ",
                    "stock_name": "神剑股份",
                    "source_name": "manual_patch",
                }
            ]
        )
