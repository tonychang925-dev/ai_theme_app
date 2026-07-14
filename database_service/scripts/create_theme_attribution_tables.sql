-- PR4.2.32a Theme Capital Attribution Foundation
--
-- stock_theme_attribution_daily: per-stock-per-theme weight allocation.
-- Weight sources: Level 1 identity_registry (PRIMARY/RELATED roles).
-- Constraint: SUM(weight) per stock per method ≤ 1.0 (application-enforced).
--
-- FORBIDDEN: institution_style, hot_money_style, main_force inference.
-- FORBIDDEN: AI-assigned weights (deferred to PR4.2.32b).

CREATE TABLE IF NOT EXISTS stock_theme_attribution_daily (
    trade_date          DATE NOT NULL,
    stock_code          TEXT NOT NULL,          -- e.g. "300223.SZ"
    subject_key         TEXT NOT NULL,          -- theme key
    theme_name          TEXT NOT NULL DEFAULT '',

    weight              NUMERIC(5, 4) NOT NULL, -- 0.0000 ~ 1.0000
    confidence          NUMERIC(5, 4) NOT NULL DEFAULT 1.0,

    method              TEXT NOT NULL,          -- "identity_registry"
    attribution_version TEXT NOT NULL DEFAULT 'identity_registry_v1',
    source              TEXT NOT NULL,          -- which table provided the binding

    diagnostics         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, stock_code, subject_key, attribution_version)
);

-- theme_capital_flow_daily: aggregated per-theme daily capital flow.
-- flow_type = ATTRIBUTED_ORDER_FLOW (weighted stock attribution, not raw theme money).
-- Must include coverage metrics for downstream intelligence confidence.

CREATE TABLE IF NOT EXISTS theme_capital_flow_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Weighted aggregation (元)
    net_flow_yuan           NUMERIC(24, 2),
    large_flow_yuan         NUMERIC(24, 2),

    -- Semantic: this is attributed order flow, not raw theme money
    flow_type               TEXT NOT NULL DEFAULT 'ATTRIBUTED_ORDER_FLOW',

    -- Composition + coverage
    stock_count             INTEGER NOT NULL DEFAULT 0,
    attributed_stock_count  INTEGER NOT NULL DEFAULT 0,
    positive_stock_count    INTEGER NOT NULL DEFAULT 0,
    flow_coverage_ratio     NUMERIC(5, 4) NOT NULL DEFAULT 0.0,

    -- Quality
    attribution_confidence  NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    attribution_method      TEXT NOT NULL,
    attribution_version     TEXT NOT NULL DEFAULT 'identity_registry_v1',

    source                  TEXT NOT NULL DEFAULT 'theme_capital_attribution_engine',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, subject_key, attribution_version)
);

-- unattributed_capital_daily: stocks with fund flow but NO theme bindings.
-- Preserved for future theme discovery / M7 analysis.
-- These funds existed — they just don't map to any known theme yet.

CREATE TABLE IF NOT EXISTS unattributed_capital_daily (
    trade_date          DATE NOT NULL,
    stock_code          TEXT NOT NULL,
    stock_name          TEXT NOT NULL DEFAULT '',

    net_flow_yuan       NUMERIC(24, 2),
    large_flow_yuan     NUMERIC(24, 2),

    reason              TEXT NOT NULL DEFAULT 'no_theme_binding',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, stock_code)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_attribution_daily_stock
    ON stock_theme_attribution_daily (trade_date, stock_code);

CREATE INDEX IF NOT EXISTS idx_attribution_daily_theme
    ON stock_theme_attribution_daily (trade_date, subject_key);

CREATE INDEX IF NOT EXISTS idx_theme_capital_flow_daily_theme
    ON theme_capital_flow_daily (trade_date, subject_key);

CREATE INDEX IF NOT EXISTS idx_unattributed_capital_daily
    ON unattributed_capital_daily (trade_date);
