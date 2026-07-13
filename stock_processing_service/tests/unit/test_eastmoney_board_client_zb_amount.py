"""PR4.2.28e Eastmoney ZB amount mapping contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from stock_processing_service.integrations.a_stock_data.clients.eastmoney_board_client import (
    EastmoneyBoardClient,
)


@dataclass
class _FakeResponse:
    payload: dict

    def json(self) -> dict:
        return self.payload


class _FakeHttp:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list[tuple[str, dict]] = []

    async def get(self, url: str, params: dict):
        self.requests.append((url, params))
        return _FakeResponse(self.payload)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_fetch_zb_pool_requests_f6_and_maps_amount() -> None:
    """TC-ID: PR4.2.28e-zb-client-amount-mapping."""
    http = _FakeHttp(
        {
            "rc": 0,
            "data": {
                "pool": [
                    {
                        "c": "601133",
                        "n": "柏诚股份",
                        "p": 15000,
                        "zdp": 3.4633,
                        "amount": 1480394240,
                        "ltsz": 10000000000,
                        "fbt": 80133,
                        "zf": 12.3,
                        "hs": 7.9009,
                        "zbc": 1,
                        "hybk": "专业工程",
                    }
                ]
            },
        }
    )

    stocks = await EastmoneyBoardClient(http_client=http).fetch_zb_pool(date(2026, 7, 9))

    assert len(stocks) == 1
    assert "getTopicZBPool" in http.requests[0][0]
    requested_fields = http.requests[0][1]["fields"].split(",")
    assert "f6" in requested_fields
    assert "f62" in requested_fields
    assert "f116" in requested_fields
    assert stocks[0].code == "601133"
    assert stocks[0].amount == 1480394240
    assert stocks[0].float_cap == 10000000000
    assert stocks[0].turnover == 7.9009
