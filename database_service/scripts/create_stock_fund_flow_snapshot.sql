-- PR4.2.31a Stock Fund Flow Evidence
--
-- This table stores vendor-defined order-size fund-flow evidence. It must not
-- be interpreted as institution or hot-money identity.

CREATE TABLE IF NOT EXISTS stock_fund_flow_snapshot (
    trade_date DATE NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',

    net_inflow_yuan NUMERIC(20, 2),
    super_large_net_inflow_yuan NUMERIC(20, 2),
    large_net_inflow_yuan NUMERIC(20, 2),
    medium_net_inflow_yuan NUMERIC(20, 2),
    small_net_inflow_yuan NUMERIC(20, 2),

    source_name TEXT NOT NULL,
    source_endpoint TEXT NOT NULL DEFAULT '',
    source_version TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL DEFAULT 'DAILY',
    "window" TEXT NOT NULL DEFAULT '1D',
    market_scope TEXT NOT NULL DEFAULT 'CN_A',
    source_quality TEXT NOT NULL DEFAULT 'UNKNOWN',
    quality TEXT NOT NULL DEFAULT 'MISSING',
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, stock_code, source_name, source_endpoint, source_version, frequency, "window", market_scope)
);

ALTER TABLE stock_fund_flow_snapshot ADD COLUMN IF NOT EXISTS source_version TEXT NOT NULL DEFAULT '';
ALTER TABLE stock_fund_flow_snapshot ADD COLUMN IF NOT EXISTS frequency TEXT NOT NULL DEFAULT 'DAILY';
ALTER TABLE stock_fund_flow_snapshot ADD COLUMN IF NOT EXISTS "window" TEXT NOT NULL DEFAULT '1D';
ALTER TABLE stock_fund_flow_snapshot ADD COLUMN IF NOT EXISTS market_scope TEXT NOT NULL DEFAULT 'CN_A';

CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_snapshot_date
    ON stock_fund_flow_snapshot (trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_snapshot_net_inflow
    ON stock_fund_flow_snapshot (trade_date, net_inflow_yuan DESC);

CREATE INDEX IF NOT EXISTS idx_stock_fund_flow_snapshot_source
    ON stock_fund_flow_snapshot (source_name, source_endpoint, source_version, frequency, "window", market_scope);

CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_fund_flow_snapshot_identity
    ON stock_fund_flow_snapshot (
        trade_date, stock_code, source_name, source_endpoint,
        source_version, frequency, "window", market_scope
    );
