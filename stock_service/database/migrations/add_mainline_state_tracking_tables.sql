-- 主线状态快照与迁移监控表
-- 版本: mainline_state_tracking.v1

CREATE TABLE IF NOT EXISTS mainline_state_daily (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    subject_key VARCHAR(64) NOT NULL,
    theme_name VARCHAR(128),

    -- 主状态（严格复用 final_cycle_state）
    state VARCHAR(32) NOT NULL,
    state_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    is_mainline BOOLEAN NOT NULL DEFAULT FALSE,

    -- 评分明细
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch_score NUMERIC(6,2) DEFAULT 0,
    fade_confirmed_score NUMERIC(6,2) DEFAULT 0,
    divergence_score NUMERIC(6,2) DEFAULT 0,
    repair_score NUMERIC(6,2) DEFAULT 0,

    -- 解释与追踪
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_verdict JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_reason TEXT,
    decision_path JSONB NOT NULL DEFAULT '[]'::jsonb,

    source_version VARCHAR(64) NOT NULL DEFAULT 'mainline_state_daily.v1',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, subject_key)
);

CREATE INDEX IF NOT EXISTS idx_mainline_state_daily_trade_date
    ON mainline_state_daily (trade_date);

CREATE INDEX IF NOT EXISTS idx_mainline_state_daily_state
    ON mainline_state_daily (trade_date, state);

CREATE INDEX IF NOT EXISTS idx_mainline_state_daily_mainline
    ON mainline_state_daily (trade_date, is_mainline, state_score DESC);


CREATE TABLE IF NOT EXISTS mainline_state_transition (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    subject_key VARCHAR(64) NOT NULL,
    theme_name VARCHAR(128),

    -- 迁移语义（非主状态）
    from_state VARCHAR(32),
    to_state VARCHAR(32) NOT NULL,
    transition_type VARCHAR(16) NOT NULL,

    from_score NUMERIC(6,2) DEFAULT 0,
    to_score NUMERIC(6,2) DEFAULT 0,
    confidence NUMERIC(6,2) DEFAULT 0,

    trigger_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    source_version VARCHAR(64) NOT NULL DEFAULT 'mainline_state_transition.v1',
    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, subject_key)
);

CREATE INDEX IF NOT EXISTS idx_mainline_state_transition_trade_date
    ON mainline_state_transition (trade_date);

CREATE INDEX IF NOT EXISTS idx_mainline_state_transition_type
    ON mainline_state_transition (trade_date, transition_type);

CREATE INDEX IF NOT EXISTS idx_mainline_state_transition_states
    ON mainline_state_transition (from_state, to_state);

-- 可选约束（按当前库规范按需启用）
-- ALTER TABLE mainline_state_daily
--   ADD CONSTRAINT chk_mainline_state_daily_state
--   CHECK (state IN ('start','fermentation','acceleration','divergence','repair','fade_watch','fade_confirmed'));
--
-- ALTER TABLE mainline_state_transition
--   ADD CONSTRAINT chk_mainline_state_transition_type
--   CHECK (transition_type IN ('flat','upgrade','downgrade','fade'));
