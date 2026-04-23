from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SubjectStockPoolDTO:
    trade_date: date
    subject_key: str
    subject_name: str
    stock_id: str
    stock_name: str | None = None
    pool_rank: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
