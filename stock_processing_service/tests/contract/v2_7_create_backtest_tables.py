"""
v2.7 — Create backtest result tables for dashboard visualization.
"""
from __future__ import annotations

import asyncio, os, sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")

DDL_RUN = """
CREATE TABLE IF NOT EXISTS backtest_run (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL DEFAULT '',
    strategy_version TEXT NOT NULL DEFAULT '',
    start_date DATE,
    end_date DATE,
    initial_capital NUMERIC(18,2) NOT NULL DEFAULT 1000000,
    final_equity NUMERIC(18,2),
    total_return NUMERIC(12,6),
    annual_return NUMERIC(12,6),
    max_drawdown NUMERIC(12,6),
    win_rate NUMERIC(8,4),
    profit_factor NUMERIC(8,2),
    trade_count INTEGER DEFAULT 0,
    avg_return_per_trade NUMERIC(12,6),
    avg_hold_days NUMERIC(8,2),
    max_single_loss NUMERIC(18,2),
    max_consecutive_losses INTEGER DEFAULT 0,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    skip_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_table TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(strategy_id, strategy_version)
)
"""

DDL_EQUITY = """
CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES backtest_run(run_id),
    strategy_id TEXT NOT NULL,
    trade_date DATE NOT NULL,
    cash NUMERIC(18,2),
    position_value NUMERIC(18,2),
    total_equity NUMERIC(18,2),
    daily_return NUMERIC(12,6),
    cumulative_return NUMERIC(12,6),
    drawdown NUMERIC(12,6),
    active_positions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, trade_date)
)
"""

DDL_TRADE = """
CREATE TABLE IF NOT EXISTS backtest_trade (
    trade_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES backtest_run(run_id),
    strategy_id TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',
    entry_date DATE NOT NULL,
    entry_price NUMERIC(12,4),
    exit_date DATE,
    exit_price NUMERIC(12,4),
    shares INTEGER DEFAULT 0,
    position_value NUMERIC(18,2),
    cost NUMERIC(18,2),
    proceeds NUMERIC(18,2),
    pnl NUMERIC(18,2),
    return_pct NUMERIC(12,6),
    hold_days INTEGER DEFAULT 0,
    exit_reason TEXT NOT NULL DEFAULT '',
    exit_rule TEXT NOT NULL DEFAULT '',
    support_type TEXT NOT NULL DEFAULT '',
    support_strength NUMERIC(8,2),
    weak_type TEXT,
    candidate_score NUMERIC(8,2),
    candidate_type TEXT,
    pool_entry_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, entry_date, stock_id)
)
"""

DDL_MONTHLY = """
CREATE TABLE IF NOT EXISTS backtest_monthly_return (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES backtest_run(run_id),
    strategy_id TEXT NOT NULL,
    month TEXT NOT NULL,
    start_equity NUMERIC(18,2),
    end_equity NUMERIC(18,2),
    return_pct NUMERIC(12,6),
    trade_count INTEGER DEFAULT 0,
    win_rate NUMERIC(8,4),
    max_drawdown NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, month)
)
"""


async def main():
    print("Creating v2.7 backtest tables...")
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    for name, ddl in [("backtest_run", DDL_RUN), ("backtest_equity_curve", DDL_EQUITY),
                       ("backtest_trade", DDL_TRADE), ("backtest_monthly_return", DDL_MONTHLY)]:
        for stmt in [s.strip() for s in ddl.split(";") if s.strip() and not s.strip().startswith("--")]:
            await c.execute_query(stmt + ";")
        print(f"  ✅ {name}")

    await gw.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
