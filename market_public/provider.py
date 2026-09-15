"""The sole Julia-facing Market provider."""
from __future__ import annotations

from typing import Any

from .contracts import (
    CAPABILITIES, EventReadRequest, EventResolveRequest, MarketResult,
    MarketStatus, ProductReadRequest,
)


def _is_dependency_failure(exc: Exception) -> bool:
    """Recognize connection failures without masking query/programming errors."""
    if isinstance(exc, (ConnectionError, TimeoutError, OSError, ImportError)):
        return True
    try:
        import asyncpg
    except ImportError:
        return exc.__class__.__name__ in {
            "PostgresConnectionError", "CannotConnectNowError",
            "ConnectionDoesNotExistError", "TooManyConnectionsError",
        }
    types = tuple(cls for cls in (
        getattr(asyncpg, "PostgresConnectionError", None),
        getattr(asyncpg, "CannotConnectNowError", None),
        getattr(asyncpg, "ConnectionDoesNotExistError", None),
        getattr(asyncpg, "TooManyConnectionsError", None),
    ) if isinstance(cls, type))
    return bool(types) and isinstance(exc, types)


class _MarketPublicProvider:
    """Private implementation; callers obtain it only from MarketPublicFactory."""

    def __init__(self, repository: Any):
        self._repository = repository

    async def execute(self, capability: str, request: Any) -> MarketResult:
        metadata = CAPABILITIES.get(capability)
        if metadata is None:
            return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "unknown_capability", "Unknown Market capability")
        try:
            if capability == "market.event.resolve":
                if not isinstance(request, EventResolveRequest) or request.limit < 1:
                    return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "Invalid event resolve request")
                if request.limit > 200:
                    return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "limit must be between 1 and 200")
                if request.feed_date is not None:
                    from datetime import datetime
                    try:
                        datetime.strptime(request.feed_date, "%Y-%m-%d")
                    except (TypeError, ValueError):
                        return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "feed_date must use YYYY-MM-DD")
                data = await self._repository.fetch_intel_feed(
                    feed_date=request.feed_date, stock_id=request.stock_id,
                    item_type="event", limit=request.limit,
                )
                if request.stock_id:
                    # The CDP event source cannot apply stock_id in the current
                    # repository SQL and must not contaminate a stock-scoped feed.
                    data = [row for row in data if row.get("source_channel") != "jyhf_cdp"]
            elif capability == "market.event.read":
                if not isinstance(request, EventReadRequest) or request.event_id < 1:
                    return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "Invalid event read request")
                rows = await self._repository.fetch_intel_feed(item_type="event", limit=200)
                data = next((row for row in rows if _event_id_from_item(row.get("item_id")) == request.event_id), None)
                if data is None:
                    return MarketResult.failure(capability, MarketStatus.NOT_FOUND, "event_not_found", "Event was not found")
            elif capability == "market.product.read":
                if not isinstance(request, ProductReadRequest) or not request.subject_key.strip():
                    return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "Invalid product request")
                data = await self._repository.fetch_theme_detail(request.subject_key)
                if data is None:
                    return MarketResult.failure(capability, MarketStatus.NOT_FOUND, "product_not_found", "Product was not found")
            else:  # guarded by CAPABILITIES; retain fail-closed behavior
                return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "unsupported_capability", "Unsupported capability")
            return MarketResult(capability, MarketStatus.SUCCESS, data=data)
        except Exception as exc:
            if _is_dependency_failure(exc):
                return MarketResult.failure(capability, MarketStatus.DEPENDENCY_UNAVAILABLE, "dependency_unavailable", str(exc))
            return MarketResult.failure(capability, MarketStatus.INTERNAL_FAILURE, "internal_failure", str(exc))

    async def close(self) -> None:
        await self._repository.close()


def _event_id_from_item(item_id: Any) -> int | None:
    """Decode canonical repository ids: event:42:theme:1 or event:jyhf_cdp:7."""
    if not isinstance(item_id, str):
        return None
    parts = item_id.split(":")
    if len(parts) >= 3 and parts[0] == "event" and parts[1].isdigit():
        return int(parts[1])
    if len(parts) >= 3 and parts[:2] == ["event", "jyhf_cdp"] and parts[2].isdigit():
        return int(parts[2])
    return None
