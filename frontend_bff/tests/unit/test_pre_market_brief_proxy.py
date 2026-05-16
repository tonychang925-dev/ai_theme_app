from __future__ import annotations

import pytest

from frontend_bff import app as app_module
from frontend_bff.app import app


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _ProxyClient:
    calls: list[dict] = []
    fail: bool = False

    def __init__(self, timeout=30.0):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self.calls.append({"method": "GET", "url": url, "params": params or {}})
        if self.fail:
            raise RuntimeError("sps unavailable")
        return _Response(
            {
                "trade_date": (params or {}).get("trade_date"),
                "snapshot_version": "pre_market_brief.v1",
                "status": "draft",
                "payload": {"diagnostics": {"partial": False}},
            }
        )

    async def post(self, url, json=None):
        self.calls.append({"method": "POST", "url": url, "json": json or {}})
        if self.fail:
            raise RuntimeError("sps unavailable")
        return _Response({"ok": True, "trade_date": (json or {}).get("trade_date"), "payload": json or {}})


def test_pre_market_brief_v2_routes_exist():
    expected = {
        ("GET", "/api/v2/pre-market-brief"),
        ("POST", "/api/v2/pre-market-brief/rebuild"),
        ("POST", "/api/v2/pre-market-brief/finalize"),
    }
    actual = {
        (method, getattr(route, "path", ""))
        for route in app.router.routes
        for method in getattr(route, "methods", set())
    }

    assert expected <= actual


@pytest.mark.asyncio
async def test_get_pre_market_brief_proxy_calls_sps_only(monkeypatch):
    _ProxyClient.calls = []
    _ProxyClient.fail = False
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _ProxyClient)

    payload = await app_module.get_pre_market_brief_proxy(trade_date="2026-05-16", date=None)

    assert payload["status"] == "draft"
    assert _ProxyClient.calls == [
        {
            "method": "GET",
            "url": f"{app_module._sps_base_url()}/api/v1/pre_market_brief",
            "params": {"trade_date": "2026-05-16"},
        }
    ]


@pytest.mark.asyncio
async def test_rebuild_and_finalize_pre_market_brief_proxy_post_to_sps(monkeypatch):
    _ProxyClient.calls = []
    _ProxyClient.fail = False
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _ProxyClient)

    rebuild = await app_module.rebuild_pre_market_brief_proxy(
        app_module.PreMarketBriefProxyPayload(trade_date="2026-05-16", force=True)
    )
    finalize = await app_module.finalize_pre_market_brief_proxy(
        app_module.PreMarketBriefFinalizeProxyPayload(trade_date="2026-05-16")
    )

    assert rebuild["ok"] is True
    assert finalize["ok"] is True
    assert _ProxyClient.calls[0]["url"].endswith("/api/v1/pre_market_brief/rebuild")
    assert _ProxyClient.calls[0]["json"]["force"] is True
    assert _ProxyClient.calls[1]["url"].endswith("/api/v1/pre_market_brief/finalize")
    assert _ProxyClient.calls[1]["json"] == {"trade_date": "2026-05-16", "force": False}


@pytest.mark.asyncio
async def test_pre_market_brief_proxy_returns_partial_when_sps_unavailable(monkeypatch):
    _ProxyClient.calls = []
    _ProxyClient.fail = True
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _ProxyClient)

    payload = await app_module.get_pre_market_brief_proxy(trade_date="2026-05-16", date=None)

    assert payload["status"] == "partial"
    assert payload["diagnostics"]["partial"] is True
    assert payload["payload"]["diagnostics"]["partial"] is True
    assert payload["payload"]["sections"]["event_driven_opportunities"] == []
