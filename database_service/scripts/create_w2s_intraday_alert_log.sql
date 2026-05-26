-- P1-I-4d: v1/v2/v2.1 影子运行告警日志表
-- 每次盘中检测同时记录三个版本的评分，供盘后复盘统计

DROP TABLE IF EXISTS w2s_intraday_alert_log CASCADE;
CREATE TABLE w2s_intraday_alert_log (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    minute_ts TIMESTAMPTZ NOT NULL,
    candidate_id BIGINT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT DEFAULT '',
    theme_name TEXT DEFAULT '',
    candidate_type TEXT DEFAULT '',
    weak_type TEXT DEFAULT '',

    -- v1/v2/v2.1 并行评分
    v1_score NUMERIC(6,2),
    v1_level TEXT,                -- A/B/C
    v2_score NUMERIC(6,2),
    v2_level TEXT,                -- turn_strong/early_turn/observe
    v21_score NUMERIC(6,2),
    v21_level TEXT,               -- turn_strong/early_turn/observe

    -- 核心诊断指标
    current NUMERIC(12,4),
    vwap NUMERIC(12,4),
    distance_to_vwap_pct NUMERIC(6,2),
    relative_strength_vs_index NUMERIC(10,4),
    relative_strength_cross_zero BOOLEAN DEFAULT FALSE,
    relative_strength_slope_5m NUMERIC(10,4),
    above_vwap_ratio_5m NUMERIC(6,4),
    above_vwap_cross_up BOOLEAN DEFAULT FALSE,
    amount_acceleration BOOLEAN DEFAULT FALSE,
    price_momentum_3m NUMERIC(10,4),
    signal_price_position_30m NUMERIC(6,4),
    break_platform_30m BOOLEAN DEFAULT FALSE,
    chase_risk_penalty NUMERIC(6,2) DEFAULT 0,
    false_break_penalty NUMERIC(6,2) DEFAULT 0,

    -- 未来收益 (回测填充)
    ret_5m NUMERIC(10,4),
    ret_10m NUMERIC(10,4),
    ret_30m NUMERIC(10,4),
    ret_60m NUMERIC(10,4),
    max_drawdown_after_signal NUMERIC(6,2),

    -- 完整 payload
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_w2s_intraday_alert_log_trade
    ON w2s_intraday_alert_log(trade_date, v21_level);
CREATE INDEX IF NOT EXISTS idx_w2s_intraday_alert_log_stock
    ON w2s_intraday_alert_log(stock_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_w2s_intraday_alert_log_minute
    ON w2s_intraday_alert_log(trade_date, minute_ts);
