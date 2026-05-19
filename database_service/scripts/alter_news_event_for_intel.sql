-- Phase 6A: news_event 兼容字段扩展
-- 新增 source_category / raw_intel_doc_id / structured_intel_event_id / source_trace_id
-- 使 intel 事件可写入 news_event，复用现有 ThemeProcessor / DecisionExecutor 后半段链路
-- 目标数据库：stock_data_test（生产环境 / 写入库）
-- 执行方式：psql -h localhost -d stock_data_test -f alter_news_event_for_intel.sql

ALTER TABLE news_event
    ADD COLUMN IF NOT EXISTS source_category VARCHAR(32) DEFAULT 'news',
    ADD COLUMN IF NOT EXISTS raw_intel_doc_id BIGINT,
    ADD COLUMN IF NOT EXISTS structured_intel_event_id BIGINT,
    ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(128);

-- 验证新增字段
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'news_event'
    AND column_name IN ('source_category', 'raw_intel_doc_id', 'structured_intel_event_id', 'source_trace_id')
ORDER BY ordinal_position;

-- 验证现有数据 source_category 默认值正确
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE source_category = 'news') AS news_rows,
    COUNT(*) FILTER (WHERE source_category IS NULL) AS null_rows
FROM news_event;
