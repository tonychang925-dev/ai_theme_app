from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class TradeDateInput:
    trade_date: date


@dataclass
class WindowInput:
    trade_date: date
    window_days: int
