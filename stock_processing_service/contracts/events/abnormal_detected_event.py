from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AbnormalDetectedPayload:
    stock_id: str
    trade_date: date
    event_types: list[str]
    row_count: int
