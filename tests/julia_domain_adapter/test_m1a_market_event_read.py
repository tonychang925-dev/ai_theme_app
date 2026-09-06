"""M1A focused regressions for market.event.read."""

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
    def __init__(self, event=None, relations=None, event_error=None, relation_error=None):
        self.event = event
        self.relations = relations or []
        self.event_error = event_error
        self.relation_error = relation_error
        self.event_calls = []
        self.relation_calls = []

    async def get_news_event_for_match(self, event_id):
        self.event_calls.append(event_id)
        if self.event_error is not None:
            raise self.event_error
        return self.event

    async def get_event_subject_mappings_by_event_ids(self, event_ids):
        self.relation_calls.append(event_ids)
        if self.relation_error is not None:
            raise self.relation_error
        return self.relations


def _request(event_id):
    return AdapterRequest(
        operation="market.event.read",
        arguments={"event_id": event_id},
        correlation_id="corr-m1a",
        idempotency_key="idem-m1a",
        schema_version="1.0",
    )


def _gateway(event=None, relations=None, **kwargs):
    return FakeGateway(
        event={
            "id": 501,
            "news_id": 901,
            "source_category": "news",
            "event_type": "product_launch",
            "summary": "Company released a new product.",
            "direction": 1,
            "confidence": 0.88,
            "source_trace_id": "news_event:901:product_launch",
            "event_time": datetime(2026, 9, 3, 9, 30, tzinfo=CST),
            "created_at": datetime(2026, 9, 3, 9, 31, tzinfo=CST),
            "title": "Company released a new product",
            "source_name": "source-a",
            "source_url": "https://example.com/a",
            **(event or {}),
        },
        relations=[{
            "event_id": 501,
            "subject_key": "ar_glasses",
            "subject_name": "AR Glasses",
            "relation_type": "primary",
            "confidence": 0.93,
            "match_reason": "product maps to subject",
            "evidence_json": {"summary": "new product"},
            "source": "theme_match_engine",
            "source_trace_id": "trace-map-1",
            "run_id": "run-map-1",
            "created_at": datetime(2026, 9, 3, 9, 35, tzinfo=CST),
            "updated_at": datetime(2026, 9, 3, 9, 36, tzinfo=CST),
        }] if relations is None else relations,
        **kwargs,
    )


def test_wire_schema_accepts_market_event_read_and_not_found_envelope():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    request = _request(501).to_dict()
    envelope = {
        "operation": "market.event.read",
        "status": "error",
        "data_state": "empty",
        "payload": {},
        "source_records": [],
        "failures": [{
            "code": "NOT_FOUND",
            "message": "news_event not found",
            "source_name": "news_event",
            "retryable": False,
            "details": {},
        }],
        "schema_version": "1.0",
    }

    request_schema = {"$ref": "#/definitions/AdapterRequest", **schema}
    envelope_schema = {"$ref": "#/definitions/DomainObservationEnvelope", **schema}
    Draft202012Validator(request_schema).validate(request)
    Draft202012Validator(envelope_schema).validate(envelope)


@pytest.mark.asyncio
async def test_valid_event_maps_source_fields_theme_and_provenance():
    gateway = _gateway()
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())

    result = await adapter.execute(_request(501))

    assert result.status == "success"
    assert result.data_state == "normal"
    assert result.payload["event"]["event_id"] == 501
    assert result.payload["event"]["source_name"] == "source-a"
    assert result.payload["theme_relations"][0]["subject_key"] == "ar_glasses"
    assert result.payload["theme_relations"][0]["evidence"] == {"summary": "new product"}
    event_record = result.source_records[0]
    relation_record = result.source_records[1]
    assert event_record.provenance["table"] == "news_event"
    assert event_record.provenance["read_boundary"] == "DatabaseGateway.get_news_event_for_match"
    assert relation_record.provenance["table"] == "event_subject_map"
    assert relation_record.provenance["read_boundary"] == "DatabaseGateway.get_event_subject_mappings_by_event_ids"


@pytest.mark.asyncio
async def test_unknown_event_returns_distinct_not_found_failure():
    adapter = DomainIntelligenceAdapter(database_gateway=FakeGateway(event=None), clock=FixedClock())

    result = await adapter.execute(_request(502))

    assert result.status == "error"
    assert result.data_state == "empty"
    assert result.payload == {}
    assert result.failures[0].code == "NOT_FOUND"
    assert result.source_records[0].status == "failed"


@pytest.mark.asyncio
async def test_event_storage_unavailable_is_not_empty_success():
    adapter = DomainIntelligenceAdapter(
        database_gateway=_gateway(event_error=ConnectionError("postgres unavailable")),
        clock=FixedClock(),
    )

    result = await adapter.execute(_request(501))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures[0].code == "UPSTREAM_UNAVAILABLE"
    assert result.failures[0].retryable is True


@pytest.mark.asyncio
async def test_malformed_event_returns_schema_mismatch():
    adapter = DomainIntelligenceAdapter(database_gateway=FakeGateway(event=["bad"]), clock=FixedClock())

    result = await adapter.execute(_request(501))

    assert result.status == "error"
    assert result.data_state == "empty"
    assert result.failures[0].code == "SCHEMA_MISMATCH"
    assert result.diagnostics["raw_type"] == "list"


@pytest.mark.asyncio
async def test_partial_event_retains_payload_and_reports_missing_fields():
    gateway = _gateway(event={"summary": None, "title": None, "source_name": None, "source_url": None})
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())

    result = await adapter.execute(_request(501))

    assert result.status == "partial"
    assert result.data_state == "normal"
    assert result.payload["event"]["event_id"] == 501
    assert result.payload["missing_fields"] == ["summary", "title", "source_name", "source_url"]
    assert result.source_records[0].status == "partial"


@pytest.mark.asyncio
async def test_relation_storage_failure_preserves_canonical_event_as_partial():
    adapter = DomainIntelligenceAdapter(
        database_gateway=_gateway(relation_error=ConnectionError("relation table unavailable")),
        clock=FixedClock(),
    )

    result = await adapter.execute(_request(501))

    assert result.status == "partial"
    assert result.payload["event"]["event_id"] == 501
    assert result.payload["theme_relations"] == []
    assert result.diagnostics["relation_state"] == "source_failure"
    assert result.source_records[0].status == "success"
    assert result.source_records[1].status == "failed"


@pytest.mark.asyncio
async def test_not_proven_enrichment_fields_are_excluded():
    gateway = _gateway(event={
        "entities": ["company"],
        "causal_claim": "causes growth",
        "evidence_set": ["evidence"],
        "raw_event_json": {"rich": True},
    })
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())

    result = await adapter.execute(_request(501))

    assert result.status == "success"
    rendered = str(result.to_dict())
    assert '"entities"' not in rendered
    assert '"causal_claim"' not in rendered
    assert '"evidence_set"' not in rendered
    assert '"raw_event_json"' not in rendered
    assert "related_symbols" in result.diagnostics["excluded_not_proven_fields"]


@pytest.mark.asyncio
async def test_event_id_is_stable_across_repeated_reads():
    gateway = _gateway()
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())

    first = await adapter.execute(_request(501))
    second = await adapter.execute(_request(501))

    assert first.payload["event"]["event_id"] == second.payload["event"]["event_id"] == 501
    assert first.payload == second.payload
    assert gateway.event_calls == [501, 501]
