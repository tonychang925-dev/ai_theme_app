"""AT-R4 HTTP/JSON transport tests.

TC-AT-R4-001: execute endpoint preserves success envelope round-trip.
TC-AT-R4-002: transport preserves partial/unavailable/error/stale semantics.
TC-AT-R4-003: health and readiness are separate.
TC-AT-R4-004: standalone client is Julia-free and package-free.
TC-AT-R4-005: api_app registers HTTP boundary without MCP or Julia imports.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.julia_domain_adapter.contracts import (  # noqa: E402
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
)
from stock_processing_service.ports.julia_domain_adapter_http import register_julia_domain_adapter_routes  # noqa: E402


class FakeAdapter:
    def __init__(self, response: DomainObservationEnvelope):
        self.response = response
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return self.response


def _app_with_adapter(response: DomainObservationEnvelope, *, workbench_base_dir: str | None = None) -> FastAPI:
    app = FastAPI()
    app.state.julia_domain_adapter = FakeAdapter(response)
    if workbench_base_dir is not None:
        app.state.julia_domain_adapter_workbench_base_dir = workbench_base_dir
    register_julia_domain_adapter_routes(app)
    return app


def _request(operation: str = "market.snapshot") -> dict:
    return {
        "operation": operation,
        "arguments": {"trade_date": "2026-08-26"},
        "correlation_id": "corr-http-001",
        "idempotency_key": "idem-http-001",
        "requested_at": "2026-08-26T10:00:00+08:00",
        "schema_version": "1.0",
        "trace_metadata": {"turn_id": "opaque"},
    }


def _envelope(*, status="success", data_state="normal", operation="market.snapshot", failures=None, source_records=None) -> DomainObservationEnvelope:
    return DomainObservationEnvelope(
        operation=operation,
        status=status,
        data_state=data_state,
        correlation_id="corr-http-001",
        provider_request_id="idem-http-001",
        observed_at="2026-08-26T15:30:00+08:00",
        payload={"themes": [{"subject_key": "theme-ai"}], "market_state": {"theme_count": 1}} if data_state != "empty" else {},
        source_records=source_records or [SourceRecord(
            source_type="database",
            source_name="theme_cycle_judgement_v2",
            source_ref="trade_date=2026-08-26",
            as_of="2026-08-26",
            observed_at="2026-08-26T15:30:00+08:00",
            freshness="stale" if data_state == "stale" else "fresh",
            status="success",
            provenance={"row_count": 1},
        )],
        failures=failures or [],
        diagnostics={},
        schema_version="1.0",
    )


def test_tc_at_r4_001_execute_endpoint_preserves_success_round_trip():
    envelope = _envelope()
    app = _app_with_adapter(envelope)
    client = TestClient(app)

    response = client.post("/adapter/v1/execute", json=_request())

    assert response.status_code == 200
    assert response.json() == envelope.to_dict()
    assert app.state.julia_domain_adapter.requests[0].correlation_id == "corr-http-001"


def test_tc_at_r4_002_transport_preserves_degraded_and_stale_semantics():
    cases = [
        _envelope(
            status="partial",
            data_state="normal",
            failures=[SourceFailure(code="UPSTREAM_UNAVAILABLE", message="redis unavailable", source_name="redis_alert_stream", retryable=True)],
            source_records=[
                SourceRecord(source_type="database", source_name="theme_cycle_judgement_v2", source_ref="ok", as_of="2026-08-26", observed_at="2026-08-26T15:30:00+08:00", freshness="fresh", status="success", provenance={"row_count": 1}),
                SourceRecord(source_type="redis", source_name="redis_alert_stream", source_ref="stream", as_of="2026-08-26", observed_at="2026-08-26T15:30:00+08:00", freshness="fresh", status="failed", provenance={}, failure=SourceFailure(code="UPSTREAM_UNAVAILABLE", message="redis unavailable", source_name="redis_alert_stream", retryable=True)),
            ],
        ),
        _envelope(status="unavailable", data_state="empty", failures=[SourceFailure(code="UPSTREAM_UNAVAILABLE", message="db unavailable", source_name="postgres", retryable=True)], source_records=[]),
        _envelope(status="error", data_state="empty", failures=[SourceFailure(code="INTERNAL_ERROR", message="provider failed", source_name="adapter")], source_records=[]),
        _envelope(status="success", data_state="stale"),
    ]

    for envelope in cases:
        client = TestClient(_app_with_adapter(envelope))
        response = client.post("/adapter/v1/execute", json=_request(envelope.operation))
        body = response.json()
        assert response.status_code == 200
        assert body["status"] == envelope.status
        assert body["data_state"] == envelope.data_state
        assert body["source_records"] == [record.to_dict() for record in envelope.source_records]
        assert body["failures"] == [failure.to_dict() for failure in envelope.failures]
        assert body["schema_version"] == "1.0"
        assert not (envelope.status in {"partial", "unavailable", "error"} and body["status"] == "success")
        assert not (envelope.data_state == "stale" and any(record.get("freshness") == "fresh" for record in body["source_records"]))


def test_tc_at_r4_003_health_and_readiness_are_separate(tmp_path):
    app = FastAPI()
    app.state.julia_domain_adapter_workbench_base_dir = str(tmp_path / "missing_workbench")
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)

    health = client.get("/adapter/v1/health").json()
    ready = client.get("/adapter/v1/ready").json()

    assert health["ok"] is True
    assert health["ready"] is True
    assert ready["ok"] is True
    assert ready["ready"] is False
    assert ready["status"] == "not_ready"
    assert ready["failures"]


def test_tc_at_r4_004_execute_rejects_malformed_request_without_schema_change():
    client = TestClient(_app_with_adapter(_envelope()))
    response = client.post("/adapter/v1/execute", json={"operation": "market.snapshot", "schema_version": "1.0"})

    assert response.status_code == 400
    assert response.json()["detail"]["schema_version"] == "1.0"


def test_tc_at_r4_005_standalone_client_has_no_julia_or_ai_theme_imports():
    path = ROOT / "scripts" / "julia_domain_adapter_client.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"julia_core", "julia_ai_assistant", "stock_processing_service", "mcp_server"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden


def test_tc_at_r4_006_api_app_registers_transport_without_julia_or_mcp_imports():
    api_text = (ROOT / "stock_processing_service" / "api_app.py").read_text(encoding="utf-8")
    assert "register_julia_domain_adapter_routes(app)" in api_text

    transport_text = (ROOT / "stock_processing_service" / "ports" / "julia_domain_adapter_http.py").read_text(encoding="utf-8")
    assert "julia_core" not in transport_text
    assert "julia_ai_assistant" not in transport_text
    assert "mcp_server" not in transport_text
    assert "AuthorizationDecision" not in transport_text
