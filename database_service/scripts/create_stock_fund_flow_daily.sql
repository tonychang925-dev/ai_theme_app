-- PR4.2.31f Tushare Stock Fund Flow Evidence (Daily)
--
-- Stores vendor-defined order-size fund-flow facts from Tushare moneyflow.
-- Tushare provides BUY/SELL direction per order-size bucket, which is a
-- richer evidence model than net-only sources.
--
-- ALL amount fields are in 元 (converted from Tushare 万元 at collection time).
-- Vol fields are in 手 (kept as-is from Tushare).
--
-- Forbidden: these fields must never be interpreted as institution/hot-money identity.
-- Semantic: vendor_defined order_size_flow, not_owner_identity.

CREATE TABLE IF NOT EXISTS stock_fund_flow_daily (
    trade_date              DATE NOT NULL,
    ts_code                 TEXT NOT NULL,    -- e.g. "300223.SZ"

    -- extra-large order bucket (特大单, >=100万/笔)
    buy_elg_amount_yuan     NUMERIC(20, 2),
    sell_elg_amount_yuan    NUMERIC(20, 2),
    buy_elg_vol_shou        NUMERIC(20, 2),
    sell_elg_vol_shou       NUMERIC(20, 2),

    -- large order bucket (大单, 20-100万/笔)
    buy_lg_amount_yuan      NUMERIC(20, 2),
    sell_lg_amount_yuan     NUMERIC(20, 2),
    buy_lg_vol_shou         NUMERIC(20, 2),
    sell_lg_vol_shou        NUMERIC(20, 2),

    -- medium order bucket (中单, 5-20万/笔)
    buy_md_amount_yuan      NUMERIC(20, 2),
    sell_md_amount_yuan     NUMERIC(20, 2),
    buy_md_vol_shou         NUMERIC(20, 2),
    sell_md_vol_shou        NUMERIC(20, 2),

    -- small order bucket (小单, <5万/笔)
    buy_sm_amount_yuan      NUMERIC(20, 2),
    sell_sm_amount_yuan     NUMERIC(20, 2),
    buy_sm_vol_shou         NUMERIC(20, 2),
    sell_sm_vol_shou        NUMERIC(20, 2),

    -- L2-based net flow (vendor-defined, do NOT recalculate from buckets)
    order_size_flow_amount_yuan  NUMERIC(20, 2),
    net_mf_vol_shou              NUMERIC(20, 2),

    -- source provenance (C6: M7 traceability)
    source_name             TEXT NOT NULL DEFAULT 'tushare',
    source_endpoint         TEXT NOT NULL DEFAULT 'moneyflow',
    source_version          TEXT NOT NULL DEFAULT 'v1',
    collected_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- semantic metadata (C5: order_size_flow, not_owner_identity)
    semantic_type           TEXT NOT NULL DEFAULT 'order_size_flow',
    not_owner_identity      BOOLEAN NOT NULL DEFAULT TRUE,

    -- evidence quality
    quality                 TEXT NOT NULL DEFAULT 'OK',
    diagnostics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_json                JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, ts_code, source_name, source_endpoint, source_version)
);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_daily_date
    ON stock_fund_flow_daily (trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_daily_ts_code
    ON stock_fund_flow_daily (ts_code, trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_daily_source
    ON stock_fund_flow_daily (source_name, source_version, collected_at);

-- Idempotency guard: same (trade_date, ts_code, source) → upsert
CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_fund_flow_daily_identity
    ON stock_fund_flow_daily (
        trade_date, ts_code, source_name, source_endpoint, source_version
    );
