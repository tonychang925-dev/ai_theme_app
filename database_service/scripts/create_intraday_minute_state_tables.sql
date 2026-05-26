-- P1-I-3: 盘中分钟状态层
-- 从 jyhf_stock_quote_snapshot / jyhf_index_quote_snapshot 聚合分钟级状态
-- 仅覆盖候选池 + 强势股范围，不做全市场

CREATE TABLE IF NOT EXISTS intraday_stock_minute_state (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    minute_ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT DEFAULT '',

    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4),
    current NUMERIC(12,4),
    pct_chg NUMERIC(8,4),

    amount NUMERIC(20,2),
    vol NUMERIC(20,2),
    amount_delta NUMERIC(20,2),
    vol_delta NUMERIC(20,2),

    vwap NUMERIC(12,4),
    above_vwap BOOLEAN,
    minute_return NUMERIC(10,4),
    day_return NUMERIC(10,4),

    index_code TEXT,
    index_pct_chg NUMERIC(8,4),
    relative_strength_vs_index NUMERIC(10,4),

    platform_high_30m NUMERIC(12,4),
    platform_low_30m NUMERIC(12,4),
    break_platform_30m BOOLEAN DEFAULT FALSE,

    source_quote_count INT DEFAULT 0,
    source_channel TEXT DEFAULT 'jyhf_market_api',
    raw_json JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (trade_date, minute_ts, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_intraday_stock_minute_state_stock_time
    ON intraday_stock_minute_state(stock_id, minute_ts DESC);

CREATE INDEX IF NOT EXISTS idx_intraday_stock_minute_state_trade_time
    ON intraday_stock_minute_state(trade_date, minute_ts DESC);


CREATE TABLE IF NOT EXISTS intraday_index_minute_state (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    minute_ts TIMESTAMPTZ NOT NULL,
    index_code TEXT NOT NULL,
    index_name TEXT DEFAULT '',

    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4),
    current NUMERIC(12,4),
    pct_chg NUMERIC(8,4),

    amount NUMERIC(20,2),
    vol NUMERIC(20,2),
    source_quote_count INT DEFAULT 0,
    raw_json JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (trade_date, minute_ts, index_code)
);

CREATE INDEX IF NOT EXISTS idx_intraday_index_minute_state_time
    ON intraday_index_minute_state(trade_date, minute_ts DESC);
