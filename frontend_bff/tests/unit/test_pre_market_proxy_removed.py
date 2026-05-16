from __future__ import annotations

from frontend_bff.app import app


def test_pre_market_brief_proxy_routes_are_removed_from_legacy_bff():
    removed = {
        ("GET", "/api/v2/pre-market-brief"),
        ("POST", "/api/v2/pre-market-brief/rebuild"),
        ("POST", "/api/v2/pre-market-brief/finalize"),
    }
    actual = {
        (method, getattr(route, "path", ""))
        for route in app.router.routes
        for method in getattr(route, "methods", set())
    }

    assert removed.isdisjoint(actual)
