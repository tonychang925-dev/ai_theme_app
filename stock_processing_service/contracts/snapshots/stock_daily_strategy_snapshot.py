from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StockDailyStrategySnapshot:
    trade_date: date
    stock_id: str
    stock_name: str
    close_price: Decimal | None = None
    pct_chg: Decimal | None = None
    volume: Decimal | None = None
    amount: Decimal | None = None
    limit_up_price: Decimal | None = None
    limit_down_price: Decimal | None = None
    snapshot_version: str = ""
    batch_id: str = ""
    trace_id: str = ""
    source_trace_id: str = ""
    labels: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    source: str = "stock_processing_service"
