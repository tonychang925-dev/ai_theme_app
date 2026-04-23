from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ThemeStockLeaderboard:
    trade_date: date
    subject_key: str
    stock_id: str
    leaderboard_rank: int
    leader_score: Decimal
    score_breakdown: dict[str, Any]
    snapshot_version: str
    batch_id: str
    trace_id: str
    source_trace_id: str
    role_name: str | None = None
    source: str = "stock_processing_service"
