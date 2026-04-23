from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import StockAuctionDTO


class AuctionGatewayAdapter:
    def __init__(self, stock_read_gateway: Any) -> None:
        self._read = stock_read_gateway

    async def get_stock_auction_snapshot(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockAuctionDTO]:
        return await self._read.get_stock_auction_snapshot(trade_date, stock_ids=stock_ids)
