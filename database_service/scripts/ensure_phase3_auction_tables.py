#!/usr/bin/env python3
"""
创建 P3.phase3 盘前集合竞价对象表。
"""

import asyncio
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


DDL = """
CREATE TABLE IF NOT EXISTS pre_market_auction_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',
    subject_key TEXT NOT NULL DEFAULT '',
    theme_name TEXT NOT NULL DEFAULT '',
    role_label TEXT NOT NULL DEFAULT '',
    window_start_time TEXT NOT NULL DEFAULT '09:20:00',
    window_end_time TEXT NOT NULL DEFAULT '09:25:00',
    last_minute_start_time TEXT NOT NULL DEFAULT '09:24:00',
    last_30s_start_time TEXT NOT NULL DEFAULT '09:24:30',
    auction_open_price NUMERIC(12,4) NOT NULL DEFAULT 0,
    pre_close NUMERIC(12,4) NOT NULL DEFAULT 0,
    auction_open_pct NUMERIC(8,4) NOT NULL DEFAULT 0,
    auction_volume NUMERIC(18,2) NOT NULL DEFAULT 0,
    auction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    last_minute_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    last_minute_ratio NUMERIC(8,4) NOT NULL DEFAULT 0,
    prev_day_max_intraday_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    carry_ratio NUMERIC(8,4) NOT NULL DEFAULT 0,
    price_path_stability_score NUMERIC(8,4) NOT NULL DEFAULT 0,
    is_red_zone BOOLEAN NOT NULL DEFAULT FALSE,
    has_end_spike BOOLEAN NOT NULL DEFAULT FALSE,
    has_end_drop BOOLEAN NOT NULL DEFAULT FALSE,
    shape_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_snapshot',
    source_trace_id TEXT NOT NULL DEFAULT '',
    source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_version TEXT NOT NULL DEFAULT 'auction_snapshot.v1',
    rule_version TEXT NOT NULL DEFAULT 'auction_snapshot.v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pre_market_auction_snapshot UNIQUE (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_pre_market_auction_snapshot_date
ON pre_market_auction_snapshot(trade_date);

CREATE INDEX IF NOT EXISTS idx_pre_market_auction_snapshot_subject
ON pre_market_auction_snapshot(subject_key);

CREATE TABLE IF NOT EXISTS pre_market_auction_signal (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',
    subject_key TEXT NOT NULL DEFAULT '',
    theme_name TEXT NOT NULL DEFAULT '',
    role_label TEXT NOT NULL DEFAULT '',
    auction_signal_score NUMERIC(8,4) NOT NULL DEFAULT 0,
    auction_signal_level TEXT NOT NULL DEFAULT '',
    signal_type TEXT NOT NULL DEFAULT '',
    leader_status TEXT NOT NULL DEFAULT '',
    action_today TEXT NOT NULL DEFAULT '',
    hard_reject_reason TEXT NOT NULL DEFAULT '',
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_signal',
    source_trace_id TEXT NOT NULL DEFAULT '',
    source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_version TEXT NOT NULL DEFAULT 'auction_signal.v1',
    rule_version TEXT NOT NULL DEFAULT 'auction_signal.v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pre_market_auction_signal UNIQUE (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_pre_market_auction_signal_date
ON pre_market_auction_signal(trade_date);

CREATE INDEX IF NOT EXISTS idx_pre_market_auction_signal_subject
ON pre_market_auction_signal(subject_key);
"""


async def main() -> int:
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            await conn.execute(DDL)
            await conn.execute(
                "ALTER TABLE pre_market_auction_snapshot ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )
            await conn.execute(
                "ALTER TABLE pre_market_auction_signal ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )
        print("[OK] ensured p3 phase3 auction tables")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
