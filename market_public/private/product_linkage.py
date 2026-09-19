"""Private Market core for product-to-stock relationship evidence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


MAX_PRODUCT_LINKAGE_LIMIT = 200
PRODUCT_LINKAGE_MAPPING_SCOPES = frozenset({"pool", "leader_overlay", "all"})
PRODUCT_LINKAGE_ROW_FIELDS = (
    "subject_key",
    "theme_id",
    "theme_name",
    "stock_id",
    "stock_name",
    "relation_type_candidate",
    "mapping_scope",
    "source_type",
    "reason",
    "remark",
    "confidence",
    "top",
    "sort",
    "stock_remark",
)


class ProductLinkageStatus(str, Enum):
    READY = "READY"
    EMPTY = "EMPTY"
    INVALID_REQUEST = "INVALID_REQUEST"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


@dataclass(frozen=True)
class ProductLinkageRequest:
    subject_key: str
    mapping_scope: str = "pool"
    include_leaders: bool = False
    limit: int = 100


@dataclass(frozen=True)
class ProductLinkageRow:
    subject_key: Any
    theme_id: Any
    theme_name: Any
    stock_id: Any
    stock_name: Any
    relation_type_candidate: Any
    mapping_scope: Any
    source_type: Any
    reason: Any
    remark: Any
    confidence: Any
    top: Any
    sort: Any
    stock_remark: Any


@dataclass(frozen=True)
class ProductLinkageFailure:
    kind: ProductLinkageStatus
    code: str
    message: str


@dataclass(frozen=True)
class ProductLinkageResult:
    status: ProductLinkageStatus
    rows: tuple[ProductLinkageRow, ...] = ()
    failure: ProductLinkageFailure | None = None


class ProductLinkageDataIntegrityError(ValueError):
    """Raised when a repository row lacks required relationship identity."""


def _is_dependency_failure(exc: Exception) -> bool:
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
    dependency_types = tuple(
        dependency_type
        for dependency_type in (
            getattr(asyncpg, "PostgresConnectionError", None),
            getattr(asyncpg, "CannotConnectNowError", None),
            getattr(asyncpg, "ConnectionDoesNotExistError", None),
            getattr(asyncpg, "TooManyConnectionsError", None),
        )
        if isinstance(dependency_type, type)
    )
    return bool(dependency_types) and isinstance(exc, dependency_types)


class MarketProductLinkageReader:
    """Read repository linkage facts with a narrow private projection."""

    def __init__(self, repository: Any):
        self._repository = repository

    async def read(self, request: ProductLinkageRequest) -> ProductLinkageResult:
        invalid_reason = self._invalid_request_reason(request)
        if invalid_reason is not None:
            return self._failure(
                ProductLinkageStatus.INVALID_REQUEST,
                "invalid_request",
                invalid_reason,
            )

        try:
            repository_rows = await self._repository.fetch_stocks_by_theme(
                subject_key=request.subject_key,
                mapping_scope=request.mapping_scope,
                include_leaders=request.include_leaders,
                limit=request.limit,
            )
        except Exception as exc:
            failure_status = (
                ProductLinkageStatus.DEPENDENCY_UNAVAILABLE
                if _is_dependency_failure(exc)
                else ProductLinkageStatus.INTERNAL_FAILURE
            )
            failure_code = (
                "repository_unavailable"
                if failure_status is ProductLinkageStatus.DEPENDENCY_UNAVAILABLE
                else "repository_internal_failure"
            )
            return self._failure(
                failure_status,
                failure_code,
                str(exc) or exc.__class__.__name__,
            )

        try:
            rows = tuple(
                self._project(row, request.subject_key)
                for row in repository_rows
            )
        except Exception as exc:
            code = (
                "projection_data_integrity_failure"
                if isinstance(exc, ProductLinkageDataIntegrityError)
                else "projection_failed"
            )
            return self._failure(
                ProductLinkageStatus.INTERNAL_FAILURE,
                code,
                str(exc) or exc.__class__.__name__,
            )

        if not rows:
            return ProductLinkageResult(ProductLinkageStatus.EMPTY)
        return ProductLinkageResult(ProductLinkageStatus.READY, rows)

    @staticmethod
    def _invalid_request_reason(request: ProductLinkageRequest) -> str | None:
        if not isinstance(request, ProductLinkageRequest):
            return "request must be ProductLinkageRequest"
        if not isinstance(request.subject_key, str) or not request.subject_key.strip():
            return "subject_key must be a non-empty string"
        if (
            not isinstance(request.mapping_scope, str)
            or request.mapping_scope not in PRODUCT_LINKAGE_MAPPING_SCOPES
        ):
            return "mapping_scope must be pool, leader_overlay, or all"
        if not isinstance(request.include_leaders, bool):
            return "include_leaders must be boolean"
        if isinstance(request.limit, bool) or not isinstance(request.limit, int):
            return "limit must be an integer"
        if request.limit < 1 or request.limit > MAX_PRODUCT_LINKAGE_LIMIT:
            return f"limit must be between 1 and {MAX_PRODUCT_LINKAGE_LIMIT}"
        return None

    @staticmethod
    def _project(row: Any, requested_subject_key: str) -> ProductLinkageRow:
        if not isinstance(row, dict):
            raise TypeError("repository linkage row must be a mapping")
        for field_name in ("subject_key", "stock_id", "mapping_scope", "source_type"):
            value = row.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ProductLinkageDataIntegrityError(
                    f"repository linkage row requires non-empty string {field_name}"
                )
        if row["subject_key"] != requested_subject_key:
            raise ProductLinkageDataIntegrityError(
                "repository linkage row subject_key does not match request"
            )
        return ProductLinkageRow(
            subject_key=row.get("subject_key"),
            theme_id=row.get("theme_id"),
            theme_name=row.get("theme_name"),
            stock_id=row.get("stock_id"),
            stock_name=row.get("stock_name"),
            relation_type_candidate=row.get("relation_type_candidate"),
            mapping_scope=row.get("mapping_scope"),
            source_type=row.get("source_type"),
            reason=row.get("reason"),
            remark=row.get("remark"),
            confidence=row.get("confidence"),
            top=row.get("top"),
            sort=row.get("sort"),
            stock_remark=row.get("stock_remark"),
        )

    @staticmethod
    def _failure(
        status: ProductLinkageStatus,
        code: str,
        message: str,
    ) -> ProductLinkageResult:
        return ProductLinkageResult(
            status=status,
            failure=ProductLinkageFailure(
                kind=status,
                code=code,
                message=message,
            ),
        )
