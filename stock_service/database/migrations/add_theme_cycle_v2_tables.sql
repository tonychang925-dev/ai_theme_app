-- 主线周期判定V2系统表结构
-- P0协议层：新增证据表、判定表、候选池扩展字段

-- 1. theme_cycle_evidence_daily - 存放原始证据与规则基础分
CREATE TABLE IF NOT EXISTS theme_cycle_evidence_daily (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    subject_key VARCHAR(64) NOT NULL,
    theme_name VARCHAR(128),

    -- 事件层
    event_count_3d INT DEFAULT 0,
    event_count_7d INT DEFAULT 0,
    strong_event_count_7d INT DEFAULT 0,
    event_recency_days INT,
    event_continuity_score NUMERIC(8,3) DEFAULT 0,  -- 精度调整：NUMERIC(8,3)
    event_strength_score NUMERIC(8,3) DEFAULT 0,    -- 精度调整：NUMERIC(8,3)

    -- 龙头/接力层
    leader_stock_id VARCHAR(16),
    leader_stock_name VARCHAR(64),
    leader_alive_score NUMERIC(8,3) DEFAULT 0,      -- 精度调整：NUMERIC(8,3)
    leader_breakdown_flag BOOLEAN DEFAULT FALSE,
    relay_strength_score NUMERIC(8,3) DEFAULT 0,    -- 精度调整：NUMERIC(8,3)
    front_row_survival_ratio NUMERIC(8,3) DEFAULT 0,

    -- 板块结构层
    board_stock_count INT DEFAULT 0,
    limit_up_count INT DEFAULT 0,
    limit_down_count INT DEFAULT 0,
    red_ratio NUMERIC(8,3) DEFAULT 0,
    big_drop_ratio NUMERIC(8,3) DEFAULT 0,
    front_row_strength_score NUMERIC(8,3) DEFAULT 0,

    -- 板块K线技术层
    theme_ret_3d NUMERIC(8,3),
    theme_ret_5d NUMERIC(8,3),
    theme_ret_10d NUMERIC(8,3),
    above_ma5 BOOLEAN,
    above_ma10 BOOLEAN,
    above_ma20 BOOLEAN,
    break_start_pivot BOOLEAN DEFAULT FALSE,
    volume_breakdown_flag BOOLEAN DEFAULT FALSE,
    theme_support_score NUMERIC(8,3) DEFAULT 0,

    -- 时间窗口字段（便于理解数据范围）
    lookback_days INT DEFAULT 7,
    evidence_window_start DATE,
    evidence_window_end DATE,

    -- 证据来源明细
    event_evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    leader_evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    board_structure_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    theme_kline_refs JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 汇总
    mainline_strength_score NUMERIC(8,3) DEFAULT 0,
    fade_risk_score NUMERIC(8,3) DEFAULT 0,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_schema_version VARCHAR(64) NOT NULL DEFAULT 'theme_cycle_evidence_schema.v1',
    source_version VARCHAR(64) NOT NULL DEFAULT 'theme_cycle_evidence.v1',
    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, subject_key)
);

-- 索引优化策略
CREATE INDEX IF NOT EXISTS idx_evidence_trade_subject
ON theme_cycle_evidence_daily(trade_date, subject_key);

CREATE INDEX IF NOT EXISTS idx_evidence_strength_composite
ON theme_cycle_evidence_daily(trade_date, mainline_strength_score DESC, fade_risk_score ASC);

