-- P1-C+: 尾盘快照表
CREATE TABLE IF NOT EXISTS jyhf_tail_session_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    snapshot_time TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    watch_stock_count INT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, snapshot_time)
);
