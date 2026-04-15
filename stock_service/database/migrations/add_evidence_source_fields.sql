-- 证据源字段扩展迁移脚本
-- P0阶段：补齐四层证据所需源表字段
-- 执行顺序：在 add_theme_cycle_v2_tables.sql 之后执行

-- 1. 扩展 theme_mainline_judgement 表 - 事件层证据增强
ALTER TABLE theme_mainline_judgement
ADD COLUMN IF NOT EXISTS event_count_3d INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS event_count_7d INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS strong_event_count_7d INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS event_recency_days INT;

COMMENT ON COLUMN theme_mainline_judgement.event_count_3d IS '近3日事件数量';
COMMENT ON COLUMN theme_mainline_judgement.event_count_7d IS '近7日事件数量';
COMMENT ON COLUMN theme_mainline_judgement.strong_event_count_7d IS '7日内强事件数量';
COMMENT ON COLUMN theme_mainline_judgement.event_recency_days IS '最近事件天数（NULL表示无事件）';

-- 2. 扩展 theme_cycle_judgement 表 - 龙头与板块结构证据增强
ALTER TABLE theme_cycle_judgement
ADD COLUMN IF NOT EXISTS leader_stock_id VARCHAR(16),
ADD COLUMN IF NOT EXISTS leader_stock_name VARCHAR(64),
ADD COLUMN IF NOT EXISTS board_stock_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS limit_down_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS red_ratio NUMERIC(8,3) DEFAULT 0,
ADD COLUMN IF NOT EXISTS big_drop_ratio NUMERIC(8,3) DEFAULT 0,
ADD COLUMN IF NOT EXISTS front_row_strength_score NUMERIC(8,3) DEFAULT 0,
ADD COLUMN IF NOT EXISTS relay_strength_score NUMERIC(8,3) DEFAULT 0,
ADD COLUMN IF NOT EXISTS front_row_survival_ratio NUMERIC(8,3) DEFAULT 0;

COMMENT ON COLUMN theme_cycle_judgement.leader_stock_id IS '龙头股票代码';
COMMENT ON COLUMN theme_cycle_judgement.leader_stock_name IS '龙头股票名称';
COMMENT ON COLUMN theme_cycle_judgement.board_stock_count IS '板块成分股数量';
COMMENT ON COLUMN theme_cycle_judgement.limit_down_count IS '跌停数量';
COMMENT ON COLUMN theme_cycle_judgement.red_ratio IS '红盘比例（0-1）';
COMMENT ON COLUMN theme_cycle_judgement.big_drop_ratio IS '大跌比例（-5%以上，0-1）';
COMMENT ON COLUMN theme_cycle_judgement.front_row_strength_score IS '前排强度评分（0-100）';
COMMENT ON COLUMN theme_cycle_judgement.relay_strength_score IS '接力强度评分（0-100）';
COMMENT ON COLUMN theme_cycle_judgement.front_row_survival_ratio IS '前排存活率（0-1）';

-- 3. 为新增字段创建索引（提升查询性能）
CREATE INDEX IF NOT EXISTS idx_tmj_event_counts
ON theme_mainline_judgement(event_count_7d DESC, strong_event_count_7d DESC);

CREATE INDEX IF NOT EXISTS idx_tcj_leader
ON theme_cycle_judgement(leader_stock_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_tcj_board_structure
ON theme_cycle_judgement(limit_down_count, red_ratio, big_drop_ratio);

-- 4. 更新现有记录的字段值（初始填充）
-- 注意：这里需要后续的数据聚合服务来实际计算这些值
-- 此迁移仅创建字段结构，数据填充由专用服务完成

-- 5. 验证字段添加成功
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    -- 检查 theme_mainline_judgement 新增字段
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'theme_mainline_judgement'
      AND column_name IN ('event_count_3d', 'event_count_7d', 'strong_event_count_7d', 'event_recency_days');

    RAISE NOTICE 'theme_mainline_judgement: 成功添加 % 个事件层字段', col_count;

    -- 检查 theme_cycle_judgement 新增字段
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'theme_cycle_judgement'
      AND column_name IN ('leader_stock_id', 'leader_stock_name', 'board_stock_count',
                         'limit_down_count', 'red_ratio', 'big_drop_ratio',
                         'front_row_strength_score', 'relay_strength_score', 'front_row_survival_ratio');

    RAISE NOTICE 'theme_cycle_judgement: 成功添加 % 个龙头/结构层字段', col_count;
END $$;