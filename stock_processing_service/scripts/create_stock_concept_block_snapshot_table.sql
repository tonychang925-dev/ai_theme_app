-- M4a.1: stock_concept_block_snapshot
-- Stores Eastmoney concept/industry/region block → stock mappings.
-- Complements subject_stock_map with external block evidence.
CREATE TABLE IF NOT EXISTS stock_concept_block_snapshot (
    id BIGSERIAL NOT NULL,
    trade_date DATE NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    block_code TEXT NOT NULL,
    block_name TEXT NOT NULL,
    block_type TEXT NOT NULL DEFAULT 'concept',  -- concept | industry | region
    pct_chg NUMERIC,
    source_name TEXT NOT NULL DEFAULT 'eastmoney',
    endpoint_key TEXT NOT NULL DEFAULT 'eastmoney_concept_blocks',
    source_trace_id TEXT NOT NULL,
    raw_snapshot_id BIGINT REFERENCES source_raw_snapshot(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stock_code, block_code, source_name)
);
CREATE INDEX IF NOT EXISTS idx_stock_cb_stock_date
    ON stock_concept_block_snapshot(stock_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_cb_block_date
    ON stock_concept_block_snapshot(block_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_cb_trade_date
    ON stock_concept_block_snapshot(trade_date);
