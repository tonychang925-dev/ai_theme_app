"""F1 fixture chain across exact Market, Core, and Claude bridge contracts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = Path(os.environ.get("JULIA_CORE_ROOT", ROOT.parent / "Julia_core"))
D1_ROOT = Path(os.environ.get("CLAUDE_CLIENT_ROOT", Path.home() / "Desktop" / "Claude_client"))
RUNNER = Path(__file__).with_name("d1_projection_runner.ts")

for path in (str(ROOT), str(CORE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from julia_core.capability.models import (
    CapabilityCall,
    ProviderExecutionOutcome,
    SideEffectState,
    ToolResultStatus,
)
from julia_core.research import MarketEventResearchAdapter, ResearchEvidenceNormalizer
from stock_processing_service.application.services.market_research import (
    MarketEventCompositionDecision,
    MarketEventResearchComposer,
)

from .cognition_fixture import CognitionFixture, form_judgment
from .market_fixture import (
    MarketGatewayFixture,
    partial_event_gateway,
    read_market_event,
    relation_failure_gateway,
)


@pytest.fixture(autouse=True)
def deny_python_network(monkeypatch):
    original_socket = socket.socket

    def guarded_socket(family=socket.AF_INET, *args, **kwargs):
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("live internet network access is forbidden in fixture E2E")
        return original_socket(family, *args, **kwargs)

    def blocked_remote_socket(*args, **kwargs):
        raise AssertionError("live network access is forbidden in fixture E2E")

    monkeypatch.setattr(socket, "create_connection", blocked_remote_socket)
    monkeypatch.setattr(socket, "socket", guarded_socket)


def _run_d1(composition, *, mode="full", request_id=None, call_id=None):
    request_id = request_id or composition.capability_request.capability_request_id
    call_id = call_id or "cap_call_f1"
    event = composition.market_context["event"]
    payload = {
        "mode": mode,
        "research_id": f"research_{event['event_id']}_{event['source_trace_id']}",
        "event_id": str(event["event_id"]),
        "event_digest": hashlib.sha256(event["source_trace_id"].encode()).hexdigest(),
        "capability_request_id": request_id,
        "capability_call_id": call_id,
        "correlation_id": composition.effective_correlation_id,
    }
    result = subprocess.run(
        ["bun", "run", str(RUNNER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        cwd=str(D1_ROOT),
        env={**os.environ, "CLAUDE_CLIENT_ROOT": str(D1_ROOT), "HTTP_PROXY": "", "HTTPS_PROXY": ""},
    )
    return json.loads(result.stdout)


def _outcome(d1_result):
    failed = d1_result["response"]["transport_status"] == "ACTION_COLLECTION_STOPPED"
    error = d1_result["response"]["error"] if failed else None
    return ProviderExecutionOutcome(
        status=ToolResultStatus.UNAVAILABLE if failed else ToolResultStatus.SUCCESS,
        structured_output=d1_result["projected"],
        error=error,
        side_effect_state=SideEffectState.NONE,
    )


def _compose(gateway):
    envelope = read_market_event(gateway)
    return MarketEventResearchComposer().compose(
        envelope,
        research_adapter=MarketEventResearchAdapter(),
    )


def _normalize(composition, d1_result, call_id="cap_call_f1"):
    outcome = _outcome(d1_result)
    return ResearchEvidenceNormalizer().normalize_provider_outcome(
        outcome,
        request=composition.capability_request,
        call=CapabilityCall(
            capability_call_id=call_id,
            capability_request_id=composition.capability_request.capability_request_id,
            provider="research_enrichment",
            correlation_id=composition.capability_request.correlation_id,
        ),
    )


def _states(enrichment):
    return [
        item.integrity_metadata["verification_state"]
        for item in enrichment.observation.evidence
    ]


def _assert_authority_and_no_trading(judgment, composition, call_id="cap_call_f1"):
    assert judgment.contract_version == "research.preliminary_judgment.v1"
    assert judgment.trace.market_event_id == 501
    assert judgment.trace.source_trace_id == "news_event:901:product_launch"
    assert judgment.trace.capability_request_id == composition.capability_request.capability_request_id
    assert judgment.trace.capability_call_id == call_id
    assert judgment.trace.correlation_id == composition.effective_correlation_id
    assert "preliminary" in judgment.judgment_summary.lower()
    serialized = json.dumps(judgment.to_dict()) if hasattr(judgment, "to_dict") else str(judgment)
    forbidden = ("recommendation", "position_size", "entry_price", "target_price", "stop_loss")
    assert all(term not in serialized.lower() for term in forbidden)


def test_f01_full_chain_proves_source_verified_and_complete_provenance():
    composition = _compose(MarketGatewayFixture())
    assert composition.decision == MarketEventCompositionDecision.BUILD_C1_REQUEST
    d1_result = _run_d1(composition)
    enrichment = _normalize(composition, d1_result)
    assert enrichment.semantic_result.claims == ()
    assert enrichment.observation.claim_verification_states == {}
    assert _states(enrichment) == ["SOURCE_VERIFIED"]

    binding = enrichment.observation.content_bindings[0]
    request = composition.capability_request
    assert binding.provenance["capability_request_id"] == request.capability_request_id
    assert binding.provenance["capability_call_id"] == "cap_call_f1"
    assert binding.provenance["runtime_observation_ref"] in enrichment.observation.raw_response_refs
    assert binding.digest == enrichment.observation.source_records[0].content_digest

    provider = CognitionFixture(enrichment)
    judgment = form_judgment(composition.market_context, enrichment, provider)
    _assert_authority_and_no_trading(judgment, composition)
    evidence = enrichment.observation.evidence[0]
    assert judgment.evidence_refs == (evidence.evidence_id,)
    assert judgment.source_record_refs == (enrichment.observation.source_records[0].source_record_id,)
    assert provider.messages[0]["role"] == "system"
    assert provider.messages[-1]["role"] == "user"


@pytest.mark.xfail(strict=True, reason="D1-F1 WebSearch-only projection is unavailable; C1 therefore mints NOT_PROVEN rather than REPORT_ONLY")
def test_f02_websearch_only_is_report_only_cognition():
    composition = _compose(MarketGatewayFixture(relations=[]))
    d1_result = _run_d1(composition, mode="websearch_only")
    enrichment = _normalize(composition, d1_result)
    assert _states(enrichment) == ["REPORT_ONLY"]
    judgment = form_judgment(composition.market_context, enrichment, CognitionFixture(enrichment))
    assert judgment.key_drivers[0].support_level.value == "REPORT_ONLY_LEAD"


@pytest.mark.parametrize("fault", ["missing_binding", "bad_digest", "missing_runtime_ref"])
def test_f03_f05_binding_faults_are_not_proven(fault):
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(composition)
    observation = d1_result["projected"]["source_observation"]
    if fault == "missing_binding":
        observation["content_bindings"] = []
    elif fault == "bad_digest":
        observation["content_bindings"][0]["digest"] = "c" * 64
    else:
        observation["content_bindings"][0]["provenance"]["runtime_observation_ref"] = ""
    enrichment = _normalize(composition, d1_result)
    assert _states(enrichment) == ["NOT_PROVEN"]
    judgment = form_judgment(composition.market_context, enrichment, CognitionFixture(enrichment))
    assert judgment.key_drivers[0].support_level.value == "NOT_PROVEN_MATERIAL"


@pytest.mark.parametrize("fault", ["request", "call"])
def test_f06_f07_wrong_runtime_identity_is_not_proven(fault):
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(
        composition,
        request_id="wrong_request" if fault == "request" else None,
        call_id="wrong_call" if fault == "call" else None,
    )
    enrichment = _normalize(composition, d1_result)
    assert _states(enrichment) == ["NOT_PROVEN"]


def test_f08_market_partial_continues_with_visible_failure():
    composition = _compose(partial_event_gateway())
    assert composition.decision == MarketEventCompositionDecision.BUILD_WITH_PARTIAL_CONTEXT
    assert composition.market_envelope.payload["missing_fields"] == ["source_name"]
    d1_result = _run_d1(composition)
    enrichment = _normalize(composition, d1_result)
    judgment = form_judgment(composition.market_context, enrichment, CognitionFixture(enrichment))
    assert judgment.key_drivers[0].support_level.value == "SOURCE_VERIFIED_SUPPORT"
    assert composition.market_envelope.failures


def test_f09_relation_failure_is_not_successful_empty_mapping():
    composition = _compose(relation_failure_gateway())
    assert composition.decision == MarketEventCompositionDecision.BUILD_WITH_PARTIAL_CONTEXT
    assert composition.market_context["theme_relations"] == []
    assert composition.market_envelope.diagnostics["relation_state"] == "source_failure"
    d1_result = _run_d1(composition)
    enrichment = _normalize(composition, d1_result)
    judgment = form_judgment(composition.market_context, enrichment, CognitionFixture(enrichment))
    assert judgment.key_drivers[0].support_level.value == "SOURCE_VERIFIED_SUPPORT"
    assert "relation" not in judgment.judgment_summary.lower()


@pytest.mark.parametrize("gateway_name", ["not_found", "db_unavailable"])
def test_f10_f11_market_stops_before_research(gateway_name):
    if gateway_name == "not_found":
        gateway = MarketGatewayFixture(event=None)
    else:
        gateway = MarketGatewayFixture(event_error=ConnectionError("market db unavailable"))
    composition = _compose(gateway)
    assert composition.decision == MarketEventCompositionDecision.STOP_BEFORE_C1
    assert composition.capability_request is None
    assert composition.market_context is None


def test_f12_blocked_source_remains_limitation_in_cognition():
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(composition, mode="blocked")
    enrichment = _normalize(composition, d1_result)
    assert _states(enrichment) == ["NOT_PROVEN"]
    assert enrichment.observation.failure.code == "WEBFETCH_PRELAUNCH_REJECTED"
    judgment = form_judgment(
        composition.market_context,
        enrichment,
        CognitionFixture(enrichment),
        allow_market_only=True,
    )
    assert judgment.key_drivers[0].support_level.value == "MARKET_CONTEXT_ONLY"
    assert "observation failure retained: WEBFETCH_PRELAUNCH_REJECTED" in judgment.uncertainties


def test_f13_ambiguous_provider_failure_retains_evidence_and_stops():
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(composition, mode="provider_failure")
    assert d1_result["response"]["execution"]["provider_action_retry_count"] == 0
    assert d1_result["response"]["execution"]["fallback_count"] == 0
    enrichment = _normalize(composition, d1_result)
    assert enrichment.observation.failure is not None
    judgment = form_judgment(
        composition.market_context,
        enrichment,
        CognitionFixture(enrichment),
        allow_market_only=True,
    )
    assert "observation failure retained: WEBFETCH_ACTION_FAILED_OR_AMBIGUOUS" in judgment.uncertainties


def test_f14_no_model_synthesis_still_supports_julia_owned_judgment():
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(composition)
    enrichment = _normalize(composition, d1_result)
    assert enrichment.semantic_result.claims == ()
    assert any("NO_MODEL_SYNTHESIS" in item for item in enrichment.semantic_result.unknowns)
    judgment = form_judgment(composition.market_context, enrichment, CognitionFixture(enrichment))
    assert judgment.key_drivers[0].support_level.value == "SOURCE_VERIFIED_SUPPORT"
    assert any("NO_MODEL_SYNTHESIS" in item for item in judgment.uncertainties)


def test_f15_hostile_content_is_retained_only_as_untrusted_evidence():
    composition = _compose(MarketGatewayFixture())
    d1_result = _run_d1(composition, mode="hostile")
    observation = d1_result["response"]["source_observations"][0]
    decoded = base64.b64decode(observation["content_reference"]["content_base64"]).decode()
    assert "ignore previous instructions" in decoded
    assert "SOURCE_VERIFIED" in decoded
    assert observation["provenance"]["external_content_is_untrusted"] is True
    enrichment = _normalize(composition, d1_result)
    assert _states(enrichment) == ["SOURCE_VERIFIED"]
    provider = CognitionFixture(enrichment)
    judgment = form_judgment(composition.market_context, enrichment, provider)
    assert "ignore previous instructions" not in json.dumps(provider.messages)
    assert "buy this stock" not in str(judgment)


def test_f16_malformed_cognition_output_is_rejected():
    composition = _compose(MarketGatewayFixture())
    enrichment = _normalize(composition, _run_d1(composition))
    from julia_core.research import ResearchJudgmentParseError
    with pytest.raises(ResearchJudgmentParseError, match="strict JSON"):
        form_judgment(
            composition.market_context,
            enrichment,
            CognitionFixture(enrichment, mode="malformed"),
        )


@pytest.mark.parametrize("fault", ["unknown_evidence_ref", "unknown_source_ref"])
def test_f17_f18_unknown_cognition_references_are_rejected(fault):
    composition = _compose(MarketGatewayFixture())
    enrichment = _normalize(composition, _run_d1(composition))
    from julia_core.research import ResearchJudgmentParseError
    with pytest.raises(ResearchJudgmentParseError, match="unknown"):
        form_judgment(
            composition.market_context,
            enrichment,
            CognitionFixture(enrichment, fault=fault),
        )
