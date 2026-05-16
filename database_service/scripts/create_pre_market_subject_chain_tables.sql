-- 盘前必读 subject_key 主链路写库表与报告快照表。
\i database_service/scripts/create_event_subject_map.sql

CREATE TABLE IF NOT EXISTS pre_market_brief_snapshot (
    trade_date date NOT NULL,
    snapshot_version varchar(100) NOT NULL DEFAULT 'pre_market_brief.v1',
    batch_id varchar(100),
    trace_id varchar(100),
    source_trace_id varchar(100),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_name varchar(100) NOT NULL DEFAULT 'pre_market_brief_builder',
    status varchar(20) NOT NULL DEFAULT 'draft',
    generated_at timestamptz,
    finalized_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, snapshot_version)
);

ALTER TABLE pre_market_brief_snapshot
ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'draft',
ADD COLUMN IF NOT EXISTS generated_at timestamptz,
ADD COLUMN IF NOT EXISTS finalized_at timestamptz,
ADD COLUMN IF NOT EXISTS source_trace_id varchar(100),
ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
