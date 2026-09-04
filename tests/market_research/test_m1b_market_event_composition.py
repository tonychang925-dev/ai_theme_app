"""M1B focused composition regressions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
)
from stock_processing_service.application.services.market_research import (
    MarketEventCompositionDecision,
    MarketEventResearchComposer,
)


@dataclass(frozen=True)
class FakeCapabilityRequest:
    capability_request_id: str
    correlation_id: str
    capability_id: str
    requested_scope: str
    arguments: dict
    provenance: dict

    def to_canonical_dict(self):
        return {
            "capability_request_id": self.capability_request_id,
            "correlation_id": self.correlation_id,
            "capability_id": self.capability_id,
            "requested_scope": self.requested_scope,
            "arguments": self.arguments,
            "provenance": self.provenance,
        }


class FakeResearchAdapter:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls = []

    def build_request(self, context, *, correlation_id, capability_request_id):
        if self.error is not None:
            raise self.error
        self.calls.append((context, correlation_id, capability_request_id))
        return FakeCapabilityRequest(
            capability_request_id=capability_request_id,
            correlation_id=correlation_id,
            capability_id="research.event.enrich",
            requested_scope="research.enrich",
            arguments=dict(context),
            provenance={
                "contract_version": "market.event.read.v1",
                "market_event_id": context["event"]["event_id"],
                "source_trace_id": context["event"]["source_trace_id"],
            },
        )


def _event(**overrides):
    value = {
        "event_id": 501,
        "event_type": "product_launch",
        "summary": "Company released a new product.",
        "direction": 1,
        "confidence": 0.88,
        "occurred_at": "2026-09-03T09:30:00+08:00",
        "title": "Company released a new product",
        "source_category": "news",
        "source_name": "source-a",
        "source_url": "https://example.test/a",
        "source_trace_id": "news_event:901:product_launch",
        "news_id": 901,
    }
    value.update(overrides)
    return value


def _relation(**overrides):
    value = {
        "subject_key": "ar_glasses",
        "subject_name": "AR Glasses",
        "relation_type": "primary",
        "confidence": 0.93,
        "match_reason": "product maps to subject",
        "evidence": {"summary": "new product", "ordering": "stable"},
        "source": "theme_match_engine",
        "source_trace_id": "trace-map-1",
        "created_at": "2026-09-03T09:35:00+08:00",
        "updated_at": "2026-09-03T09:36:00+08:00",
        "run_id": "run-map-1",
    }
    value.update(overrides)
    return value


def _source_record(source_name="news_event", *, status="success", failure=None):
    return SourceRecord(
        source_type="database",
        source_name=source_name,
        source_ref=f"public.{source_name}",
        as_of="2026-09-03T09:30:00+08:00",
        observed_at="2026-09-04T11:30:00+08:00",
        freshness="source_timestamp_based",
        status=status,
        provenance={"database": "postgresql", "schema": "public", "table": source_name},
        failure=failure,
    )


def _envelope(
    *,
    event=None,
    relations=None,
    status="success",
    failures=None,
    diagnostics=None,
    source_records=None,
):
    event = _event() if event is None else event
    relations = [_relation()] if relations is None else relations
    relation_state = diagnostics.get("relation_state") if diagnostics else (
        "mapped" if relations else "empty_not_mapped"
    )
    default_records = [
        _source_record("news_event"),
        _source_record("event_subject_map"),
    ]
    return DomainObservationEnvelope(
        operation="market.event.read",
        status=status,
        data_state="normal" if status != "unavailable" else "empty",
        correlation_id="corr-market",
        provider_request_id="idem-market",
        observed_at="2026-09-04T11:30:00+08:00",
        payload={"event": event, "theme_relations": relations, "missing_fields": []},
        source_records=source_records if source_records is not None else default_records,
        failures=failures or [],
        diagnostics=diagnostics if diagnostics is not None else {"event_id": event.get("event_id"), "relation_state": relation_state},
        schema_version="1.0",
    )


def _failed_envelope(code, *, status="error"):
    retryable = code in {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE"}
    failure = SourceFailure(code=code, message=code, source_name="news_event", retryable=retryable)
    return DomainObservationEnvelope(
        operation="market.event.read",
        status=status,
        data_state="empty",
        correlation_id="corr-market",
        provider_request_id="idem-market",
        observed_at="2026-09-04T11:30:00+08:00",
        payload={},
        source_records=[_source_record("news_event", status="failed", failure=failure)],
        failures=[failure],
        diagnostics={"reason": code, "event_id": 501},
        schema_version="1.0",
    )


def test_a01_happy_path_projects_context_and_builds_governed_request():
    adapter = FakeResearchAdapter()

    result = MarketEventResearchComposer().compose(_envelope(), research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.BUILD_C1_REQUEST
    assert result.market_context["event"]["direction"] == "1"
    assert result.market_context["event"]["confidence"] == 0.88
    assert result.market_context["theme_relations"][0]["evidence"] == (
        '{"ordering":"stable","summary":"new product"}'
    )
    assert set(result.market_context["theme_relations"][0]) == {
        "subject_key", "subject_name", "relation_type", "confidence", "match_reason",
        "evidence", "source", "source_trace_id", "updated_at",
    }
    assert result.capability_request.capability_id == "research.event.enrich"
    assert result.capability_request.correlation_id == "corr-market"
    assert result.capability_request.arguments == result.market_context


def test_a02_successful_empty_relations_remain_explicit_not_unknown():
    adapter = FakeResearchAdapter()
    envelope = _envelope(relations=[], source_records=[_source_record("news_event")])

    result = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.BUILD_C1_REQUEST
    assert result.market_context["theme_relations"] == []
    assert result.market_envelope.diagnostics["relation_state"] == "empty_not_mapped"


def test_a03_qualified_market_partial_builds_with_retained_failure():
    adapter = FakeResearchAdapter()
    failure = SourceFailure(
        code="SCHEMA_MISMATCH",
        message="missing source-backed fields",
        source_name="news_event",
        retryable=False,
        details={"missing_fields": ["source_name"]},
    )
    envelope = _envelope(
        event=_event(source_name=None),
        status="partial",
        failures=[failure],
        source_records=[_source_record("news_event", status="partial", failure=failure)],
    )
    envelope.payload["missing_fields"] = ["source_name"]

    result = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.BUILD_WITH_PARTIAL_CONTEXT
    assert result.market_context["event"]["source_name"] is None
    assert result.market_envelope.failures == [failure]


def test_a04_relation_failure_builds_partial_without_reinterpreting_empty():
    adapter = FakeResearchAdapter()
    failure = SourceFailure(
        code="UPSTREAM_UNAVAILABLE",
        message="relation table unavailable",
        source_name="event_subject_map",
        retryable=True,
    )
    envelope = _envelope(
        relations=[],
        status="partial",
        failures=[failure],
        diagnostics={"relation_state": "source_failure"},
        source_records=[
            _source_record("news_event"),
            _source_record("event_subject_map", status="failed", failure=failure),
        ],
    )

    result = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.BUILD_WITH_PARTIAL_CONTEXT
    assert result.market_context["theme_relations"] == []
    assert result.market_envelope.diagnostics["relation_state"] == "source_failure"


@pytest.mark.parametrize("code", ["INVALID_ARGUMENT", "NOT_FOUND", "SCHEMA_MISMATCH"])
def test_a05_a07_market_error_stops_before_c1(code):
    adapter = FakeResearchAdapter()

    result = MarketEventResearchComposer().compose(_failed_envelope(code), research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.STOP_BEFORE_C1
    assert adapter.calls == []
    assert result.market_context is None
    assert result.capability_request is None
    assert result.market_envelope.failures[0].code == code


@pytest.mark.parametrize("code", ["UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE"])
def test_a06_market_unavailable_stops_before_c1(code):
    adapter = FakeResearchAdapter()

    result = MarketEventResearchComposer().compose(_failed_envelope(code, status="unavailable"), research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.STOP_BEFORE_C1
    assert adapter.calls == []
    assert result.market_envelope.failures[0].retryable is True


def test_a08_unknown_market_event_field_stops_before_c1():
    adapter = FakeResearchAdapter()
    event = _event(related_symbols=["000001.SZ"])

    result = MarketEventResearchComposer().compose(_envelope(event=event), research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.STOP_BEFORE_C1
    assert adapter.calls == []
    assert result.composition_failure.code == "SCHEMA_MISMATCH"
    assert "related_symbols" in result.composition_failure.message


def test_a09_missing_c1_required_field_stops_before_c1():
    adapter = FakeResearchAdapter()
    failure = SourceFailure(
        code="SCHEMA_MISMATCH",
        message="missing source-backed fields",
        source_name="news_event",
        details={"missing_fields": ["event_type"]},
    )
    envelope = _envelope(
        event=_event(event_type=None),
        status="partial",
        failures=[failure],
        source_records=[_source_record("news_event", status="partial", failure=failure)],
    )
    envelope.payload["missing_fields"] = ["event_type"]

    result = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)

    assert result.decision == MarketEventCompositionDecision.STOP_BEFORE_C1
    assert adapter.calls == []
    assert result.composition_failure.message == "event.event_type must be a non-blank string"


def test_a10_market_provenance_remains_outside_context_and_links_ids():
    adapter = FakeResearchAdapter()
    envelope = _envelope()

    result = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)
    rendered = result.to_dict()

    assert "source_records" not in result.market_context["event"]
    assert rendered["market_envelope"]["provider_request_id"] == "idem-market"
    assert rendered["market_envelope"]["observed_at"] == "2026-09-04T11:30:00+08:00"
    assert result.projection_id.startswith("cap_req_m1b_")
    assert result.capability_request.capability_request_id == result.projection_id
    assert result.effective_correlation_id == "corr-market"


def test_a11_repeat_projection_is_deterministic_and_mints_only_missing_correlation():
    adapter = FakeResearchAdapter()
    envelope = _envelope()
    envelope_without_correlation = DomainObservationEnvelope(
        **{**envelope.__dict__, "correlation_id": ""}
    )

    first = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)
    second = MarketEventResearchComposer().compose(envelope, research_adapter=adapter)
    missing = MarketEventResearchComposer().compose(envelope_without_correlation, research_adapter=adapter)

    assert first.projection_id == second.projection_id
    assert first.market_context == second.market_context
    assert first.effective_correlation_id == "corr-market"
    assert missing.effective_correlation_id.startswith("m1b_corr_")
    assert missing.market_envelope.correlation_id == ""


def test_a12_composition_boundary_has_no_provider_or_authority_runtime():
    adapter = FakeResearchAdapter()
    result = MarketEventResearchComposer().compose(_envelope(), research_adapter=adapter)

    assert "verification_state" not in str(result.to_dict())
    assert adapter.calls
    source = Path("stock_processing_service/application/services/market_research/market_event_composition.py").read_text()
    forbidden = ["WebSearch", "WebFetch", "Claude", "julia_core", "ProviderExecutionOutcome", "ResearchEvidenceNormalizer"]
    assert all(item not in source for item in forbidden)
