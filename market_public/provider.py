"""The sole Julia-facing Market provider."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .contracts import (
    CAPABILITIES, EventReadRequest, EventResolveRequest, MarketResult,
    MarketStatus, ProductReadRequest,
)


class MarketPublicProvider:
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
                data = await self._repository.fetch_intel_feed(
                    feed_date=request.feed_date, stock_id=request.stock_id,
                    item_type="event", limit=request.limit,
                )
            elif capability == "market.event.read":
                if not isinstance(request, EventReadRequest) or request.event_id < 1:
                    return MarketResult.failure(capability, MarketStatus.INVALID_REQUEST, "invalid_request", "Invalid event read request")
                rows = await self._repository.fetch_intel_feed(item_type="event", limit=100)
                data = next((row for row in rows if row.get("event_id") == request.event_id or row.get("id") == request.event_id), None)
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
        except (ConnectionError, TimeoutError, OSError, ImportError) as exc:
            return MarketResult.failure(capability, MarketStatus.DEPENDENCY_UNAVAILABLE, "dependency_unavailable", str(exc))
        except Exception as exc:
            return MarketResult.failure(capability, MarketStatus.INTERNAL_FAILURE, "internal_failure", str(exc))

    async def close(self) -> None:
        await self._repository.close()
