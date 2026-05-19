-- Phase 6A: raw_intel_document 一手信息原始文档表
-- 用于存储公告、研报、调研、财报等原始文档，与 news_raw 表平级
-- 目标数据库：stock_data_test（生产环境 / 写入库）
-- 执行方式：psql -h localhost -d stock_data_test -f create_raw_intel_document.sql

CREATE TABLE IF NOT EXISTS raw_intel_document (
    id              BIGSERIAL PRIMARY KEY,
    source_system   VARCHAR(64)  NOT NULL,                      -- cninfo / sse / szse / akshare_cninfo / akshare_a_notice / eastmoney
    source_type     VARCHAR(64)  NOT NULL,                      -- announcement / research_report / financial_report / survey / performance_forecast / earnings_express
    source_id       VARCHAR(256) NOT NULL,                      -- 原始公告ID 或 URL hash
    source_url      TEXT,
    publish_time    TIMESTAMPTZ,
    fetch_time      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    market          VARCHAR(32),
    stock_code      VARCHAR(32),
    stock_name      VARCHAR(128),
    company_name    VARCHAR(256),
    title           TEXT,
    content_text    TEXT,
    content_html    TEXT,
    pdf_url         TEXT,
    pdf_path        TEXT,
    doc_type        VARCHAR(64),
    doc_subtype     VARCHAR(64),
    announcement_type VARCHAR(64),
    report_period   VARCHAR(32),
    checksum        VARCHAR(128),
    dedupe_key      VARCHAR(256),
    parse_status    VARCHAR(32)  NOT NULL DEFAULT 'raw',        -- raw / parsed / pdf_downloaded / ocr_done
    llm_status      VARCHAR(32)  NOT NULL DEFAULT 'pending',    -- pending / processing / done / skipped / failed
    stream_status   VARCHAR(32)  NOT NULL DEFAULT 'pending',    -- pending / produced / skipped / failed
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- (source_system, source_id) 唯一性约束，保证同一来源的同一文档不重复
    CONSTRAINT uq_raw_intel_doc_source UNIQUE (source_system, source_id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_dedupe
    ON raw_intel_document(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_publish_time
    ON raw_intel_document(publish_time DESC);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_stock
    ON raw_intel_document(stock_code);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_parse_status
    ON raw_intel_document(parse_status);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_llm_status
    ON raw_intel_document(llm_status);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_stream_status
    ON raw_intel_document(stream_status);

-- 验证表结构
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'raw_intel_document'
ORDER BY ordinal_position;
