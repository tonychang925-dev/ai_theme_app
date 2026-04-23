from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StockDailySnapshot:
    trade_date: date
    stock_id: str
    stock_name: str
    close_price: Decimal
    pct_chg: Decimal
    volume: Decimal
    amount: Decimal
    limit_up_price: Decimal
    limit_down_price: Decimal
    snapshot_version: str
    batch_id: str
    trace_id: str
    source_trace_id: str
    labels: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    source: str = "stock_processing_service"
