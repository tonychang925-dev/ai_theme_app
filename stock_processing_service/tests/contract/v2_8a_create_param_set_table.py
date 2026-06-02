"""
v2.8a — Create strategy_param_set table and add columns to backtest_run.
"""
from __future__ import annotations

import asyncio, os, sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")

DDL_PARAM_SET = """
CREATE TABLE IF NOT EXISTS strategy_param_set (
    param_set_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'w2s',
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    signal_source TEXT NOT NULL DEFAULT 'w2s_signal_validation_v1_1b',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

ALTER_BACKTEST_RUN_PARAM_SET_ID = """
ALTER TABLE backtest_run
ADD COLUMN IF NOT EXISTS param_set_id TEXT
"""

ALTER_BACKTEST_RUN_SIGNAL_SOURCE = """
ALTER TABLE backtest_run
ADD COLUMN IF NOT EXISTS signal_source TEXT NOT NULL DEFAULT 'w2s_signal_validation_v1_1b'
"""

ALTER_BACKTEST_RUN_SOURCE_CHAIN = """
ALTER TABLE backtest_run
ADD COLUMN IF NOT EXISTS source_chain TEXT NOT NULL DEFAULT 'backtest_replay'
"""

INDEX_PARAM_SET_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_sp_category ON strategy_param_set(category)
"""

INDEX_BACKTEST_RUN_PARAM_SET = """
CREATE INDEX IF NOT EXISTS idx_br_param_set ON backtest_run(param_set_id)
"""


async def main():
    print("v2.8a — Creating strategy_param_set table and backtest_run columns...")
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # Get a raw connection for multi-statement execution
    import asyncpg
    raw_conn = await asyncpg.connect(
        host="localhost", port=5432, user="postgres", password="postgres", database=DB_NAME
    )

    try:
        # Drop and recreate strategy_param_set to ensure clean schema
        await raw_conn.execute("DROP TABLE IF EXISTS strategy_param_set CASCADE")
        await raw_conn.execute(DDL_PARAM_SET)
        await raw_conn.execute(INDEX_PARAM_SET_CATEGORY)
        print("  ✅ strategy_param_set")

        # Add columns to backtest_run
        for stmt, label in [
            (ALTER_BACKTEST_RUN_PARAM_SET_ID, "param_set_id"),
            (ALTER_BACKTEST_RUN_SIGNAL_SOURCE, "signal_source"),
            (ALTER_BACKTEST_RUN_SOURCE_CHAIN, "source_chain"),
        ]:
            await raw_conn.execute(stmt)
            print(f"  ✅ backtest_run.{label}")

        await raw_conn.execute(INDEX_BACKTEST_RUN_PARAM_SET)
        print("  ✅ index on backtest_run(param_set_id)")
    finally:
        await raw_conn.close()

    await gw.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
