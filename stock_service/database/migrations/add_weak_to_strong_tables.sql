-- 弱转强两阶段系统表结构（P1/P2）

-- 盘后候选池
CREATE TABLE IF NOT EXISTS weak_to_strong_candidate_pool (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    next_trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),
    candidate_score NUMERIC(6,2) NOT NULL,
    candidate_type VARCHAR(32) NOT NULL,
    rule_version VARCHAR(64) NOT NULL,
    weak_type VARCHAR(32) NOT NULL,
    weak_intensity NUMERIC(6,2) NOT NULL,
    is_dragon_head BOOLEAN DEFAULT FALSE,
    dragon_head_level VARCHAR(16),
    prev_limit_up_count INT DEFAULT 0,
    max_consecutive_limit_up_days INT DEFAULT 0,
    support_type VARCHAR(32),
    support_level NUMERIC(12,3),
    support_strength NUMERIC(6,2) DEFAULT 0,
    expected_open_low NUMERIC(6,2),
    expected_open_high NUMERIC(6,2),
    expected_auction_pattern VARCHAR(32),
    need_last_minute_grab BOOLEAN DEFAULT TRUE,
    need_plate_follow BOOLEAN DEFAULT TRUE,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (next_trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_w2s_candidate_next_date_score
ON weak_to_strong_candidate_pool(next_trade_date, candidate_score DESC);

CREATE INDEX IF NOT EXISTS idx_w2s_candidate_trade_date
ON weak_to_strong_candidate_pool(trade_date);

CREATE INDEX IF NOT EXISTS idx_w2s_candidate_type
ON weak_to_strong_candidate_pool(candidate_type);

-- 盘前竞价确认信号
CREATE TABLE IF NOT EXISTS weak_to_strong_auction_signal (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    candidate_id BIGINT NOT NULL,
    auction_open_pct NUMERIC(6,2),
    auction_high_pct NUMERIC(6,2),
    auction_low_pct NUMERIC(6,2),
    auction_close_pct NUMERIC(6,2),
    auction_amount NUMERIC(20,2),
    auction_volume NUMERIC(20,2),
    auction_pattern VARCHAR(32),
    auction_pattern_score NUMERIC(6,2) DEFAULT 0,
    auction_stability_score NUMERIC(6,2) DEFAULT 0,
    last_minute_grab_score NUMERIC(6,2) DEFAULT 0,
    plate_follow_score NUMERIC(6,2) DEFAULT 0,
    risk_penalty NUMERIC(6,2) DEFAULT 0,
    confirmation_score NUMERIC(6,2) NOT NULL,
    signal_level VARCHAR(1) NOT NULL,
    decision VARCHAR(16) NOT NULL,
    data_status VARCHAR(16) NOT NULL DEFAULT 'ok',
    data_latency_ms INT DEFAULT 0,
    source_snapshot_id VARCHAR(64),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_w2s_auction_candidate
        FOREIGN KEY(candidate_id)
        REFERENCES weak_to_strong_candidate_pool(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_w2s_auction_trade_stock
ON weak_to_strong_auction_signal(trade_date, stock_id);

CREATE INDEX IF NOT EXISTS idx_w2s_auction_trade_level
ON weak_to_strong_auction_signal(trade_date, signal_level);

CREATE INDEX IF NOT EXISTS idx_w2s_auction_trade_stock
ON weak_to_strong_auction_signal(trade_date, stock_id);

CREATE INDEX IF NOT EXISTS idx_w2s_auction_candidate
ON weak_to_strong_auction_signal(candidate_id);
