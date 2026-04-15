-- 选股器数据库表结构

-- 选股策略表
CREATE TABLE IF NOT EXISTS stock_screening_strategy (
    strategy_id VARCHAR(64) PRIMARY KEY,
    strategy_name VARCHAR(128) NOT NULL,
    strategy_type VARCHAR(32) NOT NULL CHECK (strategy_type IN ('mainline', 'cycle', 'leader', 'technical', 'composite')),
    description TEXT,
    weight_config JSONB NOT NULL,
    filter_config JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT chk_weight_config CHECK (
        weight_config ? 'mainline' AND
        weight_config ? 'cycle' AND
        weight_config ? 'leader' AND
        weight_config ? 'technical'
    )
);

-- 选股执行记录表
CREATE TABLE IF NOT EXISTS stock_screening_execution (
    execution_id VARCHAR(64) PRIMARY KEY,
    strategy_id VARCHAR(64) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
    trade_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    total_stocks INTEGER DEFAULT 0,
    screened_stocks INTEGER DEFAULT 0,
    results_count INTEGER DEFAULT 0,
    execution_time_ms INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 选股结果表
CREATE TABLE IF NOT EXISTS stock_screening_result (
    result_id VARCHAR(64) PRIMARY KEY,
    strategy_id VARCHAR(64) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
    execution_id VARCHAR(64) NOT NULL REFERENCES stock_screening_execution(execution_id),
    trade_date DATE NOT NULL,
    stock_id VARCHAR(32) NOT NULL,
    stock_name VARCHAR(64),
    composite_score DECIMAL(5,2) NOT NULL CHECK (composite_score >= 0 AND composite_score <= 100),
    dimension_scores JSONB NOT NULL,
    rank_position INTEGER,
    screening_reason TEXT,
    theme_info JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_dimension_scores CHECK (
        dimension_scores ? 'mainline' AND
        dimension_scores ? 'cycle' AND
        dimension_scores ? 'leader' AND
        dimension_scores ? 'technical'
    )
);

-- 用户选股收藏表
CREATE TABLE IF NOT EXISTS user_stock_screening_favorite (
    favorite_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    result_id VARCHAR(64) NOT NULL REFERENCES stock_screening_result(result_id),
    notes TEXT,
    tags JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, result_id)
);

