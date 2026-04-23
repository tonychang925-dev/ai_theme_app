-- 强势股持续跟踪观察池（Phase 1）
-- 目标语义：
-- 1) strong_stock_watch_pool = 当前活动池（每只股票最多1条活动记录）
-- 2) strong_stock_watch_history = 每日快照轨迹

CREATE TABLE IF NOT EXISTS strong_stock_watch_pool (
    id BIGSERIAL PRIMARY KEY,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_start_date DATE NOT NULL,
    last_trade_date DATE NOT NULL,
    watch_window_days INT NOT NULL DEFAULT 1,

    source_tag VARCHAR(32) NOT NULL,
    relay_role VARCHAR(32) NOT NULL DEFAULT 'unknown',
    watch_status VARCHAR(32) NOT NULL DEFAULT 'active',
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,

    pool_entry_type VARCHAR(16) NOT NULL DEFAULT 'observe_only',
    candidate_promoted BOOLEAN NOT NULL DEFAULT FALSE,

    cycle_state VARCHAR(32),
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch BOOLEAN NOT NULL DEFAULT FALSE,
    fade_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    support_type VARCHAR(32),
    support_level NUMERIC(12,3),
    support_score NUMERIC(6,2) DEFAULT 0,

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- 兼容旧表结构：如果历史上有 trade_date 列，则将其回填到 last_trade_date
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='strong_stock_watch_pool' AND column_name='trade_date'
    ) THEN
        EXECUTE '
            UPDATE strong_stock_watch_pool
            SET last_trade_date = COALESCE(last_trade_date, trade_date)
            WHERE last_trade_date IS NULL
        ';
    END IF;
END $$;

-- 兼容旧唯一约束：删除 (trade_date, stock_id) 唯一约束，切到 stock_id 唯一
DO $$
DECLARE
    c RECORD;
BEGIN
    FOR c IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'strong_stock_watch_pool'::regclass
          AND contype = 'u'
          AND pg_get_constraintdef(oid) ILIKE '%trade_date%stock_id%'
    LOOP
        EXECUTE format('ALTER TABLE strong_stock_watch_pool DROP CONSTRAINT IF EXISTS %I', c.conname);
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_strong_stock_watch_pool_stock
    ON strong_stock_watch_pool (stock_id);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_status
    ON strong_stock_watch_pool (watch_status, watch_score DESC, watch_priority DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_theme
    ON strong_stock_watch_pool (subject_key, last_trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_updated_at
    ON strong_stock_watch_pool (updated_at DESC);


CREATE TABLE IF NOT EXISTS strong_stock_watch_history (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_status VARCHAR(32) NOT NULL,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,

    relay_role VARCHAR(32) NOT NULL DEFAULT 'unknown',
    pool_entry_type VARCHAR(16) NOT NULL DEFAULT 'observe_only',
    cycle_state VARCHAR(32),
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch BOOLEAN NOT NULL DEFAULT FALSE,
    fade_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    promoted_to_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    removed_reason VARCHAR(128),

    support_type VARCHAR(32),
    support_level NUMERIC(12,3),
    support_score NUMERIC(6,2) DEFAULT 0,

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_stock
    ON strong_stock_watch_history (stock_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_theme
    ON strong_stock_watch_history (subject_key, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_status
    ON strong_stock_watch_history (trade_date, watch_status);
