-- Strategy object-layer snapshot table.
-- This table stores projector outputs and must not be used as market truth.

CREATE TABLE IF NOT EXISTS stock_daily_strategy_snapshot (
    trade_date DATE NOT NULL,
    stock_id VARCHAR(32) NOT NULL,
    stock_name VARCHAR(128),
    close_price NUMERIC(18, 6),
    pct_chg NUMERIC(18, 6),
    volume NUMERIC(20, 2),
    amount NUMERIC(20, 2),
    limit_up_price NUMERIC(18, 6),
    limit_down_price NUMERIC(18, 6),
    snapshot_version VARCHAR(64) NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    trace_id VARCHAR(128) NOT NULL,
    source_trace_id VARCHAR(128),
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_name VARCHAR(64) NOT NULL DEFAULT 'stock_processing_service',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_daily_strategy_snapshot_trade_date
ON stock_daily_strategy_snapshot (trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_daily_strategy_snapshot_source
ON stock_daily_strategy_snapshot (source_name);

