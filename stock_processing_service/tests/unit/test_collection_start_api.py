from __future__ import annotations

from types import SimpleNamespace

import pytest

from stock_processing_service import api_app


class _FakeCollectionJobManager:
    def __init__(self, *, availability_payload: dict[str, object] | None = None, prepare_error: Exception | None = None):
        self._availability_payload = availability_payload or {"allowed": True, "message": "ok"}
        self._prepare_error = prepare_error

    def availability(self, trade_date: str | None = None) -> dict[str, object]:
        payload = dict(self._availability_payload)
        payload["trade_date"] = trade_date
        return payload

    async def prepare_payload(self, trade_date: str, payload: dict[str, object]) -> dict[str, object]:
        if self._prepare_error is not None:
            raise self._prepare_error
        prepared = dict(payload)
        prepared["trade_date"] = trade_date
        return prepared

    def create_job(self, trade_date: str, prepared_payload: dict[str, object]):
        return SimpleNamespace(
            to_dict=lambda: {
                "trade_date": trade_date,
                "prepared_payload": prepared_payload,
                "job_id": "job-1",
            }
        )


@pytest.mark.asyncio
async def test_start_collection_keeps_f10_payload_without_explicit_stock_ids(monkeypatch):
    monkeypatch.setattr(
        api_app.app,
        "state",
        SimpleNamespace(collection_job_manager=_FakeCollectionJobManager()),
        raising=False,
    )

    payload = await api_app.start_collection(api_app.CollectionStartRequest(trade_date="2026-06-16", options={"f10_capital": True}))

    assert payload["trade_date"] == "2026-06-16"
    assert payload["prepared_payload"]["trade_date"] == "2026-06-16"
    assert payload["prepared_payload"]["options"]["f10_capital"] is True
