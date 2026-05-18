import json
import asyncio

import pytest

from database_service.streams.handlers.theme_processor import ThemeProcessor


class _FakeRedis:
    def __init__(self):
        self.xadd_calls = []
        self.xack_calls = []

    async def xadd(self, stream, fields, maxlen=None):
        self.xadd_calls.append((stream, fields, maxlen))
        return "dead-1"

    async def xack(self, stream, group, message_id):
        self.xack_calls.append((stream, group, message_id))
        return 1


class _FakeGateway:
    async def get_news_event_for_match(self, event_id):
        return {
            "event_id": event_id,
            "news_id": 1001,
            "title": "苹果公司可能已经重启其轻量级增强现实（AR）眼镜计划",
        }


class _SlowThemeService:
    async def match_event(self, event_row, database_gateway=None):
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_move_to_dead_letter_serializes_payload_and_acks_original_message():
    redis = _FakeRedis()
    processor = ThemeProcessor(
        consumer_name="unit_processor",
        config={
            "consumer_group": "unit_group",
            "stream_structured": "stream:test:structured",
            "stream_dead_letter": "stream:test:dead",
        },
    )
    processor.redis_client = redis

    await processor._move_to_dead_letter(
        "structured",
        "msg-1",
        {"payload": {"event_id": 7918, "case_id": "pm_case_0011"}},
        "processing_cancelled_before_terminal_decision",
    )

    assert redis.xack_calls == [("stream:test:structured", "unit_group", "msg-1")]
    assert len(redis.xadd_calls) == 1
    stream, fields, maxlen = redis.xadd_calls[0]
    assert stream == "stream:test:dead"
    assert maxlen == 1000
    assert json.loads(fields["original_data"]) == {
        "payload": {"event_id": 7918, "case_id": "pm_case_0011"}
    }
    assert fields["error"] == "processing_cancelled_before_terminal_decision"


@pytest.mark.asyncio
async def test_structured_processing_cancellation_goes_dead_letter_and_acks_message():
    redis = _FakeRedis()
    processor = ThemeProcessor(
        consumer_name="unit_processor",
        config={
            "consumer_group": "unit_group",
            "stream_structured": "stream:test:structured",
            "stream_decision": "stream:test:decision",
            "stream_dead_letter": "stream:test:dead",
        },
    )
    processor.redis_client = redis
    processor.gateway = _FakeGateway()
    processor.theme_service = _SlowThemeService()

    message_data = {
        "payload": json.dumps(
            {"event_id": 7918, "case_id": "pm_case_0011", "run_id": "unit_run"},
            ensure_ascii=False,
        )
    }
    task = asyncio.create_task(
        processor._process_message_structured(
            "structured",
            "stream:test:structured",
            "msg-7918",
            message_data,
        )
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert redis.xack_calls == [("stream:test:structured", "unit_group", "msg-7918")]
    assert len(redis.xadd_calls) == 1
    _, fields, _ = redis.xadd_calls[0]
    assert fields["error"] == "processing_cancelled_before_terminal_decision"
