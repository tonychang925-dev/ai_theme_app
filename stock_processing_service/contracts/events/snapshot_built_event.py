from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SnapshotBuiltPayload:
    domain: Literal["daily_snapshot", "pre_market", "post_market", "identity"]
    snapshot_version: str
    object_name: str
    row_count: int
    success: bool
