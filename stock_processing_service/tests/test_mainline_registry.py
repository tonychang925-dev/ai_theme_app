"""Tests for PR-9: Mainline Registry — tables, persistence, review service."""
import pytest
import json
import asyncpg
from datetime import date


@pytest.fixture
async def pool():
    conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
    # Clean up test data
    await conn.execute("DELETE FROM mainline_review_queue WHERE review_id LIKE 'test_%'")
    await conn.execute("DELETE FROM mainline_registry WHERE mainline_id LIKE 'ml_test_%'")
    yield conn
    await conn.execute("DELETE FROM mainline_review_queue WHERE review_id LIKE 'test_%'")
    await conn.execute("DELETE FROM mainline_registry WHERE mainline_id LIKE 'ml_test_%'")
    await conn.close()


class TestMainlineReviewQueueTable:

    async def test_insert_and_query(self, pool):
        await pool.execute(
            """INSERT INTO mainline_review_queue (review_id, trade_date, subject_key, theme_name, machine_state, review_priority)
               VALUES ('test_001', '2026-05-29', 'sk_a', '测试题材', 'machine_slow_candidate', 85.0)
               ON CONFLICT (review_id) DO NOTHING"""
        )
        row = await pool.fetchrow("SELECT * FROM mainline_review_queue WHERE review_id = 'test_001'")
        assert row is not None
        assert row["review_status"] == "pending"
        assert row["human_decision"] is None

    async def test_idempotent_upsert(self, pool):
        """PR-9B: repeated insert should not create duplicates."""
        for _ in range(3):
            await pool.execute(
                """INSERT INTO mainline_review_queue (review_id, trade_date, subject_key, machine_state)
                   VALUES ('test_idem', '2026-05-29', 'sk_idem', 'machine_fast_candidate')
                   ON CONFLICT (review_id) DO NOTHING"""
            )
        count = await pool.fetchval("SELECT COUNT(*) FROM mainline_review_queue WHERE review_id = 'test_idem'")
        assert count == 1

    async def test_upsert_preserves_human_decision(self, pool):
        """PR-9B: machine upsert must not overwrite human-reviewed fields."""
        await pool.execute(
            """INSERT INTO mainline_review_queue (review_id, trade_date, subject_key, machine_state, review_status, human_decision, human_reviewer)
               VALUES ('test_upsert', '2026-05-29', 'sk_u', 'machine_slow_candidate', 'reviewed', 'confirm_mainline', '分析师A')"""
        )
        # Now simulate machine re-run: upsert should NOT touch human fields
        await pool.execute(
            """INSERT INTO mainline_review_queue (review_id, trade_date, subject_key, machine_state)
               VALUES ('test_upsert', '2026-05-29', 'sk_u', 'machine_slow_candidate')
               ON CONFLICT (review_id) DO UPDATE SET machine_state = EXCLUDED.machine_state
               WHERE mainline_review_queue.review_status != 'reviewed'"""
        )
        row = await pool.fetchrow("SELECT * FROM mainline_review_queue WHERE review_id = 'test_upsert'")
        assert row["human_decision"] == "confirm_mainline"  # preserved
        assert row["human_reviewer"] == "分析师A"


class TestMainlineRegistryTable:

    async def test_insert_confirmed_mainline(self, pool):
        await pool.execute(
            """INSERT INTO mainline_registry (mainline_id, mainline_name, canonical_subject_key, identity_status, valid_from)
               VALUES ('ml_test_001', '测试主线', 'sk_confirmed', 'confirmed', '2026-05-29')"""
        )
        row = await pool.fetchrow("SELECT * FROM mainline_registry WHERE mainline_id = 'ml_test_001'")
        assert row is not None
        assert row["identity_status"] == "confirmed"

    async def test_merge_related_keys(self, pool):
        await pool.execute(
            """INSERT INTO mainline_registry (mainline_id, mainline_name, canonical_subject_key, identity_status, valid_from, related_subject_keys_json)
               VALUES ('ml_test_002', '目标主线', 'sk_target', 'confirmed', '2026-05-29', '["sk_a"]'::jsonb)"""
        )
        # Merge new keys
        existing = json.loads(await pool.fetchval(
            "SELECT related_subject_keys_json FROM mainline_registry WHERE mainline_id = 'ml_test_002'"))
        merged = list(set(existing + ["sk_b", "sk_c"]))
        await pool.execute(
            "UPDATE mainline_registry SET related_subject_keys_json = $2::jsonb WHERE mainline_id = $1",
            'ml_test_002', json.dumps(merged),
        )
        row = await pool.fetchrow("SELECT * FROM mainline_registry WHERE mainline_id = 'ml_test_002'")
        keys = json.loads(row["related_subject_keys_json"])
        assert "sk_a" in keys
        assert "sk_b" in keys
        assert "sk_c" in keys


class TestReviewService:

    @pytest.mark.asyncio
    async def test_reject_invalid_decision(self):
        from stock_processing_service.application.services.mainline_review_service import MainlineReviewService
        svc = MainlineReviewService(write_port=None)
        result = await svc.submit_decision(review_id="x", human_decision="invalid")
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_confirm_missing_canonical_key(self):
        from stock_processing_service.application.services.mainline_review_service import MainlineReviewService
        svc = MainlineReviewService(write_port=None)
        result = await svc.submit_decision(review_id="x", human_decision="confirm_mainline")
        assert result["ok"] is False
        assert "canonical_subject_key" in result["error"]

    @pytest.mark.asyncio
    async def test_watch_returns_ok(self):
        from stock_processing_service.application.services.mainline_review_service import MainlineReviewService
        svc = MainlineReviewService(write_port=None)
        result = await svc.submit_decision(review_id="x", human_decision="watch")
        assert result["ok"] is True
        assert result["registry_written"] is False

    @pytest.mark.asyncio
    async def test_reject_returns_ok(self):
        from stock_processing_service.application.services.mainline_review_service import MainlineReviewService
        svc = MainlineReviewService(write_port=None)
        result = await svc.submit_decision(review_id="x", human_decision="reject")
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_merge_requires_target_id(self):
        from stock_processing_service.application.services.mainline_review_service import MainlineReviewService
        svc = MainlineReviewService(write_port=None)
        result = await svc.submit_decision(review_id="x", human_decision="merge_into_existing_mainline")
        assert result["ok"] is False
        assert "merge_target_mainline_id" in result["error"]


class TestV2BuilderFields:

    def test_pending_reviews_passthrough(self):
        from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
            PostMarketDailyReviewV2Builder,
        )
        builder = PostMarketDailyReviewV2Builder()
        doc = {
            "analyst_review_items": [
                {"review_id": "test_r1", "subject_key": "sk_a", "machine_state": "machine_fast_candidate"},
            ],
        }
        from datetime import date
        result = builder.build(trade_date=date(2026, 5, 29), recap_doc=doc)
        assert "pending_mainline_reviews" in result
        assert len(result["pending_mainline_reviews"]) == 1
        assert "confirmed_mainlines" in result

