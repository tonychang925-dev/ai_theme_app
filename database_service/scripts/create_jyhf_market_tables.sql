-- P1-A: 久赢恒丰行情接口采集 — 数据库建表
-- 执行: psql -U postgres -d stock_data_test -f create_jyhf_market_tables.sql

BEGIN;

-- 1. 原始接口响应留痕
CREATE TABLE IF NOT EXISTS jyhf_market_raw_capture (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    request_params JSONB,
    response_hash TEXT,
    raw_json JSONB,
    parse_status TEXT DEFAULT 'ok',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_jyhf_market_raw_capture_endpoint_time
    ON jyhf_market_raw_capture(endpoint_key, captured_at DESC);

-- 2. 个股实时行情快照
CREATE TABLE IF NOT EXISTS jyhf_stock_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    current NUMERIC,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    pct_chg NUMERIC,
    amount NUMERIC,
    vol NUMERIC,
    pe NUMERIC,
    market_value NUMERIC,
    limit_up NUMERIC,
    limit_down NUMERIC,
    source_endpoint TEXT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_jyhf_stock_quote_snapshot_stock_ts
    ON jyhf_stock_quote_snapshot(stock_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_jyhf_stock_quote_snapshot_trade_date
    ON jyhf_stock_quote_snapshot(trade_date);

-- 3. 指数实时行情
CREATE TABLE IF NOT EXISTS jyhf_index_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    index_code TEXT NOT NULL,
    index_name TEXT,
    current NUMERIC,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    pct_chg NUMERIC,
    amount NUMERIC,
    vol NUMERIC,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, index_code, ts)
);

-- 4. 题材下股票实时行情
CREATE TABLE IF NOT EXISTS jyhf_subject_stock_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    subject_id TEXT NOT NULL,
    subject_name TEXT,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    current NUMERIC,
    pct_chg NUMERIC,
    amount NUMERIC,
    vol NUMERIC,
    rank_no INT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, subject_id, stock_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_jyhf_subject_stock_quote_subject_ts
    ON jyhf_subject_stock_quote_snapshot(subject_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_jyhf_subject_stock_quote_stock_ts
    ON jyhf_subject_stock_quote_snapshot(stock_id, ts DESC);

COMMIT;
