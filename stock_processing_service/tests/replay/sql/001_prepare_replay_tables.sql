-- Replay strict-mode test schema bootstrap (stock_data_test only)
-- This script is intended for test database usage.

BEGIN;

-- Ensure subject context query contract is satisfiable in replay strict mode.
ALTER TABLE IF EXISTS subject_stock_daily_snapshot
    ADD COLUMN IF NOT EXISTS subject_name text;

CREATE TABLE IF NOT EXISTS stock_abnormal_event (
    trade_date date NOT NULL,
    stock_id text NOT NULL,
    event_type text NOT NULL,
    event_score numeric(12,4),
    evidence_rules jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_version text,
    batch_id text,
    trace_id text,
    source_trace_id text,
    source_name text NOT NULL DEFAULT 'stock_processing_service',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, stock_id, event_type)
);

CREATE TABLE IF NOT EXISTS theme_stock_leaderboard (
    trade_date date NOT NULL,
    subject_key text NOT NULL,
    stock_id text NOT NULL,
    leaderboard_rank integer NOT NULL,
    leader_score numeric(12,4),
    score_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_version text,
    batch_id text,
    trace_id text,
    source_trace_id text,
    role_name text,
    source_name text NOT NULL DEFAULT 'stock_processing_service',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, subject_key, stock_id)
);

CREATE TABLE IF NOT EXISTS post_market_recap_snapshot (
    trade_date date PRIMARY KEY,
    snapshot_version text NOT NULL,
    batch_id text,
    trace_id text,
    source_trace_id text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_name text NOT NULL DEFAULT 'stock_processing_service',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pre_market_brief_snapshot (
    trade_date date PRIMARY KEY,
    snapshot_version text NOT NULL,
    batch_id text,
    trace_id text,
    source_trace_id text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_name text NOT NULL DEFAULT 'stock_processing_service',
    status varchar(20) NOT NULL DEFAULT 'draft',
    generated_at timestamptz,
    finalized_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_abnormal_event_trade_date
    ON stock_abnormal_event (trade_date);
CREATE INDEX IF NOT EXISTS idx_theme_stock_leaderboard_trade_date_subject
    ON theme_stock_leaderboard (trade_date, subject_key);
CREATE INDEX IF NOT EXISTS idx_post_market_recap_snapshot_trade_date
    ON post_market_recap_snapshot (trade_date);
CREATE INDEX IF NOT EXISTS idx_pre_market_brief_snapshot_trade_date
    ON pre_market_brief_snapshot (trade_date);

COMMIT;