-- 2. theme_cycle_judgement_v2 - 存放规则层、LLM复核与最终裁决
CREATE TABLE IF NOT EXISTS theme_cycle_judgement_v2 (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    subject_key VARCHAR(64) NOT NULL,
    theme_name VARCHAR(128),

    -- 规则层输出
    cycle_state_rule VARCHAR(32) NOT NULL,
    mainline_alive_rule BOOLEAN NOT NULL DEFAULT FALSE,

    -- LLM复核输出
    cycle_state_llm VARCHAR(32),
    mainline_alive_llm BOOLEAN,

    -- 最终裁决
    final_cycle_state VARCHAR(32) NOT NULL,
    final_mainline_alive BOOLEAN NOT NULL DEFAULT FALSE,

    -- 退潮状态细分
    fade_watch BOOLEAN NOT NULL DEFAULT FALSE,
    fade_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    -- 评分字段
    mainline_strength_score NUMERIC(8,3) DEFAULT 0,
    fade_risk_score NUMERIC(8,3) DEFAULT 0,
    fade_watch_score NUMERIC(8,3) DEFAULT 0,
    fade_confirmed_score NUMERIC(8,3) DEFAULT 0,
    divergence_score NUMERIC(8,3) DEFAULT 0,
    repair_score NUMERIC(8,3) DEFAULT 0,
    confidence_score NUMERIC(8,3) DEFAULT 0,

    -- 状态转换追踪（补充字段）
    previous_cycle_state VARCHAR(32),
    state_transition_reason VARCHAR(256),

    -- 解释字段
    rule_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    llm_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 版本控制
    judgement_schema_version VARCHAR(64) NOT NULL DEFAULT 'theme_cycle_judgement.v2',
    state_machine_version VARCHAR(64) NOT NULL DEFAULT 'state_machine.v1',
    llm_prompt_version VARCHAR(64),
    source_version VARCHAR(64) NOT NULL DEFAULT 'theme_cycle_judgement.v2',
    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, subject_key)
);

-- 核心查询索引
CREATE INDEX IF NOT EXISTS idx_judgement_state
ON theme_cycle_judgement_v2(trade_date, final_cycle_state);

CREATE INDEX IF NOT EXISTS idx_judgement_fade
ON theme_cycle_judgement_v2(trade_date, fade_confirmed, fade_watch);

CREATE INDEX IF NOT EXISTS idx_judgement_mainline
ON theme_cycle_judgement_v2(trade_date, final_mainline_alive);

-- 3. 候选池联动字段扩展（增量）
ALTER TABLE weak_to_strong_candidate_pool
ADD COLUMN IF NOT EXISTS cycle_state VARCHAR(32),
ADD COLUMN IF NOT EXISTS mainline_strength_score NUMERIC(8,3) DEFAULT 0,
ADD COLUMN IF NOT EXISTS fade_watch BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS fade_confirmed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS pool_entry_type VARCHAR(16) DEFAULT 'formal',
ADD COLUMN IF NOT EXISTS judgement_id BIGINT,
ADD COLUMN IF NOT EXISTS cycle_rule_version VARCHAR(64);

-- 候选池查询索引优化
CREATE INDEX IF NOT EXISTS idx_candidate_pool_entry_type
ON weak_to_strong_candidate_pool(pool_entry_type);

CREATE INDEX IF NOT EXISTS idx_candidate_fade_state
ON weak_to_strong_candidate_pool(fade_confirmed, fade_watch);

-- 4. 现有主线周期表字段扩展（向后兼容）
ALTER TABLE theme_cycle_judgement
ADD COLUMN IF NOT EXISTS fade_watch BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS fade_confirmed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS previous_cycle_state VARCHAR(32),
ADD COLUMN IF NOT EXISTS state_transition_reason VARCHAR(256);

-- 注释说明
COMMENT ON TABLE theme_cycle_evidence_daily IS '主线周期判定V2证据表 - 存放原始证据与规则基础分，不直接做最终结论';
COMMENT ON TABLE theme_cycle_judgement_v2 IS '主线周期判定V2裁决表 - 存放规则层、LLM复核与最终裁决，支持状态机追踪';
COMMENT ON COLUMN weak_to_strong_candidate_pool.pool_entry_type IS '候选池进入类型：formal（正式候选）, observe_only（观察流）, reject（拒绝）';