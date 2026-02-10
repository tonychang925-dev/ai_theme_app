-- 创建news_raw表

\c stock_data_test

-- 如果表已存在，先删除（仅用于测试）
DROP TABLE IF EXISTS news_raw CASCADE;

-- 创建news_raw表
CREATE TABLE news_raw (
    id BIGSERIAL PRIMARY KEY,
    news_id VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(100) NOT NULL,
    publish_date DATE NOT NULL,
    publish_time TIME,
    market VARCHAR(50),
    url VARCHAR(500),
    keywords JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_news_raw_news_id ON news_raw(news_id);
CREATE INDEX idx_news_raw_publish_date ON news_raw(publish_date DESC);
CREATE INDEX idx_news_raw_source ON news_raw(source);
CREATE INDEX idx_news_raw_created_at ON news_raw(created_at DESC);

-- 验证表结构
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'news_raw'
ORDER BY ordinal_position;

-- 测试插入数据
INSERT INTO news_raw (news_id, title, content, source, publish_date, market, keywords)
VALUES 
    ('test_001', '测试新闻标题1', '测试新闻内容1', 'test_source', '2024-01-20', 'A股', '["测试", "新闻"]'::jsonb),
    ('test_002', '测试新闻标题2', '测试新闻内容2', 'test_source', '2024-01-19', '港股', '["测试", "港股"]'::jsonb)
ON CONFLICT (news_id) DO NOTHING;

-- 查看数据
SELECT 
    news_id, 
    title, 
    source, 
    publish_date, 
    market, 
    created_at 
FROM news_raw 
ORDER BY created_at DESC;
