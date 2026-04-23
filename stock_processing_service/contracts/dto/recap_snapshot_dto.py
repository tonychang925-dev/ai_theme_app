from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RecapSnapshotDTO:
    trade_date: date
    snapshot_version: str
    recap_doc: dict[str, Any]
    batch_id: str
    trace_id: str
