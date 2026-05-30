"""PR-9A: Create mainline_review_queue and mainline_registry tables.

Usage: python -m stock_processing_service.tests.contract.v2_8_create_mainline_registry_tables
       or execute SQL directly against stock_data_test.
"""
import asyncio
import asyncpg


DDL = """
-- PR-9A: Mainline Review Queue (machine candidates for human review)
CREATE TABLE IF NOT EXISTS mainline_review_queue (
    review_id           TEXT PRIMARY KEY,
    trade_date          DATE NOT NULL,

    subject_key         TEXT NOT NULL,
    theme_name          TEXT,

    mainline_id         TEXT,
    mainline_name       TEXT,

    machine_state       TEXT NOT NULL,
    final_mainline_state TEXT DEFAULT 'pending_review',

    mainline_type       TEXT,
    confirmation_path   TEXT,
    trigger_mode        TEXT,

    review_reason       TEXT,
    review_priority     NUMERIC,
    review_status       TEXT NOT NULL DEFAULT 'pending',
    suggested_human_decision TEXT,

    scores_json         JSONB DEFAULT '{}'::jsonb,
    evidence_json       JSONB DEFAULT '{}'::jsonb,
    risk_flags_json     JSONB DEFAULT '{}'::jsonb,
    diagnostics_json    JSONB DEFAULT '{}'::jsonb,

    human_decision      TEXT,
    human_reviewer      TEXT,
    human_notes         TEXT,
    reviewed_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mlrq_trade_date ON mainline_review_queue (trade_date);
CREATE INDEX IF NOT EXISTS idx_mlrq_subject_key ON mainline_review_queue (subject_key);
CREATE INDEX IF NOT EXISTS idx_mlrq_review_status ON mainline_review_queue (review_status);


-- PR-9A: Mainline Registry (human-confirmed mainlines)
CREATE TABLE IF NOT EXISTS mainline_registry (
    mainline_id             TEXT PRIMARY KEY,
    mainline_name           TEXT NOT NULL,

    canonical_subject_key   TEXT NOT NULL,
    mainline_type           TEXT,
    confirmation_path       TEXT,
    trigger_mode            TEXT,

    identity_status         TEXT NOT NULL,
    valid_from              DATE NOT NULL,
    valid_to                DATE,

    source_review_id        TEXT,

    core_subject_keys_json      JSONB DEFAULT '[]'::jsonb,
    branch_subject_keys_json    JSONB DEFAULT '[]'::jsonb,
    related_subject_keys_json   JSONB DEFAULT '[]'::jsonb,

    human_reviewer          TEXT,
    human_notes             TEXT,

    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mlr_canonical_sk ON mainline_registry (canonical_subject_key);
CREATE INDEX IF NOT EXISTS idx_mlr_identity_status ON mainline_registry (identity_status);
CREATE INDEX IF NOT EXISTS idx_mlr_valid_from ON mainline_registry (valid_from);
"""


async def run(dsn: str = "postgresql://localhost/stock_data_test") -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(DDL)
        print("mainline_review_queue + mainline_registry created/verified")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
