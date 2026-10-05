from __future__ import annotations

from fastapi.testclient import TestClient

import web_app_service.main as main_mod


def test_web_app_service_uses_fixed_sps_port_8090():
    assert main_mod._SPS_BASE_URL == "http://127.0.0.1:8090"

    with TestClient(main_mod.app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert main_mod.app.state.realtime_stack_manager._sps_port == 8090


def test_web_healthz_reports_exact_runtime_source_identity():
    import subprocess
    from pathlib import Path

    payload = __import__("asyncio").run(main_mod.healthz())
    root = Path.cwd().resolve()
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()

    assert payload["cwd"] == str(root)
    assert payload["repo_root"] == str(root)
    assert payload["git_sha"] == sha
    assert payload["git_dirty"] is False


def test_readyz_rejects_sps_source_identity_mismatch(monkeypatch):
    import asyncio
    import json
    from pathlib import Path

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "repo_root": "/tmp/legacy-ai-theme",
                "git_sha": "deadbeef",
                "git_dirty": False,
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            if url.endswith("/healthz"):
                return FakeResponse()
            raise AssertionError(url)

    monkeypatch.setattr(main_mod.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())

    root = str(Path.cwd().resolve())
    monkeypatch.setenv("AI_THEME_AUTHORIZED_REPO_ROOT", root)
    monkeypatch.setenv("AI_THEME_AUTHORIZED_GIT_SHA", main_mod._runtime_git_sha(Path.cwd().resolve()) or "")

    # Isolate unrelated readiness dependencies so only source identity decides this assertion.
    import asyncpg
    import redis.asyncio as aioredis

    class FakeConn:
        async def fetchval(self, query): return 1
        async def close(self): return None

    async def fake_connect(*args, **kwargs): return FakeConn()

    class FakeRedis:
        async def ping(self): return True
        async def aclose(self): return None

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedis())

    result = asyncio.run(main_mod.readyz())
    if hasattr(result, "body"):
        payload = json.loads(result.body)
    else:
        payload = result

    assert payload["status"] == "failed"
    assert "sps_upstream_identity" in payload["fatal"]
    assert "identity_mismatch" in payload["checks"]["sps_upstream"]
