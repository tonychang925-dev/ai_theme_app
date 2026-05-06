CREATE TABLE IF NOT EXISTS replay_snapshot_manifest (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    layer_name TEXT NOT NULL,
    snapshot_version TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    input_hash TEXT,
    output_hash TEXT,
    row_count INT DEFAULT 0,
    status TEXT NOT NULL,
    batch_id TEXT,
    trace_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (trade_date, layer_name, snapshot_version, algorithm_version)
);

CREATE INDEX IF NOT EXISTS idx_replay_snapshot_manifest_trade_date
    ON replay_snapshot_manifest (trade_date);

CREATE INDEX IF NOT EXISTS idx_replay_snapshot_manifest_layer_status
    ON replay_snapshot_manifest (layer_name, status);
