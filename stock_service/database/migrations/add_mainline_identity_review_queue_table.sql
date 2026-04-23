-- 主线身份复核队列表
-- 用途：承载 review_pending 样本，支持来源/优先级/状态审计与回放

CREATE TABLE IF NOT EXISTS mainline_identity_review_queue (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    subject_key VARCHAR(64) NOT NULL,
    theme_name VARCHAR(128),
    review_source VARCHAR(32) NOT NULL,
    review_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    priority_score NUMERIC(8,3) NOT NULL DEFAULT 0,
    trigger_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMP,
    UNIQUE (trade_date, subject_key, review_source)
);

CREATE INDEX IF NOT EXISTS idx_mainline_identity_review_queue_status
    ON mainline_identity_review_queue(trade_date, review_status, priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_mainline_identity_review_queue_subject
    ON mainline_identity_review_queue(subject_key, trade_date DESC);
