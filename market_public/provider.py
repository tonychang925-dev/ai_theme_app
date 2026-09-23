"""The sole Julia-facing Market provider."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from datetime import date, datetime, timezone
import re
from typing import Any
from uuid import uuid4

from .contracts import (
    CAPABILITIES,
    MARKET_BOUNDARY_IDENTITY_REF,
    MARKET_PUBLIC_CONTRACT_VERSION,
    EventReadRequest,
    EventResolveRequest,
    MarketAnalysisReadRequest,
    MarketDataState,
    MarketFailure,
    MarketFailureKind,
    MarketOperationStatus,
    MarketResultEnvelope,
    MarketStateReadRequest,
    ProductLinkageReadRequest,
    ProductReadRequest,
    StockQuoteReadRequest,
)
from .private.market_state import (
    MarketStateReader,
    MarketStateRequest,
    MarketStateStatus,
)
from .private.market_analysis import (
    MarketAnalysisReader,
    MarketAnalysisRequest,
    MarketAnalysisStatus,
)
from .private.product_linkage import (
    MarketProductLinkageReader,
    ProductLinkageRequest,
    ProductLinkageStatus,
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
            "PostgresConnectionError",
            "CannotConnectNowError",
            "ConnectionDoesNotExistError",
            "TooManyConnectionsError",
        }
    types = tuple(
        cls
        for cls in (
            getattr(asyncpg, "PostgresConnectionError", None),
            getattr(asyncpg, "CannotConnectNowError", None),
            getattr(asyncpg, "ConnectionDoesNotExistError", None),
            getattr(asyncpg, "TooManyConnectionsError", None),
        )
        if isinstance(cls, type)
    )
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
        for key in (
            "source_ref",
            "source_channel",
            "source_system",
            "source",
            "source_type",
            "source_name",
        ):
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
        for key in ("item_id", "subject_key", "product_id", "stock_id"):
            value = row.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                refs.add(str(value).strip())
    return tuple(sorted(refs))


def _provenance(
    capability: str, data: Any, correlation_id: str, produced_at: str
) -> MarketProvenance:
    # No capability-specific mandatory provenance profile is frozen for these
    # current runtime capabilities. Preserve available evidence, but keep the
    # status explicitly INCOMPLETE until a concrete profile is selected.
    source_refs = _source_refs(data)
    evidence_refs: tuple[str, ...] = ()
    public_object_refs = _public_object_refs(data)
    data_cutoff = None
    if capability == "market.analysis.read" and isinstance(data, dict):
        source = data.get("source")
        if isinstance(source, dict):
            source_refs = tuple(
                dict.fromkeys(
                    [
                        *source_refs,
                        *(
                            str(value)
                            for value in source.get("source_refs", [])
                            if value
                        ),
                    ]
                )
            )
        evidence_refs = tuple(
            dict.fromkeys(
                str(item.get("ref", {}).get("ref_id"))
                for item in data.get("evidence", [])
                if isinstance(item, dict)
                and isinstance(item.get("ref"), dict)
                and item["ref"].get("ref_id")
            )
        )
        public_object_refs = tuple(
            dict.fromkeys(
                [
                    *public_object_refs,
                    *(
                        str(value)
                        for value in (
                            data.get("evidence_snapshot_id"),
                            data.get("source_bundle_id"),
                        )
                        if value
                    ),
                ]
            )
        )
        data_cutoff = data.get("as_of")
    return MarketProvenance(
        None,
        produced_at=produced_at,
        market_release_identity=None,
        data_cutoff=data_cutoff,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        public_object_refs=public_object_refs,
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
        self._product_linkage_reader = MarketProductLinkageReader(repository)
        self._market_state_reader = MarketStateReader(repository)
        self._market_analysis_reader = MarketAnalysisReader(repository)

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
                    feed_date=request.feed_date,
                    stock_id=request.stock_id,
                    item_type="event",
                    limit=request.limit,
                )
                if request.stock_id:
                    data = [
                        row for row in data if row.get("source_channel") != "jyhf_cdp"
                    ]
                return _result(
                    capability,
                    operation_status=MarketOperationStatus.SUCCESS,
                    data_state=MarketDataState.READY if data else MarketDataState.EMPTY,
                    payload=data,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.event.read":
                invalid_reason = _invalid_event_read_reason(request)
                if invalid_reason is not None:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        invalid_reason,
                        correlation_id,
                        request_id,
                    )
                if request.item_id is not None:
                    data = await self._repository.fetch_intel_event_by_item_id(
                        request.item_id
                    )
                else:
                    data = await self._repository.fetch_intel_event_by_event_id(
                        request.event_id
                    )
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
            if capability == "market.product.linkage.read":
                return await self._execute_product_linkage(
                    request,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.state.read":
                return await self._execute_market_state(
                    request,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.analysis.read":
                return await self._execute_market_analysis(
                    request,
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
            if capability == "market.stock.quote.read":
                invalid_reason = _invalid_stock_quote_read_reason(request)
                if invalid_reason is not None:
                    return _failure(
                        capability,
                        MarketDataState.NOT_APPLICABLE,
                        MarketFailureKind.CONTRACT_MISMATCH,
                        "invalid_request",
                        invalid_reason,
                        correlation_id,
                        request_id,
                    )
                data = await self._repository.get_stock_daily_quote(
                    stock_id=request.stock_id,
                    trade_date=request.trade_date,
                )
                if data is None:
                    return _result(
                        capability,
                        operation_status=MarketOperationStatus.SUCCESS,
                        data_state=MarketDataState.EMPTY,
                        payload=None,
                        correlation_id=correlation_id,
                        request_id=request_id,
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

    async def _execute_product_linkage(
        self,
        request: Any,
        *,
        correlation_id: str,
        request_id: str | None,
    ) -> MarketResultEnvelope:
        capability = "market.product.linkage.read"
        if not isinstance(request, ProductLinkageReadRequest):
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                "invalid_request",
                "Invalid product linkage request",
                correlation_id,
                request_id,
            )
        private_result = await self._product_linkage_reader.read(
            ProductLinkageRequest(
                subject_key=request.subject_key,
                mapping_scope=request.mapping_scope,
                include_leaders=request.include_leaders,
                limit=request.limit,
            )
        )
        if private_result.status is ProductLinkageStatus.READY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.READY,
                payload=[asdict(row) for row in private_result.rows],
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is ProductLinkageStatus.EMPTY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.EMPTY,
                payload=[],
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is ProductLinkageStatus.INVALID_REQUEST:
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        if private_result.status is ProductLinkageStatus.DEPENDENCY_UNAVAILABLE:
            return _failure(
                capability,
                MarketDataState.UNAVAILABLE,
                MarketFailureKind.UNAVAILABLE,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        return _failure(
            capability,
            MarketDataState.UNAVAILABLE,
            MarketFailureKind.INTERNAL_FAILURE,
            private_result.failure.code,
            private_result.failure.message,
            correlation_id,
            request_id,
        )

    async def _execute_market_state(
        self,
        request: Any,
        *,
        correlation_id: str,
        request_id: str | None,
    ) -> MarketResultEnvelope:
        capability = "market.state.read"
        if not isinstance(request, MarketStateReadRequest):
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                "invalid_request",
                "Invalid market state request",
                correlation_id,
                request_id,
            )
        private_result = await self._market_state_reader.read(
            MarketStateRequest(trade_date=request.trade_date)
        )
        if private_result.status is MarketStateStatus.READY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.READY,
                payload=asdict(private_result.snapshot),
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is MarketStateStatus.EMPTY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.EMPTY,
                payload=None,
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is MarketStateStatus.INVALID_REQUEST:
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        if private_result.status is MarketStateStatus.DEPENDENCY_UNAVAILABLE:
            return _failure(
                capability,
                MarketDataState.UNAVAILABLE,
                MarketFailureKind.UNAVAILABLE,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        return _failure(
            capability,
            MarketDataState.UNAVAILABLE,
            MarketFailureKind.INTERNAL_FAILURE,
            private_result.failure.code,
            private_result.failure.message,
            correlation_id,
            request_id,
        )

    async def _execute_market_analysis(
        self,
        request: Any,
        *,
        correlation_id: str,
        request_id: str | None,
    ) -> MarketResultEnvelope:
        capability = "market.analysis.read"
        if not isinstance(request, MarketAnalysisReadRequest):
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                "invalid_request",
                "Invalid market analysis request",
                correlation_id,
                request_id,
            )
        private_result = await self._market_analysis_reader.read(
            MarketAnalysisRequest(trade_date=request.trade_date)
        )
        if private_result.status is MarketAnalysisStatus.READY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.READY,
                payload=private_result.payload,
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is MarketAnalysisStatus.EMPTY:
            return _result(
                capability,
                operation_status=MarketOperationStatus.SUCCESS,
                data_state=MarketDataState.EMPTY,
                payload=None,
                correlation_id=correlation_id,
                request_id=request_id,
            )
        if private_result.status is MarketAnalysisStatus.INVALID_REQUEST:
            return _failure(
                capability,
                MarketDataState.NOT_APPLICABLE,
                MarketFailureKind.CONTRACT_MISMATCH,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        if private_result.status is MarketAnalysisStatus.DEPENDENCY_UNAVAILABLE:
            return _failure(
                capability,
                MarketDataState.UNAVAILABLE,
                MarketFailureKind.UNAVAILABLE,
                private_result.failure.code,
                private_result.failure.message,
                correlation_id,
                request_id,
            )
        return _failure(
            capability,
            MarketDataState.UNAVAILABLE,
            MarketFailureKind.INTERNAL_FAILURE,
            private_result.failure.code,
            private_result.failure.message,
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


def _invalid_event_read_reason(request: Any) -> str | None:
    if not isinstance(request, EventReadRequest):
        return "request must be EventReadRequest"
    if (request.event_id is None) == (request.item_id is None):
        return "exactly one of event_id or item_id is required"
    if request.event_id is not None:
        if (
            isinstance(request.event_id, bool)
            or not isinstance(request.event_id, int)
            or request.event_id < 1
        ):
            return "event_id must be a positive integer"
    else:
        item_id = request.item_id
        if not isinstance(item_id, str):
            return "item_id must be a source-namespaced string"
        valid_identity = re.fullmatch(r"event:\d+:.+", item_id) or re.fullmatch(
            r"event:jyhf_cdp:\d+", item_id
        )
        if valid_identity is None:
            return "item_id must be a canonical source-namespaced event identity"
    return None


def _invalid_stock_quote_read_reason(request: Any) -> str | None:
    if not isinstance(request, StockQuoteReadRequest):
        return "request must be StockQuoteReadRequest"
    if not isinstance(request.stock_id, str) or not request.stock_id.strip():
        return "stock_id must be a non-empty string"
    if not isinstance(request.trade_date, str):
        return "trade_date must use YYYY-MM-DD"
    parsed_date = None
    with suppress(TypeError, ValueError):
        parsed_date = date.fromisoformat(request.trade_date)
    if parsed_date is None or parsed_date.isoformat() != request.trade_date:
        return "trade_date must use YYYY-MM-DD"
    return None
