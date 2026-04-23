from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PostMarketRecapSnapshot:
    trade_date: date
    snapshot_version: str
    batch_id: str
    trace_id: str
    source_trace_id: str
    recap_doc: dict[str, Any]
    source: str = "stock_processing_service"
