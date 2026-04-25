from __future__ import annotations

import os

import pytest

pytest.importorskip("asyncpg")
import asyncpg


@pytest.mark.asyncio
async def test_stock_daily_snapshot_trigger_blocks_non_tushare_update() -> None:
    """DB-level guard must reject non-tushare source_name on truth table."""
    dsn = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "database": os.getenv("REPLAY_DB_NAME", "stock_data_test"),
        "user": os.getenv("PG_USERNAME", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "ssl": os.getenv("PG_SSL_MODE", "prefer"),
    }

    try:
        conn = await asyncpg.connect(**dsn)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres unavailable for integration test: {exc}")
        return

    try:
        row = await conn.fetchrow(
            """
            SELECT trade_date, stock_id
            FROM stock_daily_snapshot
            WHERE source_name ILIKE 'tushare%'
            LIMIT 1
            """
        )
        if row is None:
            pytest.skip("no tushare row available in stock_daily_snapshot for trigger probe")
            return

        trade_date = row["trade_date"]
        stock_id = row["stock_id"]

        async with conn.transaction():
            with pytest.raises(asyncpg.PostgresError, match="blocked: non-truth source_name"):
                await conn.execute(
                    """
                    UPDATE stock_daily_snapshot
                    SET source_name = 'manual_patch'
                    WHERE trade_date = $1
                      AND stock_id = $2
                      AND source_name ILIKE 'tushare%'
                    """,
                    trade_date,
                    stock_id,
                )
    finally:
        await conn.close()

