CREATE TABLE IF NOT EXISTS event_subject_map (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL,
    news_id BIGINT,
    subject_key VARCHAR(64) NOT NULL,
    subject_name TEXT,
    confidence NUMERIC(8,4),
    relation_type VARCHAR(32) NOT NULL DEFAULT 'primary',
    match_reason TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(64) NOT NULL DEFAULT 'structured_theme_match',
    source_trace_id VARCHAR(128),
    run_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(event_id, subject_key, relation_type)
);

ALTER TABLE event_subject_map
ADD COLUMN IF NOT EXISTS news_id BIGINT,
ADD COLUMN IF NOT EXISTS subject_name TEXT,
ADD COLUMN IF NOT EXISTS match_reason TEXT,
ADD COLUMN IF NOT EXISTS source VARCHAR(64) NOT NULL DEFAULT 'structured_theme_match',
ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(128),
ADD COLUMN IF NOT EXISTS run_id VARCHAR(128),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE event_subject_map
ALTER COLUMN subject_name TYPE TEXT,
ALTER COLUMN confidence TYPE NUMERIC(8,4) USING confidence::numeric(8,4);

CREATE INDEX IF NOT EXISTS idx_event_subject_map_event_id
ON event_subject_map(event_id);

CREATE INDEX IF NOT EXISTS idx_event_subject_map_subject_key
ON event_subject_map(subject_key);

CREATE INDEX IF NOT EXISTS idx_event_subject_map_run_id
ON event_subject_map(run_id);
