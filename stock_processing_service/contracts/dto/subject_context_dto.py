from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SubjectContextDTO:
    trade_date: date
    subject_key: str
    subject_name: str
    theme_event_summary: str | None = None
    theme_context_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
