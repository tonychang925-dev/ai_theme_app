from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeadLetterPayload:
    original_event_name: str
    reason: str
    payload_excerpt: dict[str, Any]
