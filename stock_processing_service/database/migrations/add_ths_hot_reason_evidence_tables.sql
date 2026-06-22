-- THS hot reason evidence ingestion foundation.
-- Keeps raw source payloads replayable and separates source snapshots from theme evidence.

CREATE TABLE IF NOT EXISTS source_raw_snapshot (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(64) NOT NULL,
    endpoint_key VARCHAR(128) NOT NULL,
    trade_date DATE,
    request_url TEXT,
    request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_raw JSONB,
    response_text TEXT,
    response_hash VARCHAR(128) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_name, endpoint_key, trade_date, response_hash)
);

CREATE INDEX IF NOT EXISTS idx_source_raw_snapshot_source_endpoint_date
ON source_raw_snapshot (source_name, endpoint_key, trade_date);

CREATE TABLE IF NOT EXISTS market_data_source_registry (
    source_name VARCHAR(64) NOT NULL,
    endpoint_key VARCHAR(128) NOT NULL,
    domain VARCHAR(64) NOT NULL,
    owned_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    fallback_order INT NOT NULL DEFAULT 100,
    rate_limit_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    auth_type VARCHAR(32) NOT NULL DEFAULT 'none',
    freshness_sla VARCHAR(64),
    raw_snapshot_required BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    usage TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_name, endpoint_key)
);

INSERT INTO market_data_source_registry (
    source_name,
    endpoint_key,
    domain,
    owned_fields,
    fallback_order,
    rate_limit_policy,
    auth_type,
    freshness_sla,
    raw_snapshot_required,
    enabled,
    usage
) VALUES (
    'ths',
    'ths_hot_reason',
    'hot_reason',
    '["reason_raw", "reason_tags", "hot_stock_list"]'::jsonb,
    20,
    '{"policy": "simple", "min_interval_ms": 1000}'::jsonb,
    'none',
    'T+0 post-market',
    TRUE,
    TRUE,
    '盘后热点归因'
)
ON CONFLICT (source_name, endpoint_key) DO UPDATE SET
    owned_fields = EXCLUDED.owned_fields,
    fallback_order = EXCLUDED.fallback_order,
    rate_limit_policy = EXCLUDED.rate_limit_policy,
    freshness_sla = EXCLUDED.freshness_sla,
    raw_snapshot_required = EXCLUDED.raw_snapshot_required,
    enabled = EXCLUDED.enabled,
    usage = EXCLUDED.usage,
    updated_at = now();

CREATE TABLE IF NOT EXISTS ths_hot_reason_snapshot (
    trade_date DATE NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(128) NOT NULL,
    reason_raw TEXT NOT NULL,
    reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    close_price NUMERIC(18, 6),
    pct_chg NUMERIC(18, 6),
    turnover_rate NUMERIC(18, 6),
    amount NUMERIC(24, 6),
    volume NUMERIC(24, 6),
    big_order_net NUMERIC(18, 6),
    market INT,
    source_name VARCHAR(64) NOT NULL DEFAULT 'ths',
    source_trace_id VARCHAR(160) NOT NULL,
    raw_snapshot_id BIGINT REFERENCES source_raw_snapshot(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stock_code, source_name)
);

CREATE INDEX IF NOT EXISTS idx_ths_hot_reason_snapshot_date_theme
ON ths_hot_reason_snapshot (trade_date);

CREATE INDEX IF NOT EXISTS idx_ths_hot_reason_snapshot_tags
ON ths_hot_reason_snapshot USING GIN (reason_tags);

CREATE TABLE IF NOT EXISTS stock_theme_reason_evidence (
    trade_date DATE NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(128),
    theme_name VARCHAR(128) NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    evidence_text TEXT NOT NULL,
    reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_theme BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(8, 4) NOT NULL DEFAULT 0,
    source_trace_id VARCHAR(160),
    raw_snapshot_id BIGINT REFERENCES source_raw_snapshot(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stock_code, theme_name, source_name, evidence_text)
);

CREATE INDEX IF NOT EXISTS idx_stock_theme_reason_evidence_date_theme
ON stock_theme_reason_evidence (trade_date, theme_name);

CREATE INDEX IF NOT EXISTS idx_stock_theme_reason_evidence_stock
ON stock_theme_reason_evidence (trade_date, stock_code);

CREATE INDEX IF NOT EXISTS idx_stock_theme_reason_evidence_tags
ON stock_theme_reason_evidence USING GIN (reason_tags);

COMMENT ON TABLE source_raw_snapshot IS '外部行情/题材数据源原始响应快照，用于回放与排错';
COMMENT ON TABLE ths_hot_reason_snapshot IS '同花顺当日强势股及人工 reason tags 快照';
COMMENT ON TABLE stock_theme_reason_evidence IS '个股-题材归因证据表，供热点矩阵、热度评分和龙头分析复用';
