from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LeaderboardUpdatedPayload:
    subject_key: str
    trade_date: date
    row_count: int
    snapshot_version: str
