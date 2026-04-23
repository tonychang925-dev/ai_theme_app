#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from stock_service.config import StockServiceConfig


async def run_migration(config: StockServiceConfig, dry_run: bool = False) -> None:
    migration_file = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "migrations"
        / "add_mainline_state_tracking_tables.sql"
    )
    sql = migration_file.read_text(encoding="utf-8")

    if dry_run:
        print(sql)
        return

    pool = await asyncpg.create_pool(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
        min_size=1,
        max_size=2,
    )
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)

            checks = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_name IN ('mainline_state_daily', 'mainline_state_transition')
                ORDER BY table_name
                """
            )
            print("tables:", [r["table_name"] for r in checks])
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mainline state tracking migration")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(run_migration(StockServiceConfig(), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
