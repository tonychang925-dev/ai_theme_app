from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuildResult:
    name: str
    trade_date: str
    affected_rows: int
    status: str = "ok"
