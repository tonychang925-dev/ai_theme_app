from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TradeCalendarDTO:
    trade_date: date
    calendar_is_open: bool
    prev_trade_date: date | None = None
    next_trade_date: date | None = None
