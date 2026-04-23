from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SubjectStockDailySnapshot:
    trade_date: date
    subject_key: str
    stock_id: str
    subject_name: str
    in_pool_flag: bool
    pool_rank: int | None
    support_score: Decimal
    snapshot_version: str
    batch_id: str
    trace_id: str
    source_trace_id: str
    role_tags: dict[str, Any] = field(default_factory=dict)
    evidence_rules: list[str] = field(default_factory=list)
    source: str = "stock_processing_service"
