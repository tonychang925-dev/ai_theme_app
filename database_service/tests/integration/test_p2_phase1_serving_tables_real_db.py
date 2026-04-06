import os

import asyncpg
import pytest


async def _connect():
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )


@pytest.mark.asyncio
async def test_phase1_serving_tables_materialized_real_db():
    conn = await _connect()
    try:
        counts = {}
        for table in [
            "theme_detail_snapshot",
            "theme_history_event",
            "theme_tree_relation",
            "theme_stock_map",
        ]:
            counts[table] = await conn.fetchval(f"select count(*) from {table}")
        assert counts["theme_detail_snapshot"] >= 1
        assert counts["theme_history_event"] >= 1
        assert counts["theme_tree_relation"] >= 1
        assert counts["theme_stock_map"] >= 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_phase1_history_serving_traceability_real_db():
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            select subject_key, source_type, source_ref, event_id
            from theme_history_event
            where source_ref is not null
            order by rank_date desc nulls last, id desc
            limit 1
            """
        )
        assert row is not None
        assert row["subject_key"]
        assert row["source_type"]
        assert row["source_ref"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_phase1_tree_and_stock_relation_structured_real_db():
    conn = await _connect()
    try:
        tree_row = await conn.fetchrow(
            """
            select parent_subject_key, child_subject_key, relation_type, evidence_source
            from theme_tree_relation
            order by id
            limit 1
            """
        )
        assert tree_row is not None
        assert tree_row["parent_subject_key"]
        assert tree_row["child_subject_key"]
        assert tree_row["relation_type"] in {"parent_child", "children_snapshot"}
        assert tree_row["evidence_source"]

        stock_row = await conn.fetchrow(
            """
            select subject_key, stock_id, relation_type, evidence_source
            from theme_stock_map
            order by id
            limit 1
            """
        )
        assert stock_row is not None
        assert stock_row["subject_key"]
        assert stock_row["stock_id"]
        assert stock_row["relation_type"] in {"leader", "core", "member", "edge"}
        assert stock_row["evidence_source"]
    finally:
        await conn.close()
