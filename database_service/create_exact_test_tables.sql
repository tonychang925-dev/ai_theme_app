\c stock_data_test;

-- 1. 创建theme_master表（完全匹配生产环境）
CREATE TABLE IF NOT EXISTS theme_master (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    code VARCHAR(80) UNIQUE NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    level1_category VARCHAR(80),
    level2_category VARCHAR(80),
    level3_category VARCHAR(80),
    category_path TEXT[],
    category1_code VARCHAR(50),
    category2_code VARCHAR(50),
    category3_code VARCHAR(50),
    tags JSONB DEFAULT '{}'::jsonb,
    theme_type VARCHAR(30) NOT NULL DEFAULT 'concept',
    heat_score INTEGER DEFAULT 50,
    confidence_score NUMERIC DEFAULT 0.80,
    lifecycle_stage VARCHAR(20) DEFAULT 'growth',
    related_stocks TEXT[] DEFAULT '{}',
    stock_count INTEGER DEFAULT 0,
    news_count INTEGER DEFAULT 0,
    mention_count INTEGER DEFAULT 0,
    last_mentioned TIMESTAMP,
    source_system VARCHAR(50) NOT NULL,
    source_id VARCHAR(100),
    created_by VARCHAR(50) DEFAULT 'system',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 创建news_raw表
CREATE TABLE IF NOT EXISTS news_raw (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    source VARCHAR(255),
    publish_time TIMESTAMP,
    market VARCHAR(50),
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    news_id TEXT UNIQUE NOT NULL,
    publish_date DATE,
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建news_event表
CREATE TABLE IF NOT EXISTS news_event (
    id SERIAL PRIMARY KEY,
    news_id INTEGER REFERENCES news_raw(id),
    event_type VARCHAR(100),
    impact_industries TEXT[],
    direction VARCHAR(50),
    confidence NUMERIC(5,2),
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    theme_directive JSONB DEFAULT '{}'::jsonb,
    theme_directive_processed BOOLEAN DEFAULT FALSE
);

-- 4. 创建event_theme_map表
CREATE TABLE IF NOT EXISTS event_theme_map (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES news_event(id),
    theme_id INTEGER REFERENCES theme_master(id),
    confidence NUMERIC(5,2),
    match_reason TEXT,
    matched_keywords TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, theme_id)
);

-- 5. 创建financial_categories表
CREATE TABLE IF NOT EXISTS financial_categories (
    id SERIAL PRIMARY KEY,
    category_code VARCHAR(50) UNIQUE NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    parent_code VARCHAR(50),
    level INTEGER NOT NULL,
    description TEXT,
    tags JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 插入测试数据
-- 插入一些金融分类
INSERT INTO financial_categories (category_code, category_name, level, description) VALUES
('TECH', '科技', 1, '科技相关主题'),
('CONSUMER', '消费', 1, '消费相关主题'),
('FINANCE', '金融', 1, '金融相关主题'),
('HEALTH', '医疗', 1, '医疗健康相关主题'),
('INDUSTRIAL', '工业', 1, '工业制造相关主题'),
('AI', '人工智能', 2, '人工智能技术', 'TECH'),
('EV', '新能源汽车', 2, '电动汽车产业链', 'INDUSTRIAL'),
('SEMI', '半导体', 2, '半导体芯片', 'TECH'),
('PHARMA', '生物医药', 2, '生物医药创新', 'HEALTH'),
('FINTECH', '金融科技', 2, '金融科技应用', 'FINANCE')
ON CONFLICT (category_code) DO NOTHING;

-- 插入一些主题数据
INSERT INTO theme_master (name, code, description, level1_category, category1_code, theme_type, heat_score, source_system) VALUES
('人工智能', 'AI_001', '人工智能技术主题', '科技', 'AI', 'concept', 95, 'test'),
('新能源汽车', 'NEV_001', '新能源汽车产业链', '工业', 'EV', 'concept', 88, 'test'),
('半导体', 'SEMI_001', '半导体芯片产业', '科技', 'SEMI', 'concept', 82, 'test'),
('生物医药', 'BIO_001', '生物医药创新主题', '医疗', 'PHARMA', 'concept', 75, 'test'),
('金融科技', 'FINTECH_001', '金融科技应用主题', '金融', 'FINTECH', 'concept', 70, 'test'),
('消费电子', 'CONSUMER_ELECTRONICS', '消费电子产品主题', '消费', 'CONSUMER', 'concept', 65, 'test'),
('碳中和', 'CARBON_NEUTRAL', '碳中和相关主题', '环保', 'ENV', 'concept', 78, 'test'),
('5G通信', '5G_COMMUNICATION', '5G通信技术主题', '通信', 'TELECOM', 'concept', 73, 'test')
ON CONFLICT (code) DO NOTHING;

-- 插入一些新闻数据
INSERT INTO news_raw (title, content, source, publish_time, news_id, publish_date) VALUES
('AI技术突破，带动芯片需求增长', '近日，某公司发布最新AI芯片，性能提升明显...', '证券时报', '2024-01-15 09:30:00', 'news_001_20240115', '2024-01-15'),
('新能源汽车销量创新高，产业链受益', '2024年1月，新能源汽车销量同比增长150%...', '中国证券报', '2024-01-15 10:15:00', 'news_002_20240115', '2024-01-15'),
('半导体行业景气度持续提升', '全球半导体市场需求旺盛，国内企业订单充足...', '电子时报', '2024-01-15 11:00:00', 'news_003_20240115', '2024-01-15'),
('创新药研发取得重要进展', '某医药公司宣布其创新药临床试验结果积极...', '医药经济报', '2024-01-15 13:45:00', 'news_004_20240115', '2024-01-15'),
('金融科技应用加速落地', '多家银行推出基于AI的风控系统...', '金融时报', '2024-01-15 14:30:00', 'news_005_20240115', '2024-01-15')
ON CONFLICT (news_id) DO NOTHING;

-- 创建所有必要的索引（匹配生产环境）
CREATE INDEX IF NOT EXISTS idx_theme_status ON theme_master(status);
CREATE INDEX IF NOT EXISTS idx_theme_created ON theme_master(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_theme_active ON theme_master(last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_theme_stocks ON theme_master USING gin(related_stocks);
CREATE INDEX IF NOT EXISTS idx_theme_cat1 ON theme_master(category1_code);
CREATE INDEX IF NOT EXISTS idx_theme_cat2 ON theme_master(category2_code);
CREATE INDEX IF NOT EXISTS idx_theme_cat3 ON theme_master(category3_code);
CREATE INDEX IF NOT EXISTS idx_theme_heat ON theme_master(heat_score DESC);
CREATE INDEX IF NOT EXISTS idx_news_raw_news_id ON news_raw(news_id);
CREATE INDEX IF NOT EXISTS idx_news_raw_publish_date ON news_raw(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_event_news_id ON news_event(news_id);
CREATE INDEX IF NOT EXISTS idx_event_theme_event_id ON event_theme_map(event_id);
CREATE INDEX IF NOT EXISTS idx_event_theme_theme_id ON event_theme_map(theme_id);
CREATE INDEX IF NOT EXISTS idx_category_parent ON financial_categories(parent_code);

-- 创建更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为theme_master表添加触发器
DROP TRIGGER IF EXISTS update_theme_master_updated_at ON theme_master;
CREATE TRIGGER update_theme_master_updated_at 
    BEFORE UPDATE ON theme_master 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- 为financial_categories表添加触发器
DROP TRIGGER IF EXISTS update_financial_categories_updated_at ON financial_categories;
CREATE TRIGGER update_financial_categories_updated_at 
    BEFORE UPDATE ON financial_categories 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- 查看所有表和数据统计
SELECT 
    'theme_master' as table_name,
    COUNT(*) as row_count
FROM theme_master
UNION ALL
SELECT 'news_raw', COUNT(*) FROM news_raw
UNION ALL
SELECT 'news_event', COUNT(*) FROM news_event
UNION ALL
SELECT 'event_theme_map', COUNT(*) FROM event_theme_map
UNION ALL
SELECT 'financial_categories', COUNT(*) FROM financial_categories
ORDER BY table_name;

-- 显示表结构信息
SELECT 
    table_name,
    COUNT(*) as column_count,
    string_agg(column_name, ', ' ORDER BY ordinal_position) as columns_preview
FROM information_schema.columns 
WHERE table_schema = 'public'
AND table_name IN ('theme_master', 'news_raw', 'news_event')
GROUP BY table_name
ORDER BY table_name;
