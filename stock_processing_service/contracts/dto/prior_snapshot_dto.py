from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PriorSnapshotDTO:
    trade_date: date
    stock_id: str
    snapshot_version: str
    payload: dict[str, Any]
