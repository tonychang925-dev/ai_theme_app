-- M2.5 Phase 0.5: Metrics Validation Snapshot
-- Immutable daily snapshots for regression safety.
-- Every change to MarketMetrics calculators must pass validation against this table.

CREATE TABLE IF NOT EXISTS market_metrics_validation_snapshot (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT '1.1',
    snapshot_json JSONB NOT NULL,          -- frozen MarketMetricsSnapshot
    report_json JSONB NOT NULL DEFAULT '{}',  -- ValidationReport from comparison
    overall_status VARCHAR(32) NOT NULL DEFAULT 'pending',  -- ok / tolerable / review_required
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trade_date, version)
);

CREATE INDEX IF NOT EXISTS idx_mmvs_trade_date ON market_metrics_validation_snapshot (trade_date);
CREATE INDEX IF NOT EXISTS idx_mmvs_status ON market_metrics_validation_snapshot (overall_status);
