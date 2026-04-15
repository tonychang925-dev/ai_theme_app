import os

from fastapi.testclient import TestClient


os.environ.setdefault("POSTGRES_DATABASE", "stock_data_test")

from frontend_bff.app import app


def test_stock_screener_strategies_available_real_db():
    with TestClient(app) as client:
        resp = client.get("/api/stock-screener/strategies")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    first = payload[0]
    assert "strategy_id" in first
    assert "strategy_name" in first
    assert "weight_config" in first


def test_stock_screener_execute_includes_diagnostics_real_db():
    with TestClient(app) as client:
        resp = client.post(
            "/api/stock-screener/execute",
            json={
                "strategy_id": "default_composite",
                "trade_date": "2026-04-10",
                "limit": 5,
                "min_score": 60,
            },
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] in {"completed", "running", "pending"}
    assert "diagnostics" in payload
    diagnostics = payload["diagnostics"]
    assert "coverage_ratio" in diagnostics
    assert "zero_score_count" in diagnostics
    assert "missing_dimension_count" in diagnostics
    coverage = diagnostics["coverage_ratio"]
    for key in ("theme", "mainline", "cycle", "leader", "technical"):
        assert key in coverage
        assert 0.0 <= float(coverage[key]) <= 1.0


def test_stock_screener_favorite_roundtrip_real_db():
    with TestClient(app) as client:
        execute_resp = client.post(
            "/api/stock-screener/execute",
            json={
                "strategy_id": "default_composite",
                "trade_date": "2026-04-10",
                "limit": 1,
                "min_score": 60,
            },
        )
        assert execute_resp.status_code == 200
        execute_payload = execute_resp.json()
        results = execute_payload.get("results") or []
        assert len(results) >= 1
        result_id = results[0]["result_id"]

        add_resp = client.post(
            "/api/stock-screener/favorites",
            params={"user_id": "pytest_user"},
            json={"result_id": result_id, "notes": "pytest", "tags": ["pytest"]},
        )
        assert add_resp.status_code == 200
        favorite_id = add_resp.json()["favorite_id"]

        list_resp = client.get("/api/stock-screener/favorites", params={"user_id": "pytest_user"})
        assert list_resp.status_code == 200
        favorites = list_resp.json()
        assert any(item["favorite_id"] == favorite_id for item in favorites)

        del_resp = client.delete(f"/api/stock-screener/favorites/{favorite_id}")
        assert del_resp.status_code == 200
