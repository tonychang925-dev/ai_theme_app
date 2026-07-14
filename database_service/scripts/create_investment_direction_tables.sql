-- PR4.2.34a-1 Investment Direction Layer — Schema
--
-- Direction = unit of capital cognition (资金攻击方向的认知单位)
-- Theme    = unit of market classification (市场标签单位)
--
-- These layers co-exist at different abstraction levels.
-- Direction MUST NOT replace or obsolete Theme.
--
-- Event Catalyst can trigger Direction formation, not just Theme aggregation.

-- 1. Investment Direction definition
CREATE TABLE IF NOT EXISTS investment_direction (
    direction_key   TEXT PRIMARY KEY,        -- "AI_HIGH_SPEED_INTERCONNECT"
    direction_name  TEXT NOT NULL,           -- "AI高速互联"
    description     TEXT NOT NULL DEFAULT '',
    level           TEXT NOT NULL DEFAULT 'DIRECTION',  -- DIRECTION | MACRO_THEME
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    event_catalyst  TEXT,                    -- Future: event that triggered this direction
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Direction → Theme binding (with time dimension)
CREATE TABLE IF NOT EXISTS direction_theme_binding (
    direction_key   TEXT NOT NULL REFERENCES investment_direction(direction_key),
    subject_key     TEXT NOT NULL,
    theme_name      TEXT NOT NULL DEFAULT '',
    weight          NUMERIC(5, 4) NOT NULL,      -- 0.0000 ~ 1.0000, SUM ≤ 1.0 per direction per period
    role            TEXT NOT NULL DEFAULT 'SUPPORTING',  -- PRIMARY_DRIVER | SUPPORTING | OPTIONAL
    confidence      NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    source          TEXT NOT NULL DEFAULT 'manual',
    valid_from      DATE NOT NULL DEFAULT '2026-01-01',
    valid_to        DATE,                          -- NULL = currently active
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (direction_key, subject_key, valid_from)
);

-- 3. Double-counting guard: per-theme per-direction allocation
-- C10: SUM(allocated_amount per theme across directions) ≤ source_flow × 1.001
CREATE TABLE IF NOT EXISTS theme_direction_allocation_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    direction_key           TEXT NOT NULL,
    allocated_amount_yuan   NUMERIC(24, 2),
    allocation_weight       NUMERIC(5, 4) NOT NULL,
    source_flow_yuan        NUMERIC(24, 2),        -- original theme flow for audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, subject_key, direction_key)
);

-- 4. Aggregated direction-level capital flow
-- C12: Σ direction_flow + unallocated = Σ theme_flow (full capital closure)
CREATE TABLE IF NOT EXISTS direction_capital_flow_daily (
    trade_date              DATE NOT NULL,
    direction_key           TEXT NOT NULL,
    direction_name          TEXT NOT NULL DEFAULT '',

    -- Weighted aggregation from theme flows
    net_flow_yuan           NUMERIC(24, 2),
    large_flow_yuan         NUMERIC(24, 2),

    -- Flow semantics
    flow_type               TEXT NOT NULL DEFAULT 'ATTRIBUTED_DIRECTION_FLOW',

    -- Composition
    theme_count             INTEGER NOT NULL DEFAULT 0,
    attributed_theme_count  INTEGER NOT NULL DEFAULT 0,
    flow_coverage_ratio     NUMERIC(5, 4) NOT NULL DEFAULT 0.0,

    -- Attribution
    attribution_method      TEXT NOT NULL DEFAULT 'direction_weighted',
    source                  TEXT NOT NULL DEFAULT 'direction_capital_aggregator',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, direction_key)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_direction_theme_binding_direction
    ON direction_theme_binding (direction_key) WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_direction_theme_binding_subject
    ON direction_theme_binding (subject_key) WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_theme_direction_alloc_daily_date
    ON theme_direction_allocation_daily (trade_date);

CREATE INDEX IF NOT EXISTS idx_direction_capital_flow_daily_date
    ON direction_capital_flow_daily (trade_date);

CREATE INDEX IF NOT EXISTS idx_direction_capital_flow_daily_score
    ON direction_capital_flow_daily (trade_date, net_flow_yuan DESC);
