CREATE TABLE IF NOT EXISTS theme_profile_v2 (
    subject_key VARCHAR(80) PRIMARY KEY,
    subject_name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    entity_anchors JSONB NOT NULL DEFAULT '[]'::jsonb,
    domain_anchors JSONB NOT NULL DEFAULT '[]'::jsonb,
    product_anchors JSONB NOT NULL DEFAULT '[]'::jsonb,
    technology_anchors JSONB NOT NULL DEFAULT '[]'::jsonb,
    event_action_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    must_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    strong_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    should_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    support_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    weak_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    no_anchor_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    negative_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    confusion_subject_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    boundary_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    stock_pool_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_blocks JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    eval_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    generated_by VARCHAR(80) NOT NULL DEFAULT 'theme_profile_v2_builder',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_theme_profile_v2_status
ON theme_profile_v2(status);

CREATE INDEX IF NOT EXISTS idx_theme_profile_v2_quality_score
ON theme_profile_v2(quality_score DESC);

CREATE INDEX IF NOT EXISTS idx_theme_profile_v2_confusion_keys
ON theme_profile_v2 USING GIN(confusion_subject_keys);
