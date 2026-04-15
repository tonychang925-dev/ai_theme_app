-- 待人工复核事件队列表（实时链路禁止自动建题材时使用）
CREATE TABLE IF NOT EXISTS event_review_queue (
  id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL UNIQUE REFERENCES news_event(id) ON DELETE CASCADE,
  review_status VARCHAR(20) NOT NULL DEFAULT 'waiting',
  proposed_theme_name VARCHAR(200),
  proposed_theme_confidence NUMERIC(6,4),
  reason TEXT,
  source_channel VARCHAR(32) NOT NULL DEFAULT 'realtime_news',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  reviewed_by VARCHAR(100),
  reviewed_at TIMESTAMP,
  review_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_event_review_queue_status_created
ON event_review_queue(review_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_event_review_queue_source_created
ON event_review_queue(source_channel, created_at DESC);
