from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, TypeVar


PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True)
class EventEnvelope(Generic[PayloadT]):
    event_id: str
    event_name: str
    trade_date: date
    batch_id: str
    trace_id: str
    producer: str
    occurred_at: datetime
    payload_version: str
    payload: PayloadT
