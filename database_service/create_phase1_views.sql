-- P2.phase1 视图优先实现
-- 目标：
-- 1. 固定 subject_key 业务主键基线，theme_id 仅作为 L3 实体引用
-- 2. 提供 rank/detail/history/tree/stocks 的候选视图
-- 3. 仅在确有版本冻结/审计/性能需求时再沉淀 serving 表

BEGIN;

CREATE TABLE IF NOT EXISTS subject_node_staging (
    id BIGSERIAL PRIMARY KEY,
    subject_key VARCHAR(80) NOT NULL,
    subject_name VARCHAR(150) NOT NULL,
    node_level INTEGER,
    parent_subject_key VARCHAR(80),
    ancestors TEXT,
    reason TEXT,
    first_letter VARCHAR(32),
    importance INTEGER,
    sort INTEGER,
    pct_chg NUMERIC(8,4),
    status VARCHAR(20),
    source_type VARCHAR(50) DEFAULT 'jyhf_full_theme_list',
    raw_json JSONB,
    ingest_batch_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_subject_node_staging UNIQUE (subject_key)
);

CREATE INDEX IF NOT EXISTS idx_sns_parent ON subject_node_staging(parent_subject_key);
CREATE INDEX IF NOT EXISTS idx_sns_level ON subject_node_staging(node_level);

CREATE TABLE IF NOT EXISTS theme_hierarchy_staging (
    id BIGSERIAL PRIMARY KEY,
    parent_subject_key VARCHAR(80) NOT NULL,
    child_subject_key VARCHAR(80) NOT NULL,
    child_name VARCHAR(150),
    source_type VARCHAR(50) DEFAULT 'jyhf_hierarchy',
    ingest_batch_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_theme_hierarchy_staging UNIQUE (parent_subject_key, child_subject_key)
);

CREATE INDEX IF NOT EXISTS idx_ths_parent ON theme_hierarchy_staging(parent_subject_key);
CREATE INDEX IF NOT EXISTS idx_ths_child ON theme_hierarchy_staging(child_subject_key);

CREATE OR REPLACE VIEW vw_subject_theme_binding AS
SELECT
    sns.subject_key,
    tm.id AS theme_id,
    COALESCE(tm.name, sns.subject_name) AS theme_name,
    COALESCE(sns.node_level::VARCHAR(10), 'L1') AS node_level,
    'subject_node_staging'::VARCHAR(50) AS source_table,
    COALESCE(tm.source_system, 'jyhf') AS source_system,
    COALESCE(tm.source_id, sns.subject_key) AS source_id,
    sns.parent_subject_key,
    sns.ancestors,
    CASE
        WHEN tm.id IS NOT NULL AND tm.status = 'active' THEN 'active_binding'
        WHEN tm.id IS NOT NULL THEN 'inactive_binding'
        ELSE 'staging_only'
    END AS binding_status,
    COALESCE(tm.updated_at, sns.updated_at) AS last_verified_at
FROM subject_node_staging sns
LEFT JOIN theme_master tm
  ON tm.source_system = 'jyhf'
 AND tm.source_id = sns.subject_key

UNION ALL

SELECT
    tm.source_id AS subject_key,
    tm.id AS theme_id,
    tm.name AS theme_name,
    'L3'::VARCHAR(10) AS node_level,
    'theme_master'::VARCHAR(50) AS source_table,
    tm.source_system,
    tm.source_id,
    NULL::VARCHAR(80) AS parent_subject_key,
    NULL::TEXT AS ancestors,
    CASE
        WHEN tm.status = 'active' THEN 'active_binding'
        ELSE 'inactive_binding'
    END AS binding_status,
    tm.updated_at AS last_verified_at
FROM theme_master tm
WHERE tm.source_system = 'jyhf'
  AND tm.source_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM subject_node_staging sns
      WHERE sns.subject_key = tm.source_id
  );

