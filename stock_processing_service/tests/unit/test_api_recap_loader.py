import asyncpg
import pytest

from stock_processing_service import api_app


@pytest.mark.asyncio
async def test_load_recap_doc_reads_latest_updated_snapshot(monkeypatch) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.query = ""
            self.closed = False

        async def fetchrow(self, query, trade_date):
            self.query = query
            return {"payload": {"recap_doc": {"strong_hotspot_subjects": [{"theme_name": "磷化铟"}]}}}

        async def close(self) -> None:
            self.closed = True

    fake = FakeConnection()

    async def fake_connect(*args, **kwargs):
        return fake

    monkeypatch.setattr(asyncpg, "connect", fake_connect)

    recap = await api_app._load_recap_doc("2026-07-09")

    assert recap["strong_hotspot_subjects"][0]["theme_name"] == "磷化铟"
    assert "ORDER BY updated_at DESC, created_at DESC" in fake.query
    assert fake.closed is True
