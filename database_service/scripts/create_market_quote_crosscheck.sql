-- P1-D: JYHF × TDX 双源行情交叉校验表

CREATE TABLE IF NOT EXISTS market_quote_crosscheck (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    ts              TIMESTAMPTZ(3) NOT NULL,
    stock_id        VARCHAR(12) NOT NULL,   -- 002361.SZ 系统格式

    -- 原始时间戳
    jyhf_ts         TIMESTAMPTZ(3),
    tdx_ts          TIMESTAMPTZ(3),

    -- 当前价
    jyhf_price      NUMERIC(12,4),
    tdx_price       NUMERIC(12,4),
    price_diff      NUMERIC(12,4),
    price_diff_pct  NUMERIC(10,6),

    -- 涨跌幅
    jyhf_pct_chg    NUMERIC(10,4),
    tdx_pct_chg     NUMERIC(10,4),
    pct_chg_diff    NUMERIC(10,4),

    -- 成交额
    jyhf_amount     NUMERIC(18,2),
    tdx_amount      NUMERIC(18,2),
    amount_diff_pct NUMERIC(10,6),

    -- 成交量
    jyhf_vol        NUMERIC(18,2),
    tdx_vol         NUMERIC(18,2),
    vol_diff_pct    NUMERIC(10,6),

    -- 延迟（秒）
    jyhf_delay_seconds  NUMERIC(10,2),
    tdx_delay_seconds   NUMERIC(10,2),

    -- 校验结果
    crosscheck_status   VARCHAR(20) NOT NULL,
    severity            VARCHAR(10) NOT NULL,
    reason              TEXT,
    raw_json            JSONB DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_market_crosscheck UNIQUE (trade_date, stock_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_market_crosscheck_stock_ts
    ON market_quote_crosscheck(stock_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_market_crosscheck_status_ts
    ON market_quote_crosscheck(crosscheck_status, ts DESC);
