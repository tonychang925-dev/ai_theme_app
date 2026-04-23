from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class StockBarDTO:
    trade_date: date
    stock_id: str
    stock_name: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    pre_close: Decimal
    pct_chg: Decimal
    volume: Decimal
    amount: Decimal
    limit_up_price: Decimal
    limit_down_price: Decimal
