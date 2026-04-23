from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class StockAuctionDTO:
    trade_date: date
    stock_id: str
    auction_open_price: Decimal | None = None
    auction_open_pct: Decimal | None = None
    auction_volume: Decimal | None = None
    auction_amount: Decimal | None = None
    tail_auction_close_price: Decimal | None = None
    tail_auction_volume: Decimal | None = None
    tail_auction_amount: Decimal | None = None
    tail_auction_vwap: Decimal | None = None
