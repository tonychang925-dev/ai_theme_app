-- PR4.2.33a Institution Style Producer — Core Multi-Signal Model
--
-- institution_style_daily: per-theme daily institution capital preference score.
-- Computed from 4 signals: fund flow (35%), cycle (30%), stock structure (25%),
-- dragon tiger (10%). Market regime modifier is deferred to PR4.2.33b.
--
-- Every component score is individually observable for M7 calibration.
-- FORBIDDEN: single-signal inference, net_amount>0 → institution_style.

CREATE TABLE IF NOT EXISTS institution_style_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Composite scores
    institution_score       NUMERIC(6, 2),        -- 0-100 final score (base × regime, regime=1.0 in 33a)
    base_score              NUMERIC(6, 2),        -- 0-100 before regime modifier
    confidence              NUMERIC(5, 4),         -- 0.0000-1.0000
    market_regime_factor    NUMERIC(4, 3) NOT NULL DEFAULT 1.000,

    -- Component scores (individually observable for M7)
    flow_score              NUMERIC(6, 2),        -- S1: persistence+accel+large_ratio+consistency
    cycle_score             NUMERIC(6, 2),        -- S2: 7-stage cycle bonus
    structure_score         NUMERIC(6, 2),        -- S3: leader+core_stock+breadth
    dragon_tiger_score      NUMERIC(6, 2),        -- S4: seat quality + buy intensity (nullable)

    -- Lifecycle context (from theme_cycle_judgement_v2)
    lifecycle_stage         TEXT,                  -- START/INCUBATION/FERMENTATION/DIFFUSION/PEAK/DISTRIBUTION/DECAY

    -- Evidence per signal
    evidence_quality        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"flow": "HIGH"/"MEDIUM"/"LOW", "cycle": "...", "structure": "...", "dragon_tiger": "MISSING"/"LOW"/"MEDIUM"/"HIGH"}

    -- Supporting evidence detail (for AI explanation)
    evidence                JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"top_flow_stocks": [...], "cycle_reason": "...", "structure_reason": "...", "seat_detail": [...]}

    -- Top signals for explanation
    top_signals             TEXT[] NOT NULL DEFAULT '{}',

    -- Provenance
    model_version           TEXT NOT NULL DEFAULT 'institution_style_v1',
    source                  TEXT NOT NULL DEFAULT 'institution_style_producer',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, subject_key, model_version)
);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_institution_style_daily_date
    ON institution_style_daily (trade_date);

CREATE INDEX IF NOT EXISTS idx_institution_style_daily_score
    ON institution_style_daily (trade_date, institution_score DESC);

CREATE INDEX IF NOT EXISTS idx_institution_style_daily_theme
    ON institution_style_daily (subject_key, trade_date);
