import asyncio
import json

import pytest

from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from run_full_chain_test import _completed_indices, _load_resume_details, _parse_args, _parse_test_cases


class _EventBus:
    def __init__(self):
        self.published = []

    async def publish_to_stream(self, stream_key, data):
        self.published.append((stream_key, data))
        return f"msg-{len(self.published)}"


class _Gateway:
    def __init__(self):
        self.events = []

    async def create_news_event(self, event_data):
        self.events.append(event_data)
        return len(self.events)


class _TimeoutModelService:
    def __init__(self):
        self.calls = 0

    async def extract_event(self, _news_data):
        self.calls += 1
        await asyncio.sleep(1)


def _stored_message(index):
    return {
        "payload": {
            "news_data": {
                "id": index,
                "news_row_id": index,
                "news_id": f"phase6-{index}",
                "sequence": index,
                "title": f"news {index}",
                "content": "structured fallback content",
                "publish_date": "2026-05-22",
            }
        }
    }


def _processor(service, **config):
    event_bus = _EventBus()
    gateway = _Gateway()
    processor = NewsStreamProcessor(
        event_bus=event_bus,
        config={
            "database_gateway": gateway,
            "enable_local_triage": False,
            "enable_ai_analysis": True,
            "structuring_total_timeout_s": 0.01,
            "structuring_retry_delay_s": 0,
            **config,
        },
        business_services={"model_service": service},
    )
    return processor, event_bus, gateway


@pytest.mark.asyncio
async def test_tc_phase6_single_structuring_timeout_falls_back_and_continues():
    service = _TimeoutModelService()
    processor, event_bus, gateway = _processor(service, structuring_max_retries=2)

    result = await processor.process_stream_message("stored-1", _stored_message(1))

    assert result["success"] is True
    assert result["structuring"]["status"] == "structuring_timeout"
    assert result["structuring"]["llm_retry_count"] == 2
    assert result["structured_event"]["structuring_status"] == "fallback_minimal"
    assert result["structured_event"]["event_type"] == "unknown"
    assert result["structured_event"]["entities"] == []
    assert event_bus.published
    assert gateway.events[0]["summary"] == "news 1"
    stats = await processor.get_business_stats()
    assert stats["structuring_timeout_count"] == 1
    assert stats["fallback_structured_count"] == 1
    assert stats["processed_after_fallback_count"] == 1


@pytest.mark.asyncio
async def test_tc_phase6_consecutive_timeouts_open_structuring_circuit_breaker():
    service = _TimeoutModelService()
    processor, _event_bus, _gateway = _processor(
        service,
        structuring_max_retries=0,
        structuring_circuit_breaker_threshold=5,
    )

    for index in range(1, 7):
        result = await processor.process_stream_message(f"stored-{index}", _stored_message(index))
        assert result["success"] is True

    stats = await processor.get_business_stats()
    assert service.calls == 5
    assert stats["structuring_timeout_count"] == 5
    assert stats["circuit_breaker_open"] is True
    assert stats["circuit_breaker_open_count"] == 1
    assert stats["fallback_structured_count"] == 6


def test_tc_phase6_harness_offset_and_resume_helpers(tmp_path):
    args = _parse_args(["--start-index", "68", "--sample-size", "32", "--skip-existing"])
    assert args.start_index == 68
    assert args.sample_size == 32
    assert args.skip_existing is True
    assert len(_parse_test_cases(2, start_index=1)) == 2

    report_path = tmp_path / "resume.json"
    report_path.write_text(
        json.dumps(
            {
                "details": [
                    {"index": 68, "status": "ok", "news_id": "done"},
                    {"index": 69, "status": "failed", "news_id": "retry"},
                ]
            }
        ),
        encoding="utf-8",
    )
    details = _load_resume_details(report_path)
    assert _completed_indices(details) == {68}
