from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


@pytest.mark.asyncio
async def test_get_strong_watch_reads_windowed_history_from_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake_get_rows(**kwargs):
        seen.update(kwargs)
        return [
            {"trade_date": "2026-04-30", "stock_id": "000001.SZ", "watch_status": "active"},
            {"trade_date": "2026-04-29", "stock_id": "000001.SZ", "watch_status": "weakening"},
        ]

    monkeypatch.setattr(
        api_app.app,
        "state",
        SimpleNamespace(gateway=SimpleNamespace(get_strong_stock_watch_view_rows=fake_get_rows)),
        raising=False,
    )

    payload = await api_app.get_strong_watch(
        trade_date="2026-04-30",
        window_days=7,
        include_removed=False,
        latest_per_stock=False,
        stock_id="000001.SZ",
        limit=200,
    )

    assert payload["trade_date"] == "2026-04-30"
    assert len(payload["stocks"]) == 2
    assert seen == {
        "end_date": date(2026, 4, 30),
        "window_days": 7,
        "include_removed": False,
        "latest_per_stock": False,
        "stock_id": "000001.SZ",
        "limit": 200,
    }
