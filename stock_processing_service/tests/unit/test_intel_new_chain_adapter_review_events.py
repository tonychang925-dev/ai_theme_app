from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.intel_new_chain_adapter import NewChainIntelFeedAdapter


class _Gateway:
    async def get_pre_market_review_events(self, feed_date, limit=200):
        return [
            {
                "event_id": 101,
                "item_id": "review:101",
                "occurred_at": "2026-05-20T07:30:00",
                "title": "待复核事件",
                "summary": "题材匹配需人工确认",
                "theme_name": "算力",
                "confidence": 0.55,
                "impact_score": 0,
                "reason": "llm_accept_without_anchor_evidence",
                "source_channel": "structured_theme_match",
                "source_type": "event_review_queue",
            }
        ]

    async def get_new_chain_intel_recap(self, feed_date):
        return []

    async def get_new_chain_intel_w2s(self, feed_date):
        return []

    async def get_new_chain_intel_cycle(self, feed_date):
        return []

    async def get_new_chain_intel_identity(self, feed_date):
        return []

    async def get_new_chain_intel_strong_watch(self, feed_date, limit_per_source=20):
        return []

    async def get_intel_news_events(self, feed_date):
        return []

    async def get_intel_subject_history(self, feed_date):
        return []


@pytest.mark.asyncio
async def test_review_events_are_exposed_as_event_review_items():
    adapter = NewChainIntelFeedAdapter(_Gateway())

    items = await adapter.get_intel_feed(date(2026, 5, 20), item_type="event_review")

    assert len(items) == 1
    assert items[0]["item_type"] == "event_review"
    assert items[0]["source_type"] == "event_review_queue"
    assert items[0]["source_channel"] == "akshare_realtime"
    assert items[0]["theme_names"] == ["算力"]