-- 二级索引（PostgreSQL 需独立创建）
CREATE INDEX IF NOT EXISTS idx_execution_strategy_date
ON stock_screening_execution (strategy_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_execution_status
ON stock_screening_execution (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_result_strategy_date
ON stock_screening_result (strategy_id, trade_date DESC, composite_score DESC);

CREATE INDEX IF NOT EXISTS idx_result_stock
ON stock_screening_result (stock_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_result_composite_score
ON stock_screening_result (composite_score DESC);

CREATE INDEX IF NOT EXISTS idx_result_execution
ON stock_screening_result (execution_id);

CREATE INDEX IF NOT EXISTS idx_favorite_user
ON user_stock_screening_favorite (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_favorite_result
ON user_stock_screening_favorite (result_id);

-- LLM复核表索引
CREATE INDEX IF NOT EXISTS idx_stock_screening_llm_review_result_id
ON stock_screening_llm_review(result_id);

CREATE INDEX IF NOT EXISTS idx_stock_screening_llm_review_exec
ON stock_screening_llm_review(execution_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_screening_llm_review_decision
ON stock_screening_llm_review(decision) WHERE decision IN ('pass', 'watch');

-- 插入默认策略
INSERT INTO stock_screening_strategy (
    strategy_id,
    strategy_name,
    strategy_type,
    description,
    weight_config,
    filter_config,
    created_by,
    is_active
) VALUES
(
    'default_composite',
    '综合选股策略',
    'composite',
    '基于35%/30%/20%/15%决策序列的默认综合选股策略',
    '{"mainline": 0.35, "cycle": 0.30, "leader": 0.20, "technical": 0.15}',
    '{"min_composite_score": 60, "min_mainline_score": 50, "min_cycle_score": 50, "min_leader_score": 40, "min_technical_score": 40}',
    'system',
    TRUE
),
(
    'mainline_focus',
    '主线题材策略',
    'mainline',
    '侧重主线题材判断的选股策略',
    '{"mainline": 0.60, "cycle": 0.20, "leader": 0.10, "technical": 0.10}',
    '{"min_composite_score": 65, "min_mainline_score": 70}',
    'system',
    TRUE
),
(
    'cycle_timing',
    '周期择时策略',
    'cycle',
    '侧重周期阶段判断的选股策略',
    '{"mainline": 0.20, "cycle": 0.60, "leader": 0.10, "technical": 0.10}',
    '{"min_composite_score": 65, "min_cycle_score": 70}',
    'system',
    TRUE
),
(
    'leader_following',
    '龙头跟随策略',
    'leader',
    '侧重龙头判断的选股策略',
    '{"mainline": 0.20, "cycle": 0.20, "leader": 0.50, "technical": 0.10}',
    '{"min_composite_score": 65, "min_leader_score": 70}',
    'system',
    TRUE
)
ON CONFLICT (strategy_id) DO NOTHING;

-- 创建视图：选股结果详情视图
CREATE OR REPLACE VIEW stock_screening_result_detail AS
SELECT
    r.result_id,
    r.strategy_id,
    s.strategy_name,
    r.trade_date,
    r.stock_id,
    r.stock_name,
    r.composite_score,
    r.dimension_scores->>'mainline' as mainline_score,
    r.dimension_scores->>'cycle' as cycle_score,
    r.dimension_scores->>'leader' as leader_score,
    r.dimension_scores->>'technical' as technical_score,
    r.rank_position,
    r.screening_reason,
    r.theme_info,
    r.created_at,
    e.status as execution_status,
    e.execution_time_ms
FROM stock_screening_result r
JOIN stock_screening_strategy s ON r.strategy_id = s.strategy_id
JOIN stock_screening_execution e ON r.execution_id = e.execution_id;

-- 选股LLM复核结果表
CREATE TABLE IF NOT EXISTS stock_screening_llm_review (
    review_id VARCHAR(64) PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL,
    strategy_id VARCHAR(64) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
    trade_date DATE NOT NULL,
    result_id VARCHAR(64) NOT NULL REFERENCES stock_screening_result(result_id),
    stock_id VARCHAR(32) NOT NULL,
    decision VARCHAR(16) NOT NULL CHECK (decision IN ('pass', 'watch', 'reject', 'failed')),
    llm_score DECIMAL(6,2),
    confidence DECIMAL(4,3),
    reasoning TEXT,
    risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_name VARCHAR(64),
    prompt_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 创建视图：用户收藏详情视图
CREATE OR REPLACE VIEW user_screening_favorite_detail AS
SELECT
    f.favorite_id,
    f.user_id,
    f.notes,
    f.tags,
    f.created_at as favorite_created_at,
    r.result_id,
    r.strategy_id,
    r.trade_date,
    r.stock_id,
    r.stock_name,
    r.composite_score,
    r.dimension_scores,
    r.rank_position,
    r.screening_reason,
    r.theme_info,
    r.created_at as result_created_at
FROM user_stock_screening_favorite f
JOIN stock_screening_result r ON f.result_id = r.result_id;

-- 创建函数：获取策略统计
CREATE OR REPLACE FUNCTION get_strategy_statistics(
    p_strategy_id VARCHAR DEFAULT NULL,
    p_date_from DATE DEFAULT NULL,
    p_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    total_results BIGINT,
    avg_composite_score DECIMAL,
    min_composite_score DECIMAL,
    max_composite_score DECIMAL,
    recent_trade_date DATE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) as total_results,
        AVG(r.composite_score) as avg_composite_score,
        MIN(r.composite_score) as min_composite_score,
        MAX(r.composite_score) as max_composite_score,
        MAX(r.trade_date) as recent_trade_date
    FROM stock_screening_result r
    WHERE
        (p_strategy_id IS NULL OR r.strategy_id = p_strategy_id)
        AND (p_date_from IS NULL OR r.trade_date >= p_date_from)
        AND (p_date_to IS NULL OR r.trade_date <= p_date_to);
END;
$$ LANGUAGE plpgsql;

-- 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_screening_result_theme_info
ON stock_screening_result USING gin (theme_info);

CREATE INDEX IF NOT EXISTS idx_screening_result_dimension_scores
ON stock_screening_result USING gin (dimension_scores);

CREATE INDEX IF NOT EXISTS idx_screening_strategy_active
ON stock_screening_strategy (is_active) WHERE is_active = TRUE;

-- 添加注释
COMMENT ON TABLE stock_screening_strategy IS '选股策略配置表';
COMMENT ON TABLE stock_screening_execution IS '选股执行记录表';
COMMENT ON TABLE stock_screening_result IS '选股结果表';
COMMENT ON TABLE user_stock_screening_favorite IS '用户选股收藏表';
COMMENT ON TABLE stock_screening_llm_review IS '选股LLM复核结果表';

COMMENT ON COLUMN stock_screening_strategy.weight_config IS '权重配置: {mainline: 0.35, cycle: 0.30, leader: 0.20, technical: 0.15}';
COMMENT ON COLUMN stock_screening_strategy.filter_config IS '筛选条件配置';
COMMENT ON COLUMN stock_screening_result.dimension_scores IS '各维度得分: {mainline: 85, cycle: 72, leader: 90, technical: 65}';
COMMENT ON COLUMN stock_screening_result.theme_info IS '题材信息: {subject_key: "xxx", theme_name: "xxx", ...}';
COMMENT ON COLUMN stock_screening_llm_review.decision IS '复核决策: pass/watch/reject/failed';
COMMENT ON COLUMN stock_screening_llm_review.confidence IS '置信度: 0-1';
COMMENT ON COLUMN stock_screening_llm_review.risk_flags IS '风险标记列表';
COMMENT ON COLUMN stock_screening_llm_review.evidence_refs IS '证据引用列表';
