"""Private aggregate analytical evidence reader for the Market public boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import json
from typing import Any


class MarketAnalysisStatus(str, Enum):
    READY = "READY"
    EMPTY = "EMPTY"
    INVALID_REQUEST = "INVALID_REQUEST"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


@dataclass(frozen=True)
class MarketAnalysisRequest:
    trade_date: str


@dataclass(frozen=True)
class MarketAnalysisFailure:
    kind: MarketAnalysisStatus
    code: str
    message: str


@dataclass(frozen=True)
class MarketAnalysisResult:
    status: MarketAnalysisStatus
    payload: dict[str, Any] | None = None
    failure: MarketAnalysisFailure | None = None


class _MarketAnalysisDataIntegrityError(ValueError):
    pass


class MarketAnalysisReader:
    """Project one persisted producer snapshot through the existing evidence chain."""

    def __init__(self, repository: Any):
        self._repository = repository

    async def read(self, request: MarketAnalysisRequest) -> MarketAnalysisResult:
        invalid_reason = self._invalid_request_reason(request)
        if invalid_reason is not None:
            return self._failure(
                MarketAnalysisStatus.INVALID_REQUEST,
                "invalid_request",
                invalid_reason,
            )

        try:
            row = await self._repository.get_existing_post_market_recap_snapshot(
                request.trade_date
            )
        except Exception as exc:
            if self._is_dependency_failure(exc):
                return self._failure(
                    MarketAnalysisStatus.DEPENDENCY_UNAVAILABLE,
                    "repository_unavailable",
                    str(exc) or exc.__class__.__name__,
                )
            return self._failure(
                MarketAnalysisStatus.INTERNAL_FAILURE,
                "repository_protocol_failed",
                str(exc) or exc.__class__.__name__,
            )

        if row is None:
            return MarketAnalysisResult(MarketAnalysisStatus.EMPTY)
        try:
            payload = self._project(row, request.trade_date)
        except _MarketAnalysisDataIntegrityError as exc:
            return self._failure(
                MarketAnalysisStatus.DATA_INTEGRITY_FAILURE,
                "market_analysis_source_invalid",
                str(exc),
            )
        except ImportError as exc:
            return self._failure(
                MarketAnalysisStatus.DEPENDENCY_UNAVAILABLE,
                "knowledge_projection_dependency_unavailable",
                str(exc) or exc.__class__.__name__,
            )
        except Exception as exc:
            return self._failure(
                MarketAnalysisStatus.INTERNAL_FAILURE,
                "market_analysis_projection_failed",
                str(exc) or exc.__class__.__name__,
            )
        return MarketAnalysisResult(MarketAnalysisStatus.READY, payload)

    @staticmethod
    def _invalid_request_reason(request: MarketAnalysisRequest) -> str | None:
        if not isinstance(request, MarketAnalysisRequest):
            return "request must be MarketAnalysisRequest"
        if not isinstance(request.trade_date, str):
            return "trade_date must be a canonical YYYY-MM-DD string"
        try:
            parsed = date.fromisoformat(request.trade_date)
        except ValueError:
            return "trade_date must be a canonical YYYY-MM-DD string"
        if parsed.isoformat() != request.trade_date:
            return "trade_date must be a canonical YYYY-MM-DD string"
        return None

    @classmethod
    def _project(cls, row: Any, requested_date: str) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise _MarketAnalysisDataIntegrityError("snapshot row must be a mapping")
        row_date = row.get("trade_date")
        canonical_row_date = (
            row_date.isoformat() if isinstance(row_date, date) else str(row_date or "")
        )
        if canonical_row_date != requested_date:
            raise _MarketAnalysisDataIntegrityError(
                "snapshot trade_date must match the exact requested trade_date"
            )
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise _MarketAnalysisDataIntegrityError(
                    "snapshot payload must be JSON"
                ) from exc
        if not isinstance(payload, dict) or not payload:
            raise _MarketAnalysisDataIntegrityError(
                "snapshot payload must be a non-empty mapping"
            )
        source_trade_date = payload.get("trade_date")
        if source_trade_date is not None and str(source_trade_date) != requested_date:
            raise _MarketAnalysisDataIntegrityError(
                "canonical payload trade_date must match the exact requested trade_date"
            )

        from stock_processing_service.application.services.market_cognition.knowledge_evidence import (
            MarketEvidenceAdapter,
            MarketKnowledgeBundleBuilder,
        )

        try:
            bundle = MarketKnowledgeBundleBuilder.build(payload, requested_date)
            evidence = MarketEvidenceAdapter.build(bundle)
        except (TypeError, ValueError) as exc:
            raise _MarketAnalysisDataIntegrityError(str(exc)) from exc
        if not evidence.evidence:
            raise _MarketAnalysisDataIntegrityError(
                "producer snapshot contains no referenced analytical evidence"
            )

        source_refs = [
            value
            for value in (
                f"post_market_recap_snapshot:{requested_date}",
                _optional_string(row.get("snapshot_version")),
                _optional_string(row.get("batch_id")),
                _optional_string(row.get("trace_id")),
                *bundle.source_snapshot_ids,
            )
            if value is not None
        ]
        return {
            "schema_version": "market.analysis.v1",
            "trade_date": evidence.trade_date,
            "as_of": evidence.as_of.isoformat(),
            "source": {
                "snapshot_ref": "post_market_recap_snapshot",
                "snapshot_identity": (f"post_market_recap_snapshot:{requested_date}"),
                "snapshot_version": _optional_string(row.get("snapshot_version")),
                "source_snapshot_ids": list(dict.fromkeys(bundle.source_snapshot_ids)),
                "batch_id": _optional_string(row.get("batch_id")),
                "trace_id": _optional_string(row.get("trace_id")),
                "producer_versions": [
                    {"module": module, "version": version}
                    for module, version in bundle.producer_versions
                ],
                "source_refs": list(dict.fromkeys(source_refs)),
            },
            "evidence_snapshot_id": evidence.snapshot_id,
            "source_bundle_id": evidence.source_bundle_id,
            "content_hash": evidence.content_hash,
            "evidence": [_evidence_item(item) for item in evidence.evidence],
            "module_coverage": [_coverage(item) for item in evidence.module_coverage],
            "quality": {
                "status": evidence.quality.status,
                "score": evidence.quality.score,
                "missing_modules": list(evidence.quality.missing_modules),
                "issues": list(evidence.quality.issues),
            },
            "review_maturity": cls._review_maturity(payload),
        }

    @classmethod
    def _review_maturity(cls, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = [payload]
        recap_document = payload.get("recap_doc")
        if isinstance(recap_document, dict):
            candidates.append(recap_document)
        daily_review = (
            recap_document.get("daily_review_v2")
            if isinstance(recap_document, dict)
            else payload.get("daily_review_v2")
        )
        if isinstance(daily_review, dict):
            candidates.append(daily_review)

        fields: dict[str, Any] = {}
        origin: dict[str, str] = {}
        origins = ("payload", "recap_doc", "daily_review_v2")
        for source_index, candidate in enumerate(candidates):
            for field in (
                "review_maturity",
                "source_mode",
                "approval_mode",
                "approved",
                "approved_at",
                "approved_by",
                "published",
                "published_at",
                "analyst_reviewed",
                "review_status",
            ):
                if field not in candidate:
                    continue
                value = candidate[field]
                if field in fields and fields[field] != value:
                    raise _MarketAnalysisDataIntegrityError(
                        "canonical review maturity fields conflict"
                    )
                fields[field] = value
                origin[field] = origins[source_index]

        if not fields:
            return {
                "available": False,
                "source_mode": "unavailable",
                "source": "not_bound",
                "reason": (
                    "review maturity is not present in the canonical recap payload"
                ),
            }
        return {
            "available": True,
            "source": "canonical_recap",
            "field_origins": origin,
            "fields": fields,
        }

    @staticmethod
    def _is_dependency_failure(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError, OSError, ImportError)):
            return True
        return exc.__class__.__name__ in {
            "PostgresConnectionError",
            "CannotConnectNowError",
            "ConnectionDoesNotExistError",
            "TooManyConnectionsError",
        }

    @staticmethod
    def _failure(
        status: MarketAnalysisStatus, code: str, message: str
    ) -> MarketAnalysisResult:
        return MarketAnalysisResult(
            status=status,
            failure=MarketAnalysisFailure(
                kind=status,
                code=code,
                message=message,
            ),
        )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _coverage(item: Any) -> dict[str, Any]:
    return {
        "module": item.module,
        "status": item.status,
        "row_count": item.row_count,
        "missing_fields": list(item.missing_fields),
    }


def _evidence_item(item: Any) -> dict[str, Any]:
    return {
        "key": item.key,
        "value": _jsonable(item.value),
        "ref": {
            "ref_id": item.ref.ref_id,
            "source_module": item.ref.source_module,
            "source_path": item.ref.source_path,
            "source_snapshot_id": item.ref.source_snapshot_id,
        },
        "observed_at": item.observed_at.isoformat(),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
