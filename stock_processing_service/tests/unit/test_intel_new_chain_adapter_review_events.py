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


class _DuplicateGateway(_Gateway):
    async def get_intel_news_events(self, feed_date):
        return [
            {
                "item_id": "event:dup-1",
                "occurred_at": "2026-05-20T09:10:00",
                "title": "新疆自贸区政策推进",
                "summary": "新疆自贸区政策推进",
                "theme_subject_keys": ["9012396"],
                "theme_names": ["新疆自贸区"],
                "impact_score": 88,
                "confidence": 0.91,
                "source_type": "event_theme_map",
                "source_channel": "realtime_news",
            }
        ]

    async def get_intel_subject_history(self, feed_date):
        return [
            {
                "item_id": "history:dup-1",
                "occurred_at": "2026-05-20T09:10:00",
                "title": "新疆自贸区政策推进",
                "summary": "新疆自贸区政策推进",
                "theme_names": ["新疆自贸区"],
                "confidence": 0.81,
                "impact_score": 72,
                "source_type": "jyhf_cdp_dom",
                "source_channel": "jyhf_cdp",
            }
        ]

    async def resolve_subject_keys_by_names(self, names):
        return {"新疆自贸区政策推进": "9012396"}


class _SimilarDuplicateGateway(_Gateway):
    async def get_intel_news_events(self, feed_date):
        return [
            {
                "item_id": "event:dup-1",
                "occurred_at": "2026-05-31T02:12:20",
                "title": "中国汽车流通协会发布的最新一期库存预警指数调查",
                "summary": "中国汽车流通协会发布的最新一期库存预警指数调查",
                "theme_subject_keys": ["9014270"],
                "theme_names": ["新能源车"],
                "impact_score": 88,
                "confidence": 0.91,
                "source_type": "event_theme_map",
                "source_channel": "realtime_news",
            },
            {
                "item_id": "event:dup-2",
                "occurred_at": "2026-05-31T02:12:21",
                "title": "2026年5月31日，中国汽车流通协会发布的最新一期中国汽车经销商库存预警指数调查",
                "summary": "2026年5月31日，中国汽车流通协会发布的最新一期中国汽车经销商库存预警指数调查",
                "theme_subject_keys": ["9014270"],
                "theme_names": ["新能源车"],
                "impact_score": 90,
                "confidence": 0.92,
                "source_type": "event_theme_map",
                "source_channel": "realtime_news",
            },
        ]


@pytest.mark.asyncio
async def test_review_events_are_exposed_as_event_review_items():
    adapter = NewChainIntelFeedAdapter(_Gateway())

    items = await adapter.get_intel_feed(date(2026, 5, 20), item_type="event_review")

    assert len(items) == 1
    assert items[0]["item_type"] == "event_review"
    assert items[0]["source_type"] == "event_review_queue"
    assert items[0]["source_channel"] == "akshare_realtime"
    assert items[0]["theme_names"] == ["算力"]


@pytest.mark.asyncio
async def test_intel_feed_dedupes_cross_loader_duplicate_titles():
    adapter = NewChainIntelFeedAdapter(_DuplicateGateway())

    items = await adapter.get_intel_feed(date(2026, 5, 20), item_type="event")

    assert len(items) == 1
    assert items[0]["item_id"] == "event:dup-1"
    assert items[0]["title"] == "新疆自贸区政策推进"


@pytest.mark.asyncio
async def test_intel_feed_dedupes_title_rewrite_duplicates_with_same_theme_key():
    adapter = NewChainIntelFeedAdapter(_SimilarDuplicateGateway())

    items = await adapter.get_intel_feed(date(2026, 5, 31), item_type="event")

    assert len(items) == 1
    assert items[0]["item_id"] == "event:dup-2"
    assert "中国汽车流通协会" in items[0]["title"]
