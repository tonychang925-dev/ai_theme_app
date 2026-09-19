"""Private Market state reader for persisted post-market overview evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from enum import Enum
from typing import Any


MARKET_STATE_SOURCE_PATH = ("payload", "market_overview_review")


class MarketStateStatus(str, Enum):
    READY = "READY"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


@dataclass(frozen=True)
class MarketStateRequest:
    trade_date: str


@dataclass(frozen=True)
class MarketStateSnapshot:
    trade_date: str
    market_overview_review: dict[str, Any]


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
            return self._failure(
                MarketStateStatus.DEPENDENCY_UNAVAILABLE,
                "repository_unavailable",
                str(exc) or exc.__class__.__name__,
            )

        if row is None:
            return self._failure(
                MarketStateStatus.NOT_FOUND,
                "snapshot_not_found",
                "post_market_recap_snapshot was not found for the explicit trade_date",
            )

        try:
            snapshot = self._project(row, request.trade_date)
        except Exception as exc:
            return self._failure(
                MarketStateStatus.INTERNAL_FAILURE,
                "projection_failed",
                str(exc) or exc.__class__.__name__,
            )
        if snapshot is None:
            return self._failure(
                MarketStateStatus.CONTRACT_MISMATCH,
                "market_overview_review_missing",
                "snapshot payload must contain mapping market_overview_review for the exact trade_date",
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
            return None
        payload = row.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return None
        overview = payload.get("market_overview_review")
        if not isinstance(overview, dict):
            return None
        stored_date = row.get("trade_date")
        stored_date_text = (
            stored_date.isoformat()
            if hasattr(stored_date, "isoformat")
            else stored_date
        )
        if stored_date_text != requested_date:
            return None
        return MarketStateSnapshot(
            trade_date=requested_date,
            market_overview_review=overview,
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
