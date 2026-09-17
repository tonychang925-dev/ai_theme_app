"""The sole Julia-facing Market provider."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .contracts import (
    CAPABILITIES,
    MARKET_BOUNDARY_IDENTITY_REF,
    MARKET_PUBLIC_CONTRACT_VERSION,
    EventReadRequest,
    EventResolveRequest,
    MarketDataState,
    MarketFailure,
    MarketFailureKind,
    MarketOperationStatus,
    MarketResultEnvelope,
    ProductReadRequest,
)
from .provenance import MarketProvenance


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


def _produced_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_refs(data: Any) -> tuple[str, ...]:
    """Extract only source identities already present in public payload data."""
    rows = data if isinstance(data, list) else [data]
    refs: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("source_ref", "source_channel", "source_system", "source"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                refs.add(value.strip())
    return tuple(sorted(refs))


def _public_object_refs(data: Any) -> tuple[str, ...]:
    """Preserve opaque public identifiers without binding to private storage identity."""
    rows = data if isinstance(data, list) else [data]
    refs: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("item_id", "subject_key", "product_id"):
            value = row.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                refs.add(str(value).strip())
    return tuple(sorted(refs))


def _provenance(capability: str, data: Any, correlation_id: str, produced_at: str) -> MarketProvenance:
    # No capability-specific mandatory provenance profile is frozen for these
    # current runtime capabilities. Preserve available evidence, but keep the
    # status explicitly INCOMPLETE until a concrete profile is selected.
    return MarketProvenance(
        None,
        produced_at=produced_at,
        market_release_identity=None,
        source_refs=_source_refs(data),
        public_object_refs=_public_object_refs(data),
        capability_call_ref=capability,
        correlation_id=correlation_id,
    )


def _result(
    capability: str,
    *,
    operation_status: MarketOperationStatus,
    data_state: MarketDataState,
    payload: Any,
    correlation_id: str,
    request_id: str | None,
    failures: tuple[MarketFailure, ...] = (),
) -> MarketResultEnvelope:
    produced_at = _produced_at()
    return MarketResultEnvelope(
        contract_version=MARKET_PUBLIC_CONTRACT_VERSION,
        capability_id=capability,
        request_id=request_id,
        correlation_id=correlation_id,
        operation_status=operation_status,
        data_state=data_state,
        payload=payload,
        provenance=_provenance(capability, payload, correlation_id, produced_at),
        failures=failures,
        boundary_identity_ref=MARKET_BOUNDARY_IDENTITY_REF,
        runtime_observation=None,
        produced_at=produced_at,
    )


def _failure(
    capability: str,
    data_state: MarketDataState,
    kind: MarketFailureKind,
    code: str,
    message: str,
    correlation_id: str,
    request_id: str | None,
) -> MarketResultEnvelope:
    return _result(
        capability,
        operation_status=MarketOperationStatus.FAILURE,
        data_state=data_state,
        payload=None,
        correlation_id=correlation_id,
        request_id=request_id,
        failures=(MarketFailure(kind=kind, code=code, message=message),),
    )


class _MarketPublicProvider:
    """Private implementation; callers obtain it only from MarketPublicFactory."""

    def __init__(self, repository: Any):
        self._repository = repository

    async def execute(
        self,
        capability: str,
        request: Any,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> MarketResultEnvelope:
        correlation_id = correlation_id or str(uuid4())
        metadata = CAPABILITIES.get(capability)
        if metadata is None:
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                "unknown_capability",
                "Unknown Market capability",
                correlation_id,
                request_id,
            )
        try:
            if capability == "market.event.resolve":
                if not isinstance(request, EventResolveRequest) or request.limit < 1:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        "Invalid event resolve request",
                        correlation_id,
                        request_id,
                    )
                if request.limit > 200:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        "limit must be between 1 and 200",
                        correlation_id,
                        request_id,
                    )
                if request.feed_date is not None:
                    try:
                        datetime.strptime(request.feed_date, "%Y-%m-%d")
                    except (TypeError, ValueError):
                        return _failure(
                            capability,
                            MarketDataState.NOT_APPLICABLE,
                            MarketFailureKind.CONTRACT_MISMATCH,
                            "invalid_request",
                            "feed_date must use YYYY-MM-DD",
                            correlation_id,
                            request_id,
                        )
                data = await self._repository.fetch_intel_feed(
                    feed_date=request.feed_date, stock_id=request.stock_id,
                    item_type="event", limit=request.limit,
                )
                if request.stock_id:
                    data = [row for row in data if row.get("source_channel") != "jyhf_cdp"]
                return _result(
                    capability,
                    operation_status=MarketOperationStatus.SUCCESS,
                    data_state=MarketDataState.READY if data else MarketDataState.EMPTY,
                    payload=data,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.event.read":
                if not isinstance(request, EventReadRequest) or request.event_id < 1:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        "Invalid event read request",
                        correlation_id,
                        request_id,
                    )
                rows = await self._repository.fetch_intel_feed(item_type="event", limit=200)
                data = next((row for row in rows if _event_id_from_item(row.get("item_id")) == request.event_id), None)
                if data is None:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.OBJECT_NOT_FOUND,
                        "event_not_found",
                        "Event was not found",
                        correlation_id,
                        request_id,
                    )
                return _result(
                    capability,
                    operation_status=MarketOperationStatus.SUCCESS,
                    data_state=MarketDataState.READY,
                    payload=data,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.product.read":
                if (
                    not isinstance(request, ProductReadRequest)
                    or not isinstance(request.subject_key, str)
                    or not request.subject_key.strip()
                ):
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        "Invalid product request",
                        correlation_id,
                        request_id,
                    )
                data = await self._repository.fetch_theme_detail(request.subject_key)
                if data is None:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.OBJECT_NOT_FOUND,
                        "product_not_found",
                        "Product was not found",
                        correlation_id,
                        request_id,
                    )
                return _result(
                    capability,
                    operation_status=MarketOperationStatus.SUCCESS,
                    data_state=MarketDataState.READY,
                    payload=data,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                "unsupported_capability",
                "Unsupported capability",
                correlation_id,
                request_id,
            )
        except Exception as exc:
            if _is_dependency_failure(exc):
                return _failure(
                    capability,
                    MarketDataState.UNAVAILABLE,
                    MarketFailureKind.UNAVAILABLE,
                    "dependency_unavailable",
                    str(exc),
                    correlation_id,
                    request_id,
                )
            return _failure(
                capability,
                MarketDataState.UNAVAILABLE,
                MarketFailureKind.INTERNAL_FAILURE,
                "internal_failure",
                str(exc),
                correlation_id,
                request_id,
            )

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
