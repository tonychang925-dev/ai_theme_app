from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SubjectStockPoolDTO:
    trade_date: date
    subject_key: str
    subject_name: str
    stock_id: str
    stock_name: str | None = None
    pool_rank: int | None = None
