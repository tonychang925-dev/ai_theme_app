-- Phase 6A: structured_intel_event 一手信息结构化事件表
-- 用于存储 LLM 结构化后的公告/研报/调研/财报事件，平级于 news_event 表
-- 目标数据库：stock_data_test（生产环境 / 写入库）
-- 执行方式：psql -h localhost -d stock_data_test -f create_structured_intel_event.sql

CREATE TABLE IF NOT EXISTS structured_intel_event (
    id                BIGSERIAL PRIMARY KEY,
    raw_doc_id        BIGINT       NOT NULL REFERENCES raw_intel_document(id),
    event_type        VARCHAR(64)  NOT NULL,                   -- major_contract / capex_expansion / mna_restructuring / shareholder_change / regulatory_penalty / management_change / dividend_plan / performance_forecast / research_report / institutional_survey / other
    event_subtype     VARCHAR(64),
    event_level       VARCHAR(32)  NOT NULL DEFAULT 'normal',  -- normal / important / critical
    stock_code        VARCHAR(32),
    stock_name        VARCHAR(128),
    subject_keys      TEXT[],                                  -- 可能关联的题材 subject_key 候选列表
    title             TEXT,
    summary           TEXT,
    event_date        DATE,
    publish_time      TIMESTAMPTZ,
    entities          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    financial_metrics JSONB        NOT NULL DEFAULT '{}'::jsonb,
    business_metrics  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    catalyst_tags     TEXT[],
    risk_tags         TEXT[],
    confidence        NUMERIC(5,4),
    impact_score      NUMERIC(5,2),
    urgency_score     NUMERIC(5,2),
    evidence_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    llm_model         VARCHAR(64),
    stream_status     VARCHAR(32)  NOT NULL DEFAULT 'pending', -- pending / produced / skipped / failed
    stream_message_id  VARCHAR(128),
    stream_produced_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

ALTER TABLE structured_intel_event
    ADD COLUMN IF NOT EXISTS stream_message_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS stream_produced_at TIMESTAMPTZ;

-- 索引
CREATE INDEX IF NOT EXISTS idx_sie_raw_doc
    ON structured_intel_event(raw_doc_id);

CREATE INDEX IF NOT EXISTS idx_sie_stock
    ON structured_intel_event(stock_code);

CREATE INDEX IF NOT EXISTS idx_sie_event_type
    ON structured_intel_event(event_type);

CREATE INDEX IF NOT EXISTS idx_sie_event_level
    ON structured_intel_event(event_level);

CREATE INDEX IF NOT EXISTS idx_sie_publish_time
    ON structured_intel_event(publish_time DESC);

CREATE INDEX IF NOT EXISTS idx_sie_stream_status
    ON structured_intel_event(stream_status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sie_raw_doc_model_event_unique
    ON structured_intel_event(raw_doc_id, COALESCE(llm_model, ''), event_type);

-- 验证表结构
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'structured_intel_event'
ORDER BY ordinal_position;

-- 验证外键约束
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_name = 'structured_intel_event';
