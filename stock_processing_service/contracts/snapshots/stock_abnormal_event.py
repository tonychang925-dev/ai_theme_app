from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StockAbnormalEvent:
    trade_date: date
    stock_id: str
    event_type: str
    event_score: Decimal
    evidence_rules: list[str]
    raw_metrics: dict[str, Any]
    snapshot_version: str
    batch_id: str
    trace_id: str
    source_trace_id: str
    source: str = "stock_processing_service"
