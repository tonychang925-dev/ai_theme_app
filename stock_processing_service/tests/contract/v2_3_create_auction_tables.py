#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.3 — Real Auction Timeline Data Tables DDL                             ║
║  Date: 2026-05-19                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Two new tables:
  1. pre_market_auction_timeline_raw   — raw timeline snapshots (09:20-09:25)
  2. pre_market_auction_feature        — computed D2 features from timeline

Usage: python stock_processing_service/tests/contract/v2_3_create_auction_tables.py
"""

from __future__ import annotations

import asyncio, os, sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")

DDL_RAW = """
CREATE TABLE IF NOT EXISTS pre_market_auction_timeline_raw (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,       -- '09:20:00' through '09:25:00'
    indicative_open_price NUMERIC(12,4),
    indicative_open_pct NUMERIC(8,4),
    matched_volume NUMERIC(18,2),
    matched_amount NUMERIC(18,2),
    bid_price NUMERIC(12,4),
    ask_price NUMERIC(12,4),
    bid_volume NUMERIC(18,2),
    ask_volume NUMERIC(18,2),
    source_name TEXT NOT NULL DEFAULT 'tushare',
    source_api TEXT NOT NULL DEFAULT 'stk_auction',
    data_mode TEXT NOT NULL DEFAULT 'synthetic_single_point',
    -- 'synthetic_single_point' = single 09:25 point from stk_auction
    -- 'timeline_tick'          = multi-point timeline from Level-2
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(trade_date, stock_id, snapshot_time)
);

CREATE INDEX IF NOT EXISTS idx_auction_timeline_raw_date
ON pre_market_auction_timeline_raw(trade_date);

CREATE INDEX IF NOT EXISTS idx_auction_timeline_raw_stock
ON pre_market_auction_timeline_raw(stock_id);

CREATE INDEX IF NOT EXISTS idx_auction_timeline_raw_date_stock
ON pre_market_auction_timeline_raw(trade_date, stock_id);
"""

DDL_FEATURE = """
CREATE TABLE IF NOT EXISTS pre_market_auction_feature (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',
    subject_key TEXT NOT NULL DEFAULT '',
    theme_name TEXT NOT NULL DEFAULT '',

    -- Core features computed from timeline
    open_pct_0925 NUMERIC(8,4),
    price_trend_0920_0925 NUMERIC(8,4),
    -- positive = upward trend, negative = downward
    price_stability_score NUMERIC(8,4),
    -- 0-100, higher = more stable
    last_minute_price_change NUMERIC(8,4),
    last_minute_volume_ratio NUMERIC(8,4),
    last_minute_grab_score NUMERIC(8,4),
    -- 0-100 composite
    tail_drop_risk NUMERIC(8,4),
    -- 0-1, higher = more drop risk
    auction_volume_ratio NUMERIC(8,4),
    -- auction_amount / prev_day_max_intraday_amount

    -- Pattern detection
    auction_pattern TEXT,
    -- stable / tail_lift / tail_drop / step_up / u_recovery / volatile
    shape_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_red_zone BOOLEAN DEFAULT false,
    has_end_spike BOOLEAN DEFAULT false,
    has_end_drop BOOLEAN DEFAULT false,

    -- Data quality
    data_status TEXT NOT NULL DEFAULT 'synthetic_single_point',
    -- real_auction_timeline / synthetic_single_point / partial / missing
    timeline_points_count INTEGER NOT NULL DEFAULT 0,
    timeline_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- snapshot of [{"ts":"09:20:00","price":...,"amount":...},...]

    -- Source
    rule_version TEXT NOT NULL DEFAULT 'auction_feature.v2.3',
    source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_auction_feature_date
ON pre_market_auction_feature(trade_date);

CREATE INDEX IF NOT EXISTS idx_auction_feature_stock
ON pre_market_auction_feature(stock_id);

CREATE INDEX IF NOT EXISTS idx_auction_feature_status
ON pre_market_auction_feature(data_status);
"""


async def main():
    print(f"\n{'='*60}")
    print(f"  v2.3 — CREATE AUCTION TIMELINE TABLES")
    print(f"{'='*60}")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # Raw table
    print(f"\n  Creating pre_market_auction_timeline_raw...")
    await c.execute_query(DDL_RAW)
    print(f"  ✅ pre_market_auction_timeline_raw ready")

    # Feature table
    print(f"\n  Creating pre_market_auction_feature...")
    await c.execute_query(DDL_FEATURE)
    print(f"  ✅ pre_market_auction_feature ready")

    print(f"\n{'='*60}")
    print(f"  Tables created successfully")
    print(f"{'='*60}\n")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
