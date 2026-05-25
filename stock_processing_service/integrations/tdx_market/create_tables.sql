-- TDX 行情独立表（v2：stock_id=系统格式, api_stock_id=纯数字, source_channel）

-- 1. 实时行情快照（5档盘口）
CREATE TABLE IF NOT EXISTS tdx_stock_quote_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    ts              TIMESTAMPTZ(3) NOT NULL,
    stock_id        VARCHAR(12) NOT NULL,        -- 002361.SZ
    api_stock_id    VARCHAR(10) NOT NULL DEFAULT '', -- 002361
    price           NUMERIC(12,4),
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    last_close      NUMERIC(12,4),
    amount          NUMERIC(18,2),
    vol             NUMERIC(18,2),
    servertime      VARCHAR(20),
    bid1            NUMERIC(12,4),
    ask1            NUMERIC(12,4),
    bid_vol1        INTEGER,
    ask_vol1        INTEGER,
    bid2            NUMERIC(12,4),
    ask2            NUMERIC(12,4),
    bid_vol2        INTEGER,
    ask_vol2        INTEGER,
    bid3            NUMERIC(12,4),
    ask3            NUMERIC(12,4),
    bid_vol3        INTEGER,
    ask_vol3        INTEGER,
    bid4            NUMERIC(12,4),
    ask4            NUMERIC(12,4),
    bid_vol4        INTEGER,
    ask_vol4        INTEGER,
    bid5            NUMERIC(12,4),
    ask5            NUMERIC(12,4),
    bid_vol5        INTEGER,
    ask_vol5        INTEGER,
    source_channel  VARCHAR(32) NOT NULL DEFAULT 'tdx_market_agent',
    raw_json        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tdx_quote UNIQUE (trade_date, stock_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_tdx_quote_stock_ts ON tdx_stock_quote_snapshot(stock_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tdx_quote_trade_date ON tdx_stock_quote_snapshot(trade_date);

-- 2. 分时数据（按 minute_index，不伪造 timestamp）
CREATE TABLE IF NOT EXISTS tdx_stock_minute_bar (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    ts              TIMESTAMPTZ(3) NOT NULL,
    stock_id        VARCHAR(12) NOT NULL,        -- 002361.SZ
    api_stock_id    VARCHAR(10) NOT NULL DEFAULT '', -- 002361
    minute_index    INTEGER NOT NULL,
    price           NUMERIC(12,4),
    vol             NUMERIC(18,2),
    volume          NUMERIC(18,2),
    source_channel  VARCHAR(32) NOT NULL DEFAULT 'tdx_market_agent',
    raw_json        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tdx_minute UNIQUE (trade_date, stock_id, minute_index, ts)
);

CREATE INDEX IF NOT EXISTS idx_tdx_minute_stock ON tdx_stock_minute_bar(stock_id, trade_date, minute_index);

-- 3. 日线/K线
CREATE TABLE IF NOT EXISTS tdx_stock_daily_bar (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    ts              TIMESTAMPTZ(3) NOT NULL,
    stock_id        VARCHAR(12) NOT NULL,        -- 002361.SZ
    api_stock_id    VARCHAR(10) NOT NULL DEFAULT '', -- 002361
    bar_time        TIMESTAMPTZ(3),
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    close           NUMERIC(12,4),
    vol             NUMERIC(18,2),
    amount          NUMERIC(18,2),
    frequency       INTEGER NOT NULL DEFAULT 9,
    source_channel  VARCHAR(32) NOT NULL DEFAULT 'tdx_market_agent',
    raw_json        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tdx_daily_bar UNIQUE (stock_id, bar_time, frequency)
);

CREATE INDEX IF NOT EXISTS idx_tdx_daily_stock ON tdx_stock_daily_bar(stock_id, bar_time DESC);
