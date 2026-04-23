from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BuildResult:
    name: str
    trade_date: str
    affected_rows: int
    status: str = "ok"
    batch_id: str = ""
    trace_id: str = ""
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    published_events: list[str] = field(default_factory=list)
    cache_writes: int = 0
