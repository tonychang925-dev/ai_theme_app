ALTER TABLE theme_cycle_judgement_v2
ADD COLUMN IF NOT EXISTS snapshot_version TEXT,
ADD COLUMN IF NOT EXISTS batch_id TEXT,
ADD COLUMN IF NOT EXISTS trace_id TEXT,
ADD COLUMN IF NOT EXISTS rule_version TEXT,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_theme_cycle_judgement_v2_snapshot
ON theme_cycle_judgement_v2 (trade_date, snapshot_version);

CREATE INDEX IF NOT EXISTS idx_theme_cycle_judgement_v2_batch_trace
ON theme_cycle_judgement_v2 (batch_id, trace_id);

COMMENT ON COLUMN theme_cycle_judgement_v2.snapshot_version IS 'Replay/build snapshot version that produced this cycle judgement row.';
COMMENT ON COLUMN theme_cycle_judgement_v2.batch_id IS 'Replay/build batch id for audit and matrix correlation.';
COMMENT ON COLUMN theme_cycle_judgement_v2.trace_id IS 'Replay/build trace id for end-to-end diagnostics.';
COMMENT ON COLUMN theme_cycle_judgement_v2.rule_version IS 'Subject cycle judgement rule version used by stock_processing_service.';
COMMENT ON COLUMN theme_cycle_judgement_v2.updated_at IS 'Last update timestamp for the judgement row.';
