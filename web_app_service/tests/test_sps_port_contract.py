from __future__ import annotations

from fastapi.testclient import TestClient

import web_app_service.main as main_mod


def test_web_app_service_uses_fixed_sps_port_8090():
    assert main_mod._SPS_BASE_URL == "http://127.0.0.1:8090"

    with TestClient(main_mod.app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert main_mod.app.state.realtime_stack_manager._sps_port == 8090
