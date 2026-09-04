"""I2A focused regressions for the Market-owned event resolver."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import AdapterRequest

SCHEMA_PATH = ROOT / "docs" / "integration" / "JULIA_ADAPTER_SCHEMA_v1.json"
CST = timezone(timedelta(hours=8))


class FixedClock:
    def now(self):
        return datetime(2026, 9, 4, 11, 30, tzinfo=CST)


class FakeGateway:
    def __init__(self, candidates=None, resolver_error=None):
        self.candidates = candidates or []
        self.resolver_error = resolver_error
        self.resolve_calls = []
        self.event_calls = []
        self.event = None

    async def resolve_market_event_candidates(
        self, *, query, normalized_theme=None, time_window=None, limit=20
    ):
        self.resolve_calls.append(
            {
                "query": query,
                "normalized_theme": normalized_theme,
                "time_window": time_window,
                "limit": limit,
            }
        )
        if self.resolver_error is not None:
            raise self.resolver_error
        hint = normalized_theme or query
        return [item for item in self.candidates if item["hint"] == hint]

    async def get_news_event_for_match(self, event_id):
        self.event_calls.append(event_id)
        if self.event is None:
            return None
        return {**self.event, "id": event_id}

    async def get_event_subject_mappings_by_event_ids(self, event_ids):
        return []


def _candidate(event_id, hint="半导体设备", occurred_at=None, title=None):
    return {
        "hint": hint,
        "market_event_id": event_id,
        "title": title or f"Event {event_id}",
        "summary": f"Canonical event {event_id}",
        "occurred_at": occurred_at or datetime(2026, 9, 3, tzinfo=CST),
        "matched_subjects": [{
            "subject_key": "semi_equipment",
            "subject_name": "半导体设备",
            "relation_type": "primary",
            "confidence": 0.93,
        }],
    }


def _request(**arguments):
    return AdapterRequest(
        operation="market.event.resolve",
        arguments=arguments,
        correlation_id="corr-i2a",
        idempotency_key="idem-i2a",
        schema_version="1.0",
    )


def _adapter(gateway):
    return DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())


def test_wire_schema_accepts_market_event_resolve():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    request = _request(query="今天半导体设备为什么涨？", normalized_theme="半导体设备", limit=20).to_dict()
    envelope_schema = {
        "$ref": "#/definitions/DomainObservationEnvelope",
        **schema,
    }
    envelope = {
        "operation": "market.event.resolve",
        "status": "success",
        "data_state": "normal",
        "payload": {"state": "RESOLVED", "query": "今天", "candidates": [], "selected_event_id": 1},
        "source_records": [],
        "failures": [],
        "schema_version": "1.0",
    }
    request_schema = {"$ref": "#/definitions/AdapterRequest", **schema}
    Draft202012Validator(request_schema).validate(request)
    Draft202012Validator(envelope_schema).validate(envelope)


@pytest.mark.asyncio
async def test_one_candidate_resolved_and_selected_id_is_canonical():
    gateway = FakeGateway([_candidate(501)])
    result = await _adapter(gateway).execute(_request(query="今天半导体设备为什么涨？", normalized_theme="半导体设备"))

    assert result.status == "success"
    assert result.payload["state"] == "RESOLVED"
    assert result.payload["selected_event_id"] == 501
    assert result.payload["candidates"][0]["market_event_id"] == 501
    assert result.payload["candidates"][0]["matched_subjects"][0]["subject_name"] == "半导体设备"
    assert result.source_records[0].provenance["canonical_id"] == "public.news_event.id"


@pytest.mark.asyncio
async def test_zero_candidates_is_unresolved_and_ambiguous_preserves_bounded_candidates():
    adapter = _adapter(FakeGateway())
    unresolved = await adapter.execute(_request(query="不存在主题", normalized_theme="不存在主题"))
    ambiguous_gateway = FakeGateway([_candidate(501), _candidate(502)])
    ambiguous = await _adapter(ambiguous_gateway).execute(_request(query="今天半导体设备为什么涨？", normalized_theme="半导体设备"))

    assert unresolved.status == "success"
    assert unresolved.data_state == "empty"
    assert unresolved.payload["state"] == "UNRESOLVED"
    assert unresolved.payload["candidates"] == []
    assert ambiguous.payload["state"] == "AMBIGUOUS"
    assert "selected_event_id" not in ambiguous.payload
    assert [item["market_event_id"] for item in ambiguous.payload["candidates"]] == [501, 502]


@pytest.mark.asyncio
async def test_database_and_relation_failures_are_not_unresolved():
    connection_error = ConnectionError("database unavailable")
    relation_error = RuntimeError("event_subject_map lookup failed")

    db_result = await _adapter(FakeGateway(resolver_error=connection_error)).execute(
        _request(query="半导体设备", normalized_theme="半导体设备")
    )
    relation_result = await _adapter(FakeGateway(resolver_error=relation_error)).execute(
        _request(query="半导体设备", normalized_theme="半导体设备")
    )

    assert db_result.status == "unavailable"
    assert db_result.payload == {}
    assert db_result.failures[0].retryable is True
    assert relation_result.status == "error"
    assert relation_result.payload == {}
    assert relation_result.failures[0].code == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_same_state_is_deterministic_and_only_one_candidate_auto_selects():
    candidates = [
        _candidate(502, occurred_at=datetime(2026, 9, 4, 10, tzinfo=CST)),
        _candidate(501, occurred_at=datetime(2026, 9, 4, 9, tzinfo=CST)),
    ]
    gateway = FakeGateway(candidates)
    adapter = _adapter(gateway)
    arguments = _request(query="半导体设备", normalized_theme="半导体设备", time_window={"date": "2026-09-04"}).arguments
    first = await adapter.execute(_request(**arguments))
    second = await adapter.execute(_request(**arguments))

    assert first.payload == second.payload
    assert first.payload["state"] == "AMBIGUOUS"
    assert gateway.resolve_calls[0] == gateway.resolve_calls[1]


@pytest.mark.asyncio
async def test_selected_id_feeds_existing_market_event_read():
    gateway = FakeGateway([_candidate(501)])
    gateway.event = {
        "news_id": 901,
        "source_category": "news",
        "event_type": "policy",
        "summary": "Semiconductor equipment event",
        "direction": 1,
        "confidence": 0.9,
        "source_trace_id": "trace-501",
        "event_time": datetime(2026, 9, 3, tzinfo=CST),
        "title": "Semiconductor equipment event",
        "source_name": "source-a",
        "source_url": "https://example.com",
    }
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())
    resolved = await adapter.execute(_request(query="半导体设备", normalized_theme="半导体设备"))
    read = await adapter.execute(AdapterRequest(
        operation="market.event.read",
        arguments={"event_id": resolved.payload["selected_event_id"]},
        correlation_id="corr-read",
        idempotency_key="idem-read",
    ))

    assert gateway.event_calls == [501]
    assert read.status == "success"
    assert read.payload["event"]["event_id"] == 501


@pytest.mark.asyncio
async def test_hostile_query_is_inert_and_event_id_is_not_resolution():
    hostile = "'; DROP TABLE news_event; --"
    gateway = FakeGateway([_candidate(501)])
    adapter = _adapter(gateway)
    hostile_result = await adapter.execute(_request(query=hostile, normalized_theme=hostile))
    rejected = await adapter.execute(_request(query="半导体设备", market_event_id=501))

    assert hostile_result.status == "success"
    assert hostile_result.payload["state"] == "UNRESOLVED"
    assert gateway.resolve_calls == [{
        "query": hostile,
        "normalized_theme": hostile,
        "time_window": {},
        "limit": 20,
    }]
    assert rejected.status == "error"
    assert rejected.failures[0].code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_no_llm_or_provider_is_involved():
    class AuditedGateway(FakeGateway):
        def __getattr__(self, name):
            if "llm" in name or "provider" in name:
                raise AssertionError(f"unexpected dependency: {name}")
            raise AttributeError(name)

    result = await _adapter(AuditedGateway()).execute(_request(query="半导体设备", normalized_theme="半导体设备"))

    assert result.payload["state"] == "UNRESOLVED"
