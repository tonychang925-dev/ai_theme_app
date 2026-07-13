"""PR4.2.28e board-pool collector amount persistence contract."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import date

import pytest

from stock_processing_service.scripts.collect_eastmoney_board_pool import _stock_to_dict


@dataclass
class _FriedStock:
    code: str = "601133"
    name: str = "柏诚股份"
    pct: float = 3.4633
    break_times: int = 1
    first_seal: str = "08:01:33"
    turnover: float = 7.9009
    amount: float = 1480394240
    industry: str = "专业工程"


def test_stock_to_dict_preserves_zb_amount_for_raw_json() -> None:
    """TC-ID: PR4.2.28e-zb-raw-json-amount."""
    raw = _stock_to_dict(_FriedStock())

    assert raw["code"] == "601133"
    assert raw["amount"] == 1480394240
    assert raw["turnover"] == 7.9009


class _FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args):
        self.calls.append((query, args))


class _FakeClient:
    async def fetch_zt_pool(self, trade_date: date):
        return []

    async def fetch_zb_pool(self, trade_date: date):
        return [_FriedStock()]

    async def fetch_dt_pool(self, trade_date: date):
        return []

    async def fetch_yzt_pool(self, trade_date: date):
        return []

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_collect_date_persists_zb_amount(monkeypatch) -> None:
    """TC-ID: PR4.2.28e-zb-amount-persistence."""
    from stock_processing_service.scripts import collect_eastmoney_board_pool

    client_module = importlib.import_module("integrations.a_stock_data.clients.eastmoney_board_client")
    monkeypatch.setattr(client_module, "EastmoneyBoardClient", lambda: _FakeClient())
    conn = _FakeConn()

    result = await collect_eastmoney_board_pool.collect_date(conn, date(2026, 7, 9))

    assert result["zb"] == 1
    assert result["errors"] == []
    zb_call = next(call for call in conn.calls if call[1][1] == "ZB")
    args = zb_call[1]
    assert args[9] == 1480394240
    assert '"amount": 1480394240' in args[14]
