from __future__ import annotations

from datetime import date
from typing import Any

class DBMarketDataGateway:
    """Adapter over DatabaseGateway for market daily data."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    async def get_trade_calendar(self, target_date: date) -> dict[str, Any]:
        return await self._db.get_trade_calendar(target_date)

    async def get_daily_quotes(self, trade_date: date) -> list[dict[str, Any]]:
        return await self._db.get_stock_daily_bars(trade_date)

    async def get_daily_factors(self, trade_date: date) -> list[dict[str, Any]]:
        # Phase1 暂以日线对象代理，后续补全独立因子对象。
        return await self._db.get_stock_daily_bars(trade_date)
