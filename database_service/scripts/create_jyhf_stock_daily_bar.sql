-- P1-F: JYHF 日K线存储表
-- 对应接口: GET /api/app/data/one-stock-daily
-- 用于盘后回补、K线形态判断、D1 弱转强结构判断

CREATE TABLE IF NOT EXISTS jyhf_stock_daily_bar (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    api_stock_id TEXT DEFAULT '',
    stock_name TEXT DEFAULT '',
    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4),
    pre_close NUMERIC(12,4),
    change NUMERIC(12,4),
    pct_chg NUMERIC(8,4),
    vol NUMERIC(18,2),
    amount NUMERIC(18,2),
    source_channel TEXT DEFAULT 'jyhf_market_api',
    source_endpoint TEXT DEFAULT '/api/app/data/one-stock-daily',
    raw_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_jyhf_stock_daily_bar_stock_date
    ON jyhf_stock_daily_bar(stock_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_jyhf_stock_daily_bar_trade_date
    ON jyhf_stock_daily_bar(trade_date);
