"""Julia-facing, transport-neutral Market contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MarketStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    INVALID_REQUEST = "INVALID_REQUEST"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


@dataclass(frozen=True)
class CapabilityMetadata:
    capability: str
    provider: str = "market"
    permission_scope: str = "market.observe"
    side_effect: str = "READ_ONLY"
    c08_required: bool = True


CAPABILITIES = {
    name: CapabilityMetadata(name)
    for name in (
        "market.event.resolve",
        "market.event.read",
        "market.product.read",
    )
}


@dataclass(frozen=True)
class EventResolveRequest:
    feed_date: str | None = None
    stock_id: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class EventReadRequest:
    event_id: int


@dataclass(frozen=True)
class ProductReadRequest:
    subject_key: str


@dataclass(frozen=True)
class MarketResult:
    capability: str
    status: MarketStatus
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def failure(cls, capability: str, status: MarketStatus, code: str, message: str) -> "MarketResult":
        return cls(capability, status, error_code=code, error_message=message)
