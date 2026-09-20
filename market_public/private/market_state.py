"""Private Market state reader for persisted post-market overview evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from enum import Enum
from typing import Any


MARKET_STATE_SOURCE_PATH = ("payload", "market_overview_review")
MARKET_STATE_SOURCE = "post_market_recap_snapshot.payload.market_overview_review"
WRAPPED_MARKET_STATE_SOURCE = (
    "post_market_recap_snapshot.payload.recap_doc.market_overview_review"
)


class MarketStateStatus(str, Enum):
    READY = "READY"
    INVALID_REQUEST = "INVALID_REQUEST"
    EMPTY = "EMPTY"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


@dataclass(frozen=True)
class MarketStateRequest:
    trade_date: str


@dataclass(frozen=True)
class MarketStateSnapshot:
    trade_date: str
    breadth: "MarketStateBreadth"
    source: str
    snapshot_version: str


@dataclass(frozen=True)
class MarketStateBreadth:
    up_count: int
    down_count: int
    up_ratio: float
    limit_up_count: int
    limit_down_count: int
    turnover_yi: float


@dataclass(frozen=True)
class MarketStateFailure:
    kind: MarketStateStatus
    code: str
    message: str


@dataclass(frozen=True)
class MarketStateResult:
    status: MarketStateStatus
    snapshot: MarketStateSnapshot | None = None
    failure: MarketStateFailure | None = None


class MarketStateReader:
    """Read one explicit trade date from the persisted recap snapshot."""

    def __init__(self, repository: Any):
        self._repository = repository

    async def read(self, request: MarketStateRequest) -> MarketStateResult:
        invalid_reason = self._invalid_request_reason(request)
        if invalid_reason is not None:
            return self._failure(
                MarketStateStatus.INVALID_REQUEST,
                "invalid_request",
                invalid_reason,
            )

        try:
            row = await self._repository.get_existing_post_market_recap_snapshot(
                request.trade_date
            )
        except Exception as exc:
            if _is_connectivity_exception(exc):
                return self._failure(
                    MarketStateStatus.DEPENDENCY_UNAVAILABLE,
                    "repository_unavailable",
                    str(exc) or exc.__class__.__name__,
                )
            return self._failure(
                MarketStateStatus.INTERNAL_FAILURE,
                "repository_protocol_failed",
                str(exc) or exc.__class__.__name__,
            )

        if row is None:
            return self._failure(
                MarketStateStatus.EMPTY,
                "snapshot_not_found",
                "post_market_recap_snapshot was not found for the explicit trade_date",
            )

        try:
            snapshot = self._project(row, request.trade_date)
        except _MarketStateDataIntegrityError as exc:
            return self._failure(
                MarketStateStatus.DATA_INTEGRITY_FAILURE,
                "market_overview_review_invalid",
                str(exc),
            )
        except Exception as exc:
            return self._failure(
                MarketStateStatus.INTERNAL_FAILURE,
                "projection_failed",
                str(exc) or exc.__class__.__name__,
            )
        return MarketStateResult(MarketStateStatus.READY, snapshot)

    @staticmethod
    def _invalid_request_reason(request: MarketStateRequest) -> str | None:
        if not isinstance(request, MarketStateRequest):
            return "request must be MarketStateRequest"
        if not isinstance(request.trade_date, str):
            return "trade_date must be a canonical YYYY-MM-DD string"
        try:
            parsed = date.fromisoformat(request.trade_date)
        except ValueError:
            return "trade_date must be a canonical YYYY-MM-DD string"
        if parsed.isoformat() != request.trade_date:
            return "trade_date must be a canonical YYYY-MM-DD string"
        return None

    @staticmethod
    def _project(row: Any, requested_date: str) -> MarketStateSnapshot | None:
        if not isinstance(row, dict):
            raise _MarketStateDataIntegrityError("snapshot row must be a mapping")
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise _MarketStateDataIntegrityError(
                    "snapshot payload must be JSON"
                ) from exc
        if not isinstance(payload, dict):
            raise _MarketStateDataIntegrityError("snapshot payload must be a mapping")
        recap_document = payload.get("recap_doc")
        wrapped = isinstance(recap_document, dict) and bool(recap_document)
        direct_overview = payload.get("market_overview_review")
        if wrapped:
            wrapped_overview = recap_document.get("market_overview_review")
            if (
                "market_overview_review" in payload
                and direct_overview != wrapped_overview
            ):
                raise _MarketStateDataIntegrityError(
                    "snapshot payload and recap_doc market_overview_review conflict"
                )
            if "market_overview_review" in payload:
                overview = direct_overview
                source = MARKET_STATE_SOURCE
            else:
                overview = wrapped_overview
                source = WRAPPED_MARKET_STATE_SOURCE
        else:
            overview = direct_overview
            source = MARKET_STATE_SOURCE
        if not isinstance(overview, dict):
            raise _MarketStateDataIntegrityError(
                "snapshot market_overview_review must be a mapping"
            )
        stored_date = row.get("trade_date")
        stored_date_text = (
            stored_date.isoformat()
            if hasattr(stored_date, "isoformat")
            else stored_date
        )
        if stored_date_text != requested_date:
            raise _MarketStateDataIntegrityError(
                "snapshot trade_date must exactly match the requested trade_date"
            )
        snapshot_version = row.get("snapshot_version")
        if not isinstance(snapshot_version, str) or not snapshot_version:
            raise _MarketStateDataIntegrityError(
                "snapshot_version must be a non-empty string"
            )
        up_count = _required_int(overview, "up_count")
        down_count = _required_int(overview, "down_count")
        limit_up_count = _required_int(overview, "limit_up_total")
        limit_down_count = _required_int(overview, "limit_down_total")
        total_amount_wan = _required_number(overview, "total_amount")
        return MarketStateSnapshot(
            trade_date=requested_date,
            breadth=MarketStateBreadth(
                up_count=up_count,
                down_count=down_count,
                up_ratio=round(up_count / max(up_count + down_count, 1), 3),
                limit_up_count=limit_up_count,
                limit_down_count=limit_down_count,
                turnover_yi=round(total_amount_wan / 10_000, 2),
            ),
            source=source,
            snapshot_version=snapshot_version,
        )

    @staticmethod
    def _failure(
        kind: MarketStateStatus,
        code: str,
        message: str,
    ) -> MarketStateResult:
        return MarketStateResult(
            status=kind,
            failure=MarketStateFailure(kind=kind, code=code, message=message),
        )


class _MarketStateDataIntegrityError(ValueError):
    """Private marker for malformed persisted market-overview evidence."""


def _is_connectivity_exception(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return exc.__class__.__name__ in {
        "PostgresConnectionError",
        "CannotConnectNowError",
        "ConnectionDoesNotExistError",
        "TooManyConnectionsError",
    }


def _required_int(mapping: dict[str, Any], field: str) -> int:
    value = _required_value(mapping, field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _MarketStateDataIntegrityError(f"{field} must be an integer")
    if value < 0:
        raise _MarketStateDataIntegrityError(f"{field} must be non-negative")
    return value


def _required_number(mapping: dict[str, Any], field: str) -> float:
    value = _required_value(mapping, field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _MarketStateDataIntegrityError(f"{field} must be numeric")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise _MarketStateDataIntegrityError(f"{field} must be finite")
    if number < 0:
        raise _MarketStateDataIntegrityError(f"{field} must be non-negative")
    return number


def _required_value(mapping: dict[str, Any], field: str) -> Any:
    if field not in mapping or mapping[field] is None:
        raise _MarketStateDataIntegrityError(f"{field} is required")
    return mapping[field]
