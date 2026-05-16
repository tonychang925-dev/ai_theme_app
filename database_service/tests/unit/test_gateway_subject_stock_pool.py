from __future__ import annotations

from datetime import date

import pytest

from database_service.gateway import DatabaseGateway


class _DailyOnlyClient:
    async def get_subject_stock_daily_snapshot_by_trade_date(self, trade_date):
        return [
            {
                "trade_date": trade_date,
                "subject_key": "theme-a",
                "stock_id": "000001.SZ",
                "stock_name": "核心股份",
            }
        ]


@pytest.mark.asyncio
async def test_gateway_subject_stock_pool_falls_back_to_daily_snapshot_method():
    DatabaseGateway._instance = None
    try:
        gateway = DatabaseGateway()
        gateway._client = _DailyOnlyClient()

        rows = await gateway.get_subject_stock_pool_by_trade_date(date(2026, 5, 16))

        assert rows[0]["subject_key"] == "theme-a"
        assert rows[0]["stock_id"] == "000001.SZ"
    finally:
        DatabaseGateway._instance = None
