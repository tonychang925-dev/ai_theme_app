-- P1-I-4a: 盘中弱转强观察告警日志表 (审计/复盘用)

CREATE TABLE IF NOT EXISTS w2s_intraday_alert_log (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    candidate_id BIGINT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT DEFAULT '',
    alert_level TEXT NOT NULL,       -- A / B / C
    intraday_score NUMERIC(6,2),
    severity TEXT,
    item_type TEXT,

    current NUMERIC(12,4),
    vwap NUMERIC(12,4),
    above_vwap_ratio_5m NUMERIC(6,4),
    relative_strength_vs_index NUMERIC(10,4),
    break_platform_30m BOOLEAN DEFAULT FALSE,

    latest_minute_ts TIMESTAMPTZ,
    data_delay_seconds INT DEFAULT 0,
    vwap_unit_suspect BOOLEAN DEFAULT FALSE,

    score_breakdown JSONB DEFAULT '{}',
    evidence_rules JSONB DEFAULT '[]',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_w2s_intraday_alert_log_trade
    ON w2s_intraday_alert_log(trade_date, alert_level);
CREATE INDEX IF NOT EXISTS idx_w2s_intraday_alert_log_stock
    ON w2s_intraday_alert_log(stock_id, trade_date DESC);
