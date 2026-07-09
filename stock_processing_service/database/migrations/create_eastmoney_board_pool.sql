-- M2.5: Eastmoney Board Pool daily snapshot (a-stock-data 打板层)
-- Stores 涨停池(ZT), 炸板池(ZB), 跌停池(DT), 昨涨停池(YZT) per trading day.
-- Data source: Eastmoney push2ex API

CREATE TABLE IF NOT EXISTS eastmoney_board_pool_daily (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    pool_type VARCHAR(8) NOT NULL,       -- ZT | ZB | DT | YZT
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    limit_days INTEGER DEFAULT 0,        -- 连板数 (lbc)
    pct NUMERIC(10,4),                   -- 涨跌幅%
    break_times INTEGER DEFAULT 0,       -- 炸板次数/开板次数 (zbc)
    seal_fund NUMERIC(18,2),             -- 封单资金 (fund)
    turnover NUMERIC(12,4),              -- 换手率% (hs)
    amount NUMERIC(18,2),                -- 成交额 (amount)
    industry VARCHAR(64),                -- 行业 (hybk)
    zt_stat VARCHAR(32),                 -- N天M板
    first_seal VARCHAR(16),              -- 首次封板时间 HH:MM:SS
    last_seal VARCHAR(16),               -- 最后封板时间
    raw_json JSONB DEFAULT '{}',         -- 原始API数据
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trade_date, pool_type, stock_code)
);

CREATE INDEX IF NOT EXISTS idx_embp_date_pool ON eastmoney_board_pool_daily (trade_date, pool_type);
CREATE INDEX IF NOT EXISTS idx_embp_stock ON eastmoney_board_pool_daily (stock_code, trade_date);
