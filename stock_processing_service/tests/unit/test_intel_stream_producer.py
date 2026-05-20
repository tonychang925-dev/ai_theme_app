from __future__ import annotations

import json

import pytest

from stock_processing_service.application.services.intel_stream_producer import IntelStreamProducer


class _Redis:
    def __init__(self) -> None:
        self.messages = []

    async def xadd(self, stream_name, fields, maxlen=10000):
        self.messages.append({"stream_name": stream_name, "fields": fields, "maxlen": maxlen})
        return "1710000000000-0"


class _Gateway:
    def __init__(self) -> None:
        self.events = {
            1: {"id": 1, "raw_doc_id": 10, "stream_status": "pending", "title": "队首"},
            2: {
                "id": 2,
                "raw_doc_id": 20,
                "stream_status": "pending",
                "event_type": "major_contract",
                "source_type": "announcement",
                "stock_code": "000001",
                "stock_name": "平安银行",
                "title": "重大合同公告",
                "summary": "签署重大合同",
                "confidence": 0.8,
                "impact_score": 80,
                "publish_time": "2026-05-19T16:00:00+08:00",
                "entities": {"entity_anchors": ["客户A"]},
                "evidence_json": {"evidence": ["重大合同"]},
            },
            3: {
                "id": 3,
                "raw_doc_id": 30,
                "stream_status": "produced",
                "stream_message_id": "1700000000000-1",
            },
        }
        self.news_events = []
        self.status_updates = []

    async def get_pending_intel_events_for_stream(self, limit=50):
        return [self.events[1]][:limit]

    async def get_intel_event_for_stream(self, intel_event_id):
        return self.events.get(intel_event_id)

    async def create_news_event_with_intel(self, event_data):
        self.news_events.append(event_data)
        return {"id": 101, **event_data}

    async def update_intel_event_stream_status(self, event_id, status, stream_message_id=None):
        self.status_updates.append(
            {"event_id": event_id, "status": status, "stream_message_id": stream_message_id}
        )
        self.events[event_id]["stream_status"] = status
        self.events[event_id]["stream_message_id"] = stream_message_id


@pytest.mark.asyncio
async def test_produce_uses_exact_event_lookup_not_pending_queue_head():
    gateway = _Gateway()
    redis = _Redis()
    producer = IntelStreamProducer(gateway, redis_client=redis, run_id="unit")

    message_id = await producer.produce(2)

    assert message_id == "1710000000000-0"
    assert gateway.news_events[0]["structured_intel_event_id"] == 2
    assert gateway.status_updates == [
        {"event_id": 2, "status": "produced", "stream_message_id": "1710000000000-0"}
    ]
    payload = json.loads(redis.messages[0]["fields"]["payload"])
    assert payload["event_id"] == 101
    assert payload["structured_intel_event_id"] == 2


@pytest.mark.asyncio
async def test_produce_returns_existing_message_for_already_produced_event():
    gateway = _Gateway()
    redis = _Redis()
    producer = IntelStreamProducer(gateway, redis_client=redis, run_id="unit")

    message_id = await producer.produce(3)

    assert message_id == "1700000000000-1"
    assert gateway.news_events == []
    assert redis.messages == []
