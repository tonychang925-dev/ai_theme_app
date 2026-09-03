"""AT-R7 Deployment Hardening tests.

TC-AT-R7-001: env configuration model and path portability.
TC-AT-R7-002: alternate-cwd import/startup without source path modification.
TC-AT-R7-003: DB/Redis readiness semantics without full market query.
TC-AT-R7-004: execute timeout yields structured envelope.
TC-AT-R7-005: request/response payload bounds.
TC-AT-R7-006: structured correlation logging and secret redaction.
TC-AT-R7-007: frozen schema/fixtures unchanged.
TC-AT-R7-008: no sibling sys.path stitching / no Julia import / no semantic routing.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.julia_domain_adapter.contracts import DomainObservationEnvelope, SourceRecord
from stock_processing_service.ports.julia_domain_adapter_config import JuliaDomainAdapterHTTPConfig
from stock_processing_service.ports.julia_domain_adapter_http import register_julia_domain_adapter_routes

SCHEMA_SHA256 = "baf4d21efd2681009d3eeab899e7320624c05fe6397fa4aa4ef713f009451497"
FROZEN_RESPONSE_HASHES = {
    "market_alerts_empty.json": "1fa5cb20203bdb865fd89714c898a9f5e9ce496e12184c21ed7963e044220bb8",
    "market_alerts_success.json": "2c60b7c4d2b386b95499bd0439c0bed091a7d9a275a4ef19b63ae3f7e109dcd6",
    "market_snapshot_empty.json": "2436d6905c5db66e92cd5c7e9caede23545b2b175adbab4845599a4d3680c9ce",
    "market_snapshot_error.json": "e7692d3d1d0dc309ef6d5889d984e88ecef364450ba9883586e0311cc06f329e",
    "market_snapshot_partial.json": "aa1115cd6bbf9dd5dc38fb63c155234ff8d5695af0769698ce5bc4860f35cf7c",
    "market_snapshot_stale.json": "c86b5c1475776658dddb1bf32bee1d171b4031aaaa7fac4802a74df0e97386c7",
    "market_snapshot_success.json": "270384c2a95747dfac05b8c3eb4ad6a43230f75db0d1f69a9772b5a6ca8fdfdf",
    "market_snapshot_unavailable.json": "dc8959dfaca54fe5dd557bcf7c35006a7b49d2dfc64b7f10aa611b04e80784f4",
}


class SlowAdapter:
    async def execute(self, request):
        import asyncio
        await asyncio.sleep(0.1)
        raise AssertionError("wait_for should time out before this")


class BigResponseAdapter:
    async def execute(self, request):
        return DomainObservationEnvelope(
            operation=request.operation,
            status="success",
            data_state="normal",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=request.requested_at,
            payload={"blob": "x" * 4096},
            source_records=[SourceRecord(source_type="test", source_name="big", source_ref="fixture", as_of="2026-08-26", observed_at=request.requested_at, freshness="fresh", status="success", provenance={})],
            failures=[],
        )


def _request() -> dict:
    return {
        "operation": "market.snapshot",
        "arguments": {"trade_date": "2026-08-26"},
        "correlation_id": "corr-at-r7",
        "idempotency_key": "idem-at-r7",
        "requested_at": "2026-08-26T10:00:00+08:00",
        "schema_version": "1.0",
        "trace_metadata": {},
    }


def test_tc_at_r7_001_env_configuration_model_and_path_portability(tmp_path):
    env = {
        "AI_THEME_APP_ROOT": str(tmp_path / "root"),
        "JULIA_ADAPTER_WORKBENCH_BASE_DIR": str(tmp_path / "wb"),
        "JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS": "2.5",
        "JULIA_ADAPTER_MAX_REQUEST_BYTES": "2048",
        "JULIA_ADAPTER_MAX_RESPONSE_BYTES": "4096",
        "JULIA_ADAPTER_REDIS_REQUIRED": "true",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    config = JuliaDomainAdapterHTTPConfig.from_env(env)
    assert config.workbench_base_dir == tmp_path / "wb"
    assert config.execute_timeout_seconds == 2.5
    assert config.max_request_bytes == 2048
    assert config.max_response_bytes == 4096
    assert config.redis_required is True
    assert config.redis_url_valid() is True


def test_tc_at_r7_002_alternate_cwd_import_startup_without_source_path_modification(tmp_path):
    script = "from stock_processing_service.ports.julia_domain_adapter_config import JuliaDomainAdapterHTTPConfig; print(JuliaDomainAdapterHTTPConfig.from_env({}).max_request_bytes)"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, text=True, capture_output=True, check=True)
    assert result.stdout.strip() == "262144"


def test_tc_at_r7_003_db_redis_readiness_semantics_without_market_query(tmp_path):
    app = FastAPI()
    app.state.julia_domain_adapter_config = JuliaDomainAdapterHTTPConfig(
        workbench_base_dir=tmp_path,
        redis_required=True,
        redis_url="not-a-redis-url",
        database_required=True,
    )
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)
    health = client.get("/adapter/v1/health").json()
    ready = client.get("/adapter/v1/ready").json()

    assert health["ok"] is True
    assert ready["ready"] is False
    assert ready["dependencies"]["database"]["ready"] is False
    assert ready["dependencies"]["redis"]["ready"] is False
    assert {failure["source_name"] for failure in ready["failures"]} >= {"database", "redis"}


def test_tc_at_r7_004_execute_timeout_returns_structured_domain_envelope():
    app = FastAPI()
    app.state.julia_domain_adapter = SlowAdapter()
    app.state.julia_domain_adapter_config = JuliaDomainAdapterHTTPConfig(workbench_base_dir=Path("/tmp"), execute_timeout_seconds=0.1)
    register_julia_domain_adapter_routes(app)
    body = TestClient(app).post("/adapter/v1/execute", json=_request()).json()

    assert body["status"] == "unavailable"
    assert body["data_state"] == "empty"
    assert body["failures"][0]["code"] == "UPSTREAM_TIMEOUT"
    assert body["correlation_id"] == "corr-at-r7"


def test_tc_at_r7_005_request_and_response_payload_bounds():
    app = FastAPI()
    app.state.julia_domain_adapter = BigResponseAdapter()
    app.state.julia_domain_adapter_config = JuliaDomainAdapterHTTPConfig(workbench_base_dir=Path("/tmp"), max_request_bytes=1024, max_response_bytes=1024)
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)

    too_large = dict(_request())
    too_large["arguments"] = {"blob": "x" * 2048}
    assert client.post("/adapter/v1/execute", json=too_large).status_code == 413

    body = client.post("/adapter/v1/execute", json=_request()).json()
    assert body["status"] == "error"
    assert body["failures"][0]["message"] == "adapter response payload too large"
    assert body["correlation_id"] == "corr-at-r7"


def test_tc_at_r7_006_structured_correlation_logging_and_secret_redaction(caplog):
    from tests.julia_domain_adapter.test_at_r4_http_transport import _app_with_adapter, _envelope
    caplog.set_level("INFO", logger="stock_processing_service.ports.julia_domain_adapter_http")
    client = TestClient(_app_with_adapter(_envelope()))
    response = client.post("/adapter/v1/execute", json=_request())
    assert response.status_code == 200
    text = caplog.text
    assert "julia_domain_adapter.execute.start" in text
    assert "julia_domain_adapter.execute.end" in text
    assert "corr-at-r7" in text
    assert "secret" not in json.dumps(response.json())


def test_tc_at_r7_007_frozen_schema_and_response_fixtures_unchanged():
    schema = ROOT / "docs" / "integration" / "JULIA_ADAPTER_SCHEMA_v1.json"
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == SCHEMA_SHA256
    fixture_dir = ROOT / "docs" / "integration" / "fixtures" / "julia_domain_adapter"
    for name, expected in FROZEN_RESPONSE_HASHES.items():
        assert hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest() == expected


def test_tc_at_r7_008_no_sibling_sys_path_stitching_or_forbidden_runtime_features():
    targets = [
        ROOT / "stock_processing_service" / "application" / "services" / "julia_domain_adapter",
        ROOT / "stock_processing_service" / "ports" / "julia_domain_adapter_http.py",
        ROOT / "stock_processing_service" / "ports" / "julia_domain_adapter_config.py",
        ROOT / "scripts" / "julia_domain_adapter_client.py",
    ]
    forbidden_text = [
        "/Users/admin/julia_core",
        "/Users/admin/julia_ai_assistant",
        "market.intent.resolve",
        "semantic_router",
        "natural_language",
        "user_text",
        "execute_order",
        "modify_strategy",
    ]
    forbidden_import_roots = {"julia_core", "julia_ai_assistant", "mcp_server"}
    for target in targets:
        paths = [target] if target.is_file() else list(target.rglob("*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for needle in forbidden_text:
                assert needle not in text
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in forbidden_import_roots
                elif isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] not in forbidden_import_roots


def test_tc_at_r7_009_rejects_extra_top_level_request_fields():
    app = FastAPI()
    app.state.julia_domain_adapter_config = JuliaDomainAdapterHTTPConfig(workbench_base_dir=Path("/tmp"))
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)
    request = _request()
    request["unsupported_field"] = "must-not-be-ignored"
    response = client.post("/adapter/v1/execute", json=request)
    assert response.status_code == 400
    assert "unsupported fields: unsupported_field" in response.json()["detail"]["error"]


def test_tc_at_r7_010_invalid_utf8_returns_http_400():
    app = FastAPI()
    app.state.julia_domain_adapter_config = JuliaDomainAdapterHTTPConfig(workbench_base_dir=Path("/tmp"))
    register_julia_domain_adapter_routes(app)
    client = TestClient(app)
    response = client.post("/adapter/v1/execute", content=b"\xff")
    assert response.status_code == 400
    assert response.json()["detail"]["error"].startswith("invalid UTF-8:")
