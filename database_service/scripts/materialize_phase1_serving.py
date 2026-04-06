#!/usr/bin/env python3
"""
物化 P2.phase1 四张 serving 表：
- theme_detail_snapshot
- theme_history_event
- theme_tree_relation
- theme_stock_map
"""

import asyncio
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_detail_snapshot (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        theme_id INTEGER,
        theme_name VARCHAR(150),
        snapshot_version INTEGER NOT NULL,
        summary TEXT,
        detail_html TEXT,
        reason_short TEXT,
        detail_version INTEGER,
        is_current BOOLEAN DEFAULT TRUE,
        source_type VARCHAR(50) NOT NULL,
        source_ref TEXT NOT NULL,
        snapshot_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_detail_snapshot UNIQUE (subject_key, snapshot_version)
    );
    CREATE INDEX IF NOT EXISTS idx_tds_subject_key ON theme_detail_snapshot(subject_key);
    CREATE INDEX IF NOT EXISTS idx_tds_theme_id ON theme_detail_snapshot(theme_id);
    CREATE INDEX IF NOT EXISTS idx_tds_current ON theme_detail_snapshot(subject_key, is_current);

    CREATE TABLE IF NOT EXISTS theme_history_event (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        theme_id INTEGER,
        theme_name VARCHAR(150),
        subject_rank_id BIGINT,
        event_id INTEGER,
        rank_date DATE,
        driver_summary TEXT,
        description TEXT,
        heat INTEGER,
        heat_name VARCHAR(50),
        pct_chg NUMERIC(8,4),
        his_pct_chg NUMERIC(8,4),
        source_type VARCHAR(50) NOT NULL,
        source_ref TEXT NOT NULL,
        trace_id VARCHAR(120),
        evidence_json JSONB,
        effective_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_history_event UNIQUE (subject_key, source_type, source_ref)
    );
    CREATE INDEX IF NOT EXISTS idx_the_subject_key ON theme_history_event(subject_key, rank_date DESC);
    CREATE INDEX IF NOT EXISTS idx_the_theme_id ON theme_history_event(theme_id, rank_date DESC);
    CREATE INDEX IF NOT EXISTS idx_the_event_id ON theme_history_event(event_id);

    CREATE TABLE IF NOT EXISTS theme_tree_relation (
        id BIGSERIAL PRIMARY KEY,
        parent_subject_key VARCHAR(80) NOT NULL,
        parent_theme_id INTEGER,
        parent_theme_name VARCHAR(150),
        child_subject_key VARCHAR(80) NOT NULL,
        child_theme_id INTEGER,
        child_name VARCHAR(150),
        relation_type VARCHAR(40) NOT NULL,
        evidence_source VARCHAR(50) NOT NULL,
        source_type VARCHAR(50) NOT NULL,
        pct_chg NUMERIC(8,4),
        stock_count INTEGER,
        limit_up_count INTEGER,
        lead_stock_id VARCHAR(20),
        lead_stock_name VARCHAR(100),
        depth INTEGER,
        evidence_json JSONB,
        effective_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_tree_relation UNIQUE (
            parent_subject_key, child_subject_key, relation_type, source_type
        )
    );
    CREATE INDEX IF NOT EXISTS idx_ttr_parent ON theme_tree_relation(parent_subject_key);
    CREATE INDEX IF NOT EXISTS idx_ttr_child ON theme_tree_relation(child_subject_key);

    CREATE TABLE IF NOT EXISTS theme_stock_map (
        id BIGSERIAL PRIMARY KEY,
        subject_key VARCHAR(80) NOT NULL,
        theme_id INTEGER,
        theme_name VARCHAR(150),
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        relation_type VARCHAR(20) NOT NULL,
        evidence_source VARCHAR(50) NOT NULL,
        confidence NUMERIC(4,2),
        source_type VARCHAR(50) NOT NULL,
        reason TEXT,
        remark TEXT,
        evidence_json JSONB,
        effective_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_stock_map UNIQUE (subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tsm_subject ON theme_stock_map(subject_key);
    CREATE INDEX IF NOT EXISTS idx_tsm_stock ON theme_stock_map(stock_id);
    CREATE INDEX IF NOT EXISTS idx_tsm_theme_id ON theme_stock_map(theme_id);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def materialize_detail_snapshot(manager: PostgresDatabaseManager) -> None:
    sql = """
    INSERT INTO theme_detail_snapshot (
        subject_key, theme_id, theme_name, snapshot_version, summary,
        detail_html, reason_short, detail_version, is_current,
        source_type, source_ref, snapshot_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        COALESCE(detail_version, 1) AS snapshot_version,
        summary,
        detail_html,
        reason_short,
        detail_version,
        COALESCE(is_current, TRUE) AS is_current,
        'subject_detail' AS source_type,
        ('subject_detail:' || subject_key || ':' || COALESCE(detail_version, 1)::text) AS source_ref,
        COALESCE(detail_updated_at, NOW()) AS snapshot_at
    FROM vw_theme_detail_joined
    WHERE detail_html IS NOT NULL OR summary IS NOT NULL OR reason_short IS NOT NULL
    ON CONFLICT (subject_key, snapshot_version)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        summary = EXCLUDED.summary,
        detail_html = EXCLUDED.detail_html,
        reason_short = EXCLUDED.reason_short,
        detail_version = EXCLUDED.detail_version,
        is_current = EXCLUDED.is_current,
        source_type = EXCLUDED.source_type,
        source_ref = EXCLUDED.source_ref,
        snapshot_at = EXCLUDED.snapshot_at,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def materialize_history_event(manager: PostgresDatabaseManager) -> None:
    sql = """
    INSERT INTO theme_history_event (
        subject_key, theme_id, theme_name, subject_rank_id, event_id,
        rank_date, driver_summary, description, heat, heat_name, pct_chg, his_pct_chg,
        source_type, source_ref, trace_id, evidence_json, effective_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        subject_rank_id,
        event_id,
        rank_date,
        LEFT(COALESCE(description, ''), 500) AS driver_summary,
        description,
        heat,
        heat_name,
        pct_chg,
        his_pct_chg,
        source_type,
        source_ref,
        NULL::VARCHAR(120) AS trace_id,
        jsonb_build_object(
            'source_type', source_type,
            'source_ref', source_ref,
            'event_id', event_id,
            'subject_rank_id', subject_rank_id
        ) AS evidence_json,
        COALESCE(rank_date::timestamp, NOW()) AS effective_at
    FROM vw_theme_history_candidate
    WHERE source_ref IS NOT NULL
    ON CONFLICT (subject_key, source_type, source_ref)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        subject_rank_id = EXCLUDED.subject_rank_id,
        event_id = EXCLUDED.event_id,
        rank_date = EXCLUDED.rank_date,
        driver_summary = EXCLUDED.driver_summary,
        description = EXCLUDED.description,
        heat = EXCLUDED.heat,
        heat_name = EXCLUDED.heat_name,
        pct_chg = EXCLUDED.pct_chg,
        his_pct_chg = EXCLUDED.his_pct_chg,
        trace_id = EXCLUDED.trace_id,
        evidence_json = EXCLUDED.evidence_json,
        effective_at = EXCLUDED.effective_at,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def materialize_tree_relation(manager: PostgresDatabaseManager) -> None:
    sql = """
    INSERT INTO theme_tree_relation (
        parent_subject_key, parent_theme_id, parent_theme_name, child_subject_key,
        child_theme_id, child_name, relation_type, evidence_source, source_type,
        pct_chg, stock_count, limit_up_count, lead_stock_id, lead_stock_name,
        depth, evidence_json, effective_at
    )
    SELECT
        parent_subject_key,
        parent_theme_id,
        parent_theme_name,
        child_subject_key,
        child_theme_id,
        child_name,
        relation_type,
        source_type AS evidence_source,
        source_type,
        pct_chg,
        stock_count,
        limit_up_count,
        lead_stock_id,
        lead_stock_name,
        depth,
        jsonb_build_object(
            'relation_type', relation_type,
            'source_type', source_type,
            'lead_stock_id', lead_stock_id,
            'lead_stock_name', lead_stock_name,
            'depth', depth
        ) AS evidence_json,
        NOW() AS effective_at
    FROM vw_theme_tree_candidate
    ON CONFLICT (parent_subject_key, child_subject_key, relation_type, source_type)
    DO UPDATE SET
        parent_theme_id = EXCLUDED.parent_theme_id,
        parent_theme_name = EXCLUDED.parent_theme_name,
        child_theme_id = EXCLUDED.child_theme_id,
        child_name = EXCLUDED.child_name,
        evidence_source = EXCLUDED.evidence_source,
        pct_chg = EXCLUDED.pct_chg,
        stock_count = EXCLUDED.stock_count,
        limit_up_count = EXCLUDED.limit_up_count,
        lead_stock_id = EXCLUDED.lead_stock_id,
        lead_stock_name = EXCLUDED.lead_stock_name,
        depth = EXCLUDED.depth,
        evidence_json = EXCLUDED.evidence_json,
        effective_at = EXCLUDED.effective_at,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def materialize_stock_map(manager: PostgresDatabaseManager) -> None:
    sql = """
    INSERT INTO theme_stock_map (
        subject_key, theme_id, theme_name, stock_id, stock_name,
        relation_type, evidence_source, confidence, source_type,
        reason, remark, evidence_json, effective_at
    )
    SELECT
        subject_key,
        theme_id,
        theme_name,
        stock_id,
        stock_name,
        relation_type_candidate AS relation_type,
        source_type AS evidence_source,
        confidence,
        source_type,
        reason,
        remark,
        evidence_json,
        NOW() AS effective_at
    FROM vw_theme_stock_map_candidate
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        theme_id = EXCLUDED.theme_id,
        theme_name = EXCLUDED.theme_name,
        stock_name = EXCLUDED.stock_name,
        relation_type = EXCLUDED.relation_type,
        evidence_source = EXCLUDED.evidence_source,
        confidence = EXCLUDED.confidence,
        source_type = EXCLUDED.source_type,
        reason = EXCLUDED.reason,
        remark = EXCLUDED.remark,
        evidence_json = EXCLUDED.evidence_json,
        effective_at = EXCLUDED.effective_at,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def print_counts(manager: PostgresDatabaseManager) -> None:
    async with manager.pool.acquire() as conn:
        for table in [
            "theme_detail_snapshot",
            "theme_history_event",
            "theme_tree_relation",
            "theme_stock_map",
        ]:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"{table}={count}")


async def main() -> int:
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        await materialize_detail_snapshot(manager)
        await materialize_history_event(manager)
        await materialize_tree_relation(manager)
        await materialize_stock_map(manager)
        await print_counts(manager)
        print("[OK] materialized phase1 serving tables")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
