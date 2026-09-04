"""AT-R5 Contract + Fault Injection Matrix.

TC-AT-R5-001..018 cover the minimum 18-case acceptance matrix.
TC-AT-R5-HTTP covers transport fault-injection invariants.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
    ValidationError,
)
from stock_processing_service.ports.julia_domain_adapter_http import register_julia_domain_adapter_routes

CST = timezone(timedelta(hours=8))
SCHEMA_PATH = ROOT / "docs" / "integration" / "JULIA_ADAPTER_SCHEMA_v1.json"
FIXTURE_DIR = ROOT / "docs" / "integration" / "fixtures" / "julia_domain_adapter"
EXPECTED_RESPONSE_FIXTURES = {
    "market_alerts_empty.json",
    "market_alerts_success.json",
    "market_snapshot_empty.json",
    "market_snapshot_error.json",
    "market_snapshot_partial.json",
    "market_snapshot_stale.json",
    "market_snapshot_success.json",
    "market_snapshot_unavailable.json",
}
REQUIRED_REQUEST_EXAMPLES = {"adapter_request_market_snapshot.json"}
ALLOWED_ADDITIVE_REQUEST_EXAMPLES = {"adapter_request_market_alerts.json"}
EXPECTED_SCHEMA_SHA256 = "ff8c45f06f8f10a4deb5023e90bca5ac41d8697a3c337216d48aa30c0bbb81f4"


class FixedClock:
    def now(self):
        return datetime(2026, 8, 26, 15, 30, tzinfo=CST)


class FakeExporter:
    def __init__(self, result=None, exc: BaseException | None = None):
        self.result = result
        self.exc = exc

    async def export(self, trade_date: str):
        if self.exc:
            raise self.exc
        return self.result


class FakeHttpAdapter:
    def __init__(self, response: DomainObservationEnvelope):
        self.response = response

    async def execute(self, request):
        return self.response


def _req(operation="market.snapshot", args=None):
    return AdapterRequest(
        operation=operation,
        arguments=args or {"trade_date": "2026-08-26"},
        correlation_id="corr-at-r5",
        idempotency_key="idem-at-r5",
        requested_at="2026-08-26T10:00:00+08:00",
        schema_version="1.0",
        trace_metadata={"trace": "opaque"},
    )


def _snapshot_payload(**overrides):
    data = {
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-08-26",
        "status": "live",
        "market_state": {"theme_count": 1},
        "themes": [{"subject_key": "theme-ai"}],
        "quality": {"coverage": 1.0},
        "source_records": [{
            "source_type": "database",
            "source_name": "theme_cycle_judgement_v2",
            "source_ref": "trade_date=2026-08-26",
            "as_of": "2026-08-26",
            "freshness": "fresh",
            "status": "success",
            "provenance": {"row_count": 1},
        }],
    }
    data.update(overrides)
    return data


async def _execute_snapshot(result=None, exc=None):
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(result, exc), clock=FixedClock())
    return await adapter.execute(_req("market.snapshot"))


@pytest.mark.asyncio
async def test_tc_at_r5_001_snapshot_normal_success():
    result = await _execute_snapshot(_snapshot_payload())
    assert (result.status, result.data_state) == ("success", "normal")


@pytest.mark.asyncio
async def test_tc_at_r5_002_alerts_normal_success_covered_by_facade_fixture(tmp_path):
    from tests.julia_domain_adapter.test_at_r2_domain_adapter_facade import _write_approved_snapshot
    _write_approved_snapshot(tmp_path, attention_level="HIGH")
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())
    result = await adapter.execute(_req("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))
    assert (result.status, result.data_state) == ("success", "normal")


@pytest.mark.asyncio
async def test_tc_at_r5_003_optional_source_failure_to_partial():
    result = await _execute_snapshot(_snapshot_payload(status="partial", missing_sources=["money_flow_enhanced"]))
    assert result.status == "partial"
    assert result.failures[0].source_name == "money_flow_enhanced"


@pytest.mark.asyncio
async def test_tc_at_r5_004_required_dependency_failure_to_unavailable():
    result = await _execute_snapshot(None, ConnectionError("database down"))
    assert (result.status, result.data_state) == ("unavailable", "empty")
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_tc_at_r5_005_provider_exception_to_error():
    result = await _execute_snapshot(None, RuntimeError("provider bug"))
    assert (result.status, result.data_state) == ("error", "empty")
    assert result.failures[0].code == AdapterErrorCode.INTERNAL_ERROR.value


@pytest.mark.asyncio
async def test_tc_at_r5_006_provider_exception_is_not_success_empty():
    result = await _execute_snapshot(None, RuntimeError("provider bug"))
    assert not (result.status == "success" and result.data_state == "empty")


@pytest.mark.asyncio
async def test_tc_at_r5_007_legitimate_no_data_success_empty():
    result = await _execute_snapshot(_snapshot_payload(market_state={}, themes=[]))
    assert (result.status, result.data_state) == ("success", "empty")
    assert result.failures == []
    assert result.source_records[0].status == "success"


@pytest.mark.asyncio
async def test_tc_at_r5_008_stale_source_explicit():
    result = await _execute_snapshot(_snapshot_payload(trade_date="2026-08-25", freshness="stale"))
    assert result.data_state == "stale"
    assert all(record.freshness == "stale" for record in result.source_records)


@pytest.mark.asyncio
async def test_tc_at_r5_009_upstream_timeout():
    result = await _execute_snapshot(None, TimeoutError("slow"))
    assert (result.status, result.data_state) == ("unavailable", "empty")
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_TIMEOUT.value


def test_tc_at_r5_010_unsupported_operation():
    with pytest.raises(ValidationError):
        AdapterRequest.from_dict({"operation": "market.intent.resolve", "arguments": {}, "schema_version": "1.0"})


def test_tc_at_r5_011_malformed_arguments():
    with pytest.raises(ValidationError):
        AdapterRequest.from_dict({"operation": "market.snapshot", "arguments": [], "schema_version": "1.0"})


def test_tc_at_r5_012_correlation_metadata_round_trip():
    raw = json.loads((FIXTURE_DIR / "adapter_request_market_snapshot.json").read_text(encoding="utf-8"))
    assert AdapterRequest.from_dict(raw).to_dict() == raw


def test_tc_at_r5_013_unsupported_schema_version():
    with pytest.raises(ValidationError):
        AdapterRequest.from_dict({"operation": "market.snapshot", "arguments": {}, "schema_version": "9.9"})


def test_tc_at_r5_014_health_vs_readiness(tmp_path):
    app = FastAPI()
    app.state.julia_domain_adapter_workbench_base_dir = str(tmp_path / "missing")
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)
    assert client.get("/adapter/v1/health").json()["ready"] is True
    assert client.get("/adapter/v1/ready").json()["ready"] is False


def test_tc_at_r5_015_secret_redaction():
    failure = SourceFailure(
        code="UPSTREAM_UNAVAILABLE",
        message="postgresql://user:secret@localhost/db token=abc",
        source_name="postgres",
        details={"PASSWORD": "secret", "safe": "ok"},
    )
    serialized = json.dumps(failure.to_dict())
    assert "secret" not in serialized
    assert "abc" not in serialized
    assert failure.to_dict()["details"]["safe"] == "ok"


def test_tc_at_r5_016_deterministic_dispatch_no_nlp_routing_surface():
    package = ROOT / "stock_processing_service" / "application" / "services" / "julia_domain_adapter"
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.rglob("*.py"))
    forbidden = ["user_text", "natural_language", "semantic_router", "intent_resolver", "market.intent.resolve"]
    for item in forbidden:
        assert item not in text


def test_tc_at_r5_017_no_write_side_effects(tmp_path):
    from tests.julia_domain_adapter.test_at_r2_domain_adapter_facade import _write_approved_snapshot
    _write_approved_snapshot(tmp_path, attention_level="HIGH")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())
    import asyncio
    asyncio.run(adapter.execute(_req("market.alerts", {"trade_date": "2026-08-26"})))
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert after == before


def test_tc_at_r5_018_golden_fixture_compatibility_and_list():
    names = {p.name for p in FIXTURE_DIR.glob("*.json")}
    assert EXPECTED_RESPONSE_FIXTURES.issubset(names)
    assert REQUIRED_REQUEST_EXAMPLES.issubset(names)
    assert names <= EXPECTED_RESPONSE_FIXTURES | REQUIRED_REQUEST_EXAMPLES | ALLOWED_ADDITIVE_REQUEST_EXAMPLES
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if path.name.startswith("adapter_request"):
            AdapterRequest.from_dict(raw)
        else:
            assert DomainObservationEnvelope.from_dict(raw).to_dict() == raw


def test_tc_at_r5_http_provider_failure_remains_structured_envelope():
    envelope = DomainObservationEnvelope(
        operation="market.snapshot",
        status="error",
        data_state="empty",
        correlation_id="corr-at-r5",
        provider_request_id="idem-at-r5",
        observed_at="2026-08-26T15:30:00+08:00",
        payload={},
        source_records=[],
        failures=[SourceFailure(code="INTERNAL_ERROR", message="provider bug", source_name="market_context_exporter")],
    )
    app = FastAPI()
    app.state.julia_domain_adapter = FakeHttpAdapter(envelope)
    register_julia_domain_adapter_routes(app)
    response = TestClient(app).post("/adapter/v1/execute", json=_req().to_dict())
    assert response.status_code == 200
    assert response.json() == envelope.to_dict()
    assert response.json()["status"] == "error"


def test_tc_at_r5_http_partial_preserves_success_material_and_failures():
    envelope = DomainObservationEnvelope(
        operation="market.snapshot",
        status="partial",
        data_state="normal",
        correlation_id="corr-at-r5",
        provider_request_id="idem-at-r5",
        observed_at="2026-08-26T15:30:00+08:00",
        payload={"market_state": {"theme_count": 1}, "themes": [{"subject_key": "theme-ai"}]},
        source_records=[
            SourceRecord(source_type="database", source_name="theme_cycle_judgement_v2", source_ref="ok", as_of="2026-08-26", observed_at="2026-08-26T15:30:00+08:00", freshness="fresh", status="success", provenance={"row_count": 1}),
            SourceRecord(source_type="redis", source_name="redis_alert_stream", source_ref="stream", as_of="2026-08-26", observed_at="2026-08-26T15:30:00+08:00", freshness="fresh", status="failed", provenance={}, failure=SourceFailure(code="UPSTREAM_UNAVAILABLE", message="redis unavailable", source_name="redis_alert_stream", retryable=True)),
        ],
        failures=[SourceFailure(code="UPSTREAM_UNAVAILABLE", message="redis unavailable", source_name="redis_alert_stream", retryable=True)],
    )
    app = FastAPI()
    app.state.julia_domain_adapter = FakeHttpAdapter(envelope)
    register_julia_domain_adapter_routes(app)
    body = TestClient(app).post("/adapter/v1/execute", json=_req().to_dict()).json()
    assert body["status"] == "partial"
    assert body["payload"]["themes"]
    assert body["failures"]
    assert {r["status"] for r in body["source_records"]} == {"success", "failed"}


def test_tc_at_r5_http_serialization_preserves_correlation_and_freshness():
    envelope = DomainObservationEnvelope(
        operation="market.snapshot",
        status="success",
        data_state="stale",
        correlation_id="corr-at-r5",
        provider_request_id="idem-at-r5",
        observed_at="2026-08-25T15:30:00+08:00",
        payload={"themes": [{"subject_key": "theme-ai"}]},
        source_records=[SourceRecord(source_type="file_cache", source_name="cached_snapshot", source_ref="cache", as_of="2026-08-25", observed_at="2026-08-25T15:30:00+08:00", freshness="stale", status="success", provenance={"cache": True})],
    )
    app = FastAPI()
    app.state.julia_domain_adapter = FakeHttpAdapter(envelope)
    register_julia_domain_adapter_routes(app)
    body = TestClient(app).post("/adapter/v1/execute", json=_req().to_dict()).json()
    assert body["correlation_id"] == "corr-at-r5"
    assert body["provider_request_id"] == "idem-at-r5"
    assert body["data_state"] == "stale"
    assert body["source_records"][0]["freshness"] == "stale"


def test_tc_at_r5_julia_independent_and_schema_unchanged():
    import hashlib
    assert hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest() == EXPECTED_SCHEMA_SHA256
    checked = [
        ROOT / "stock_processing_service" / "application" / "services" / "julia_domain_adapter",
        ROOT / "stock_processing_service" / "ports" / "julia_domain_adapter_http.py",
        ROOT / "scripts" / "julia_domain_adapter_client.py",
    ]
    forbidden_roots = {"julia_core", "julia_ai_assistant"}
    for target in checked:
        paths = [target] if target.is_file() else list(target.rglob("*.py"))
        for path in paths:
            tree = ast_parse(path)
            for node in __import__("ast").walk(tree):
                if isinstance(node, __import__("ast").Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in forbidden_roots
                elif isinstance(node, __import__("ast").ImportFrom):
                    assert (node.module or "").split(".")[0] not in forbidden_roots


def ast_parse(path: Path):
    import ast
    return ast.parse(path.read_text(encoding="utf-8"))