CREATE OR REPLACE VIEW vw_theme_rank_current AS
WITH ranked AS (
    SELECT
        srd.*,
        ROW_NUMBER() OVER (
            PARTITION BY srd.subject_key
            ORDER BY srd.rank_date DESC, srd.id DESC
        ) AS rn
    FROM subject_rank_daily srd
)
SELECT
    r.subject_key,
    b.theme_id,
    b.theme_name,
    r.rank_date,
    r.heat,
    r.heat_name,
    r.pct_chg,
    r.his_pct_chg,
    r.red,
    r.description,
    r.source_system
FROM ranked r
LEFT JOIN vw_subject_theme_binding b
  ON b.subject_key = r.subject_key
WHERE r.rn = 1;

CREATE OR REPLACE VIEW vw_theme_detail_joined AS
SELECT
    b.subject_key,
    b.theme_id,
    COALESCE(tm.name, b.theme_name) AS theme_name,
    tpe.summary,
    sd.detail_html,
    sd.reason_short,
    sd.detail_version,
    sd.is_current,
    sd.updated_at AS detail_updated_at
FROM vw_subject_theme_binding b
LEFT JOIN theme_master tm
  ON tm.id = b.theme_id
LEFT JOIN theme_profile_ext tpe
  ON tpe.subject_key = b.subject_key
LEFT JOIN subject_detail sd
  ON sd.subject_key = b.subject_key
 AND COALESCE(sd.is_current, TRUE) = TRUE;

CREATE OR REPLACE VIEW vw_theme_stock_map_candidate AS
SELECT
    ssm.subject_key,
    b.theme_id,
    b.theme_name,
    ssm.stock_id,
    COALESCE(ssm.stock_name, s.stock_name, s2.name) AS stock_name,
    ssm.relation_type_candidate,
    ssm.top,
    ssm.sort,
    ssm.reason,
    ssm.remark,
    ssm.confidence,
    ssm.source_type,
    ssm.evidence_json,
    s.detail_html,
    s.remark AS stock_remark,
    s.price,
    s.pct_chg,
    CASE
        WHEN ssm.source_type = 'jyhf_stock_list' THEN 'pool'
        WHEN ssm.source_type IN ('jyhf_children', 'jyhf_children_leader') THEN 'leader_overlay'
        ELSE 'other'
    END AS mapping_scope
FROM subject_stock_staging ssm
LEFT JOIN vw_subject_theme_binding b
  ON b.subject_key = ssm.subject_key
LEFT JOIN subject_stock_detail_staging s
  ON s.stock_id = ssm.stock_id
LEFT JOIN stocks s2
  ON s2.stock_id = ssm.stock_id;

CREATE OR REPLACE VIEW vw_theme_tree_candidate AS
SELECT
    th.parent_subject_key,
    pb.theme_id AS parent_theme_id,
    pb.theme_name AS parent_theme_name,
    th.child_subject_key,
    cb.theme_id AS child_theme_id,
    COALESCE(cb.theme_name, th.child_name) AS child_name,
    'parent_child' AS relation_type,
    th.source_type,
    NULL::NUMERIC(8,4) AS pct_chg,
    NULL::INTEGER AS stock_count,
    NULL::INTEGER AS limit_up_count,
    NULL::VARCHAR(20) AS lead_stock_id,
    NULL::VARCHAR(100) AS lead_stock_name,
    NULL::INTEGER AS depth
FROM theme_hierarchy_staging th
LEFT JOIN vw_subject_theme_binding pb
  ON pb.subject_key = th.parent_subject_key
LEFT JOIN vw_subject_theme_binding cb
  ON cb.subject_key = th.child_subject_key

UNION ALL

