import os

from fastapi.testclient import TestClient

os.environ.setdefault("POSTGRES_DATABASE", "stock_data_test")

from frontend_bff import app as app_module
from frontend_bff.app import app


def test_v2_intel_feed_alias_contract(monkeypatch):
    async def _fake_fetch_intel_feed_view(**kwargs):
        return {
            "date": kwargs.get("feed_date") or "2026-04-29",
            "type": kwargs.get("item_type") or "all",
            "session": kwargs.get("session") or "all",
            "count": 0,
            "items": [],
            "diagnostics": {"sources": ["unit_test"]},
        }

    monkeypatch.setattr(app_module.bff_repo, "fetch_intel_feed_view", _fake_fetch_intel_feed_view)

    with TestClient(app) as client:
        resp = client.get("/api/v2/intel/feed", params={"date": "2026-04-29", "type": "all", "session": "all", "limit": 20})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["type"] == "all"
    assert "diagnostics" in payload


def test_v2_intel_stream_alias_contract():
    route_hits = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) == "/api/v2/intel/stream" and "GET" in getattr(r, "methods", set())
    ]
    assert route_hits, "missing GET /api/v2/intel/stream route"


def test_v2_strong_stock_watch_alias_contract(monkeypatch):
    async def _fake_fetch_strong_stock_watch_view(**kwargs):
        return {
            "trade_date": kwargs.get("trade_date") or "2026-04-29",
            "window_days": kwargs.get("window_days") or 7,
            "stocks": [],
            "count": 0,
        }

    monkeypatch.setattr(app_module.bff_repo, "fetch_strong_stock_watch_view", _fake_fetch_strong_stock_watch_view)

    with TestClient(app) as client:
        resp = client.get("/api/v2/intel/strong-stocks/watch", params={"date": "2026-04-29", "window_days": 7, "limit": 20})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["trade_date"] == "2026-04-29"
