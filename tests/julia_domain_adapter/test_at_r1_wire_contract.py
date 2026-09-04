"""AT-R1 Wire Contract tests for provider-native Julia Domain Adapter.

TC-AT-R1-001: request/envelope round-trip.
TC-AT-R1-002: supported operation and schema-version validation.
TC-AT-R1-003: status/data_state invariants.
TC-AT-R1-004: golden fixture compatibility.
TC-AT-R1-005: source failure and diagnostics redaction.
TC-AT-R1-006: no Julia import or natural-language dispatch surface.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    ADAPTER_SCHEMA_VERSION,
    SUPPORTED_OPERATIONS,
    AdapterErrorCode,
    AdapterRequest,
    AdapterStatus,
    DataState,
    DomainObservationEnvelope,
    SourceFailure,
    ValidationError,
    redact_diagnostics,
)

FIXTURE_DIR = ROOT / "docs" / "integration" / "fixtures" / "julia_domain_adapter"
CONTRACT_DIR = ROOT / "stock_processing_service" / "application" / "services" / "julia_domain_adapter"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_tc_at_r1_001_adapter_request_round_trips_correlation_metadata():
    raw = _load_fixture("adapter_request_market_snapshot.json")
    req = AdapterRequest.from_dict(raw)

    assert req.operation == "market.snapshot"
    assert req.schema_version == ADAPTER_SCHEMA_VERSION
    assert req.trace_metadata["turn_id"] == "opaque-turn-id"
    assert req.to_dict() == raw


def test_tc_at_r1_002_rejects_unsupported_operation_and_schema_version():
    with pytest.raises(ValidationError, match="unsupported operation"):
        AdapterRequest.from_dict({
            "operation": "market.intent.resolve",
            "arguments": {},
            "schema_version": "1.0",
        })

    with pytest.raises(ValidationError, match="unsupported schema_version"):
        AdapterRequest.from_dict({
            "operation": "market.snapshot",
            "arguments": {},
            "schema_version": "2.0",
        })

    assert SUPPORTED_OPERATIONS == {"market.snapshot", "market.alerts", "market.event.read", "market.event.resolve"}


def test_tc_at_r1_003_status_and_data_state_invariants_are_enforced():
    # Legitimate empty result is success + empty + no failures.
    empty = DomainObservationEnvelope.from_dict(_load_fixture("market_snapshot_empty.json"))
    assert empty.status == AdapterStatus.SUCCESS.value
    assert empty.data_state == DataState.EMPTY.value
    assert empty.failures == []

    # Dependency failure must not be represented as success + empty.
    with pytest.raises(ValidationError, match="status=success must not include failures"):
        DomainObservationEnvelope(
            operation="market.snapshot",
            status="success",
            data_state="empty",
            payload={},
            failures=[SourceFailure(
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                message="db failed",
                source_name="postgres",
                retryable=True,
            )],
        )

    with pytest.raises(ValidationError, match="status=partial requires"):
        DomainObservationEnvelope(
            operation="market.snapshot",
            status="partial",
            data_state="normal",
            payload={"market_state": {}},
        )

    with pytest.raises(ValidationError, match="requires at least one explicit failure"):
        DomainObservationEnvelope(
            operation="market.snapshot",
            status="unavailable",
            data_state="empty",
            payload={},
        )


def test_tc_at_r1_004_all_golden_response_fixtures_parse_and_round_trip():
    fixture_names = [
        "market_snapshot_success.json",
        "market_snapshot_partial.json",
        "market_snapshot_unavailable.json",
        "market_snapshot_error.json",
        "market_snapshot_empty.json",
        "market_snapshot_stale.json",
        "market_alerts_success.json",
        "market_alerts_empty.json",
    ]

    for name in fixture_names:
        raw = _load_fixture(name)
        envelope = DomainObservationEnvelope.from_dict(raw)
        assert envelope.schema_version == "1.0", name
        assert envelope.operation in SUPPORTED_OPERATIONS, name
        assert envelope.status in {item.value for item in AdapterStatus}, name
        assert envelope.data_state in {item.value for item in DataState}, name
        assert envelope.to_dict() == raw, name


def test_tc_at_r1_005_secret_like_values_are_redacted_in_failures_and_diagnostics():
    failure = SourceFailure(
        code="UPSTREAM_UNAVAILABLE",
        message="connect postgresql://user:supersecret@localhost/db failed token=abc123",
        source_name="postgres",
        details={
            "DATABASE_URL": "postgresql://user:supersecret@localhost/db",
            "api_token": "abc123",
            "safe": "value",
        },
    )
    payload = failure.to_dict()

    assert "supersecret" not in json.dumps(payload)
    assert "abc123" not in json.dumps(payload)
    assert payload["details"]["api_token"] == "***"
    assert payload["details"]["safe"] == "value"

    redacted = redact_diagnostics({"error": "redis://:pw@localhost/0 password=hunter2"})
    assert "pw" not in json.dumps(redacted)
    assert "hunter2" not in json.dumps(redacted)


def test_tc_at_r1_006_contract_module_has_no_julia_import_or_nlp_dispatch_surface():
    forbidden_import_roots = {"julia_core", "julia_ai_assistant"}
    forbidden_names = {"user_text", "natural_language", "intent_resolver", "semantic_router", "market_intent_resolve"}

    for path in CONTRACT_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in forbidden_import_roots, f"forbidden import {alias.name} in {path}"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden_import_roots, f"forbidden import from {node.module} in {path}"
            elif isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"forbidden NLP dispatch name {node.id} in {path}"

    text = "\n".join(p.read_text(encoding="utf-8") for p in CONTRACT_DIR.glob("*.py"))
    assert "market.intent.resolve" not in text
    assert "CapabilityRequest" not in text
    assert "ToolResult" not in text
    assert "Evidence" not in text


def test_tc_at_r1_007_missing_required_fields_are_rejected():
    request = _load_fixture("adapter_request_market_snapshot.json")
    for field in ("operation", "arguments", "schema_version"):
        broken = dict(request)
        broken.pop(field)
        with pytest.raises(ValidationError, match="missing required fields"):
            AdapterRequest.from_dict(broken)

    envelope = _load_fixture("market_snapshot_success.json")
    for field in ("operation", "status", "data_state", "payload", "source_records", "failures", "schema_version"):
        broken = dict(envelope)
        broken.pop(field)
        with pytest.raises(ValidationError, match="missing required fields"):
            DomainObservationEnvelope.from_dict(broken)


def test_tc_at_r1_008_malformed_arguments_and_payload_shapes_are_rejected():
    with pytest.raises(ValidationError, match="arguments must be an object"):
        AdapterRequest.from_dict({
            "operation": "market.snapshot",
            "arguments": ["not", "an", "object"],
            "schema_version": "1.0",
        })

    with pytest.raises(ValidationError, match="payload must be an object"):
        DomainObservationEnvelope.from_dict({
            "operation": "market.snapshot",
            "status": "success",
            "data_state": "normal",
            "payload": ["not", "an", "object"],
            "source_records": [],
            "failures": [],
            "schema_version": "1.0",
        })

    with pytest.raises(ValidationError):
        DomainObservationEnvelope.from_dict({
            "operation": "market.snapshot",
            "status": "success",
            "data_state": "normal",
            "payload": {},
            "source_records": ["not-an-object"],
            "failures": [],
            "schema_version": "1.0",
        })


def test_tc_at_r1_009_complete_status_data_state_matrix_is_enforced():
    failure = SourceFailure(
        code="UPSTREAM_UNAVAILABLE",
        message="source unavailable",
        source_name="postgres",
        retryable=True,
    )

    legal = {
        ("success", "normal", False),
        ("success", "empty", False),
        ("success", "stale", False),
        ("partial", "normal", True),
        ("partial", "stale", True),
        ("unavailable", "empty", True),
        ("error", "empty", True),
    }

    for status in (item.value for item in AdapterStatus):
        for data_state in (item.value for item in DataState):
            for with_failure in (False, True):
                kwargs = {
                    "operation": "market.snapshot",
                    "status": status,
                    "data_state": data_state,
                    "payload": {"value": "x"} if data_state != "empty" else {},
                    "source_records": [],
                    "failures": [failure] if with_failure else [],
                }
                if (status, data_state, with_failure) in legal:
                    DomainObservationEnvelope(**kwargs)
                else:
                    with pytest.raises(ValidationError):
                        DomainObservationEnvelope(**kwargs)


def test_tc_at_r1_010_source_failure_round_trip_and_error_code_catalog():
    expected_codes = {
        "INVALID_ARGUMENT",
        "OPERATION_NOT_SUPPORTED",
        "NOT_FOUND",
        "UPSTREAM_TIMEOUT",
        "UPSTREAM_UNAVAILABLE",
        "SCHEMA_MISMATCH",
        "INTERNAL_ERROR",
    }
    assert {item.value for item in AdapterErrorCode} == expected_codes

    raw = {
        "code": "UPSTREAM_TIMEOUT",
        "message": "query timed out",
        "source_name": "money_flow_enhanced",
        "retryable": True,
        "details": {"timeout_ms": 1500},
    }
    failure = SourceFailure.from_dict(raw)
    assert failure.to_dict() == raw

    with pytest.raises(ValidationError, match="invalid failure.code"):
        SourceFailure.from_dict({"code": "NOT_A_CODE", "message": "bad"})


def test_tc_at_r1_011_stale_fixture_has_explicit_stale_semantics():
    raw = _load_fixture("market_snapshot_stale.json")
    envelope = DomainObservationEnvelope.from_dict(raw)

    assert envelope.status == "success"
    assert envelope.data_state == "stale"
    assert envelope.failures == []
    assert envelope.source_records
    assert all(record.freshness == "stale" for record in envelope.source_records)
    assert envelope.diagnostics["requested_trade_date"] != envelope.source_records[0].as_of