SELECT
    scs.parent_subject_key,
    pb.theme_id AS parent_theme_id,
    pb.theme_name AS parent_theme_name,
    scs.child_subject_key,
    cb.theme_id AS child_theme_id,
    COALESCE(cb.theme_name, scs.child_name) AS child_name,
    'children_snapshot' AS relation_type,
    scs.source_type,
    scs.pct_chg,
    scs.stock_count,
    scs.limit_up_count,
    scs.lead_stock_id,
    scs.lead_stock_name,
    scs.depth
FROM subject_children_staging scs
LEFT JOIN vw_subject_theme_binding pb
  ON pb.subject_key = scs.parent_subject_key
LEFT JOIN vw_subject_theme_binding cb
  ON cb.subject_key = scs.child_subject_key;

CREATE OR REPLACE VIEW vw_theme_history_candidate AS
SELECT
    srd.subject_key,
    b.theme_id,
    b.theme_name,
    NULL::BIGINT AS subject_rank_id,
    srd.rank_date,
    srd.description,
    srd.heat,
    srd.heat_name,
    srd.pct_chg,
    srd.his_pct_chg,
    NULL::INTEGER AS event_id,
    'jyhf_rank_daily' AS source_type,
    srd.id::TEXT AS source_ref
FROM subject_rank_daily srd
LEFT JOIN vw_subject_theme_binding b
  ON b.subject_key = srd.subject_key
WHERE srd.source_system IS DISTINCT FROM 'snapshot_agg'

UNION ALL

SELECT
    shs.subject_key,
    b.theme_id,
    b.theme_name,
    shs.subject_rank_id,
    shs.rank_date,
    shs.description,
    shs.heat,
    shs.heat_name,
    shs.pct_chg,
    shs.his_pct_chg,
    NULL::INTEGER AS event_id,
    shs.source_type,
    COALESCE(shs.subject_rank_id::TEXT, shs.id::TEXT) AS source_ref
FROM subject_history_staging shs
LEFT JOIN vw_subject_theme_binding b
  ON b.subject_key = shs.subject_key

UNION ALL

SELECT
    tm.source_id AS subject_key,
    etm.theme_id,
    tm.name AS theme_name,
    NULL::BIGINT AS subject_rank_id,
    ne.event_time::DATE AS rank_date,
    ne.summary AS description,
    NULL::INTEGER AS heat,
    NULL::VARCHAR(50) AS heat_name,
    NULL::NUMERIC(8,4) AS pct_chg,
    NULL::NUMERIC(8,4) AS his_pct_chg,
    ne.id AS event_id,
    'event_theme_map' AS source_type,
    ne.id::TEXT AS source_ref
FROM event_theme_map etm
JOIN news_event ne
  ON ne.id = etm.event_id
JOIN theme_master tm
  ON tm.id = etm.theme_id
WHERE tm.source_system = 'jyhf'
  AND tm.source_id IS NOT NULL

UNION ALL

SELECT
    esm.subject_key,
    COALESCE(b.theme_id, tm.id) AS theme_id,
    COALESCE(b.theme_name, tm.name) AS theme_name,
    NULL::BIGINT AS subject_rank_id,
    COALESCE(ne.event_time::date, ne.created_at::date, esm.created_at::date) AS rank_date,
    COALESCE(NULLIF(ne.summary, ''), '') AS description,
    NULL::INTEGER AS heat,
    NULL::VARCHAR(50) AS heat_name,
    NULL::NUMERIC(8,4) AS pct_chg,
    NULL::NUMERIC(8,4) AS his_pct_chg,
    ne.id AS event_id,
    'event_subject_map' AS source_type,
    ne.id::TEXT AS source_ref
FROM event_subject_map esm
JOIN news_event ne
  ON ne.id = esm.event_id
LEFT JOIN vw_subject_theme_binding b
  ON b.subject_key = esm.subject_key
LEFT JOIN theme_master tm
  ON tm.source_system = 'jyhf'
 AND tm.source_id = esm.subject_key
WHERE NULLIF(ne.summary, '') IS NOT NULL;

COMMIT;
