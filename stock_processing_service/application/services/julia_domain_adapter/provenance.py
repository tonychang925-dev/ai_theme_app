"""AT-R3 provenance and degradation helpers for provider-native adapter results."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from .contracts import AdapterErrorCode, SourceFailure, SourceRecord


def classify_exception(exc: BaseException) -> tuple[str, str, bool]:
    """Return (adapter_status, error_code, retryable) for provider exceptions."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "unavailable", AdapterErrorCode.UPSTREAM_TIMEOUT.value, True
    if isinstance(exc, (ConnectionError, OSError)):
        return "unavailable", AdapterErrorCode.UPSTREAM_UNAVAILABLE.value, True
    return "error", AdapterErrorCode.INTERNAL_ERROR.value, False


def source_failure(
    *,
    source_name: str,
    message: str,
    code: str | None = None,
    retryable: bool = True,
    details: Mapping[str, Any] | None = None,
) -> SourceFailure:
    return SourceFailure(
        code=code or AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
        message=message,
        source_name=source_name,
        retryable=retryable,
        details=dict(details or {}),
    )


def missing_source_failure(source_name: str) -> SourceFailure:
    return source_failure(
        source_name=source_name,
        message=f"source unavailable: {source_name}",
        code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
        retryable=True,
        details={"dependency": dependency_kind(source_name)},
    )


def dependency_kind(source_name: str) -> str:
    text = source_name.lower()
    if "redis" in text or "stream" in text:
        return "redis"
    if "postgres" in text or "db" in text or "database" in text or "sql" in text:
        return "database"
    if "file" in text or "snapshot" in text or "workbench" in text:
        return "file_store"
    return "domain_source"


def normalize_raw_failure(raw: Mapping[str, Any]) -> SourceFailure:
    name = str(raw.get("source_name") or raw.get("source") or raw.get("name") or "domain_source")
    code = str(raw.get("code") or AdapterErrorCode.UPSTREAM_UNAVAILABLE.value)
    return source_failure(
        source_name=name,
        message=str(raw.get("message") or raw.get("reason") or f"source unavailable: {name}"),
        code=code,
        retryable=bool(raw.get("retryable", True)),
        details=raw.get("details", {}) if isinstance(raw.get("details"), Mapping) else {},
    )


def normalize_source_record(
    raw: Mapping[str, Any],
    *,
    default_as_of: str,
    default_observed_at: str,
    default_freshness: str,
) -> SourceRecord:
    failure = raw.get("failure")
    return SourceRecord(
        source_type=str(raw.get("source_type") or raw.get("type") or "domain_source"),
        source_name=str(raw.get("source_name") or raw.get("source") or raw.get("name") or "domain_source"),
        source_ref=str(raw.get("source_ref") or raw.get("ref") or ""),
        as_of=str(raw.get("as_of") or default_as_of),
        observed_at=str(raw.get("observed_at") or default_observed_at),
        freshness=str(raw.get("freshness") or default_freshness),
        status=str(raw.get("status") or "success"),
        provenance=raw.get("provenance", {}) if isinstance(raw.get("provenance"), Mapping) else {},
        failure=normalize_raw_failure(failure) if isinstance(failure, Mapping) else None,
    )


def source_record(
    *,
    source_type: str,
    source_name: str,
    source_ref: str,
    as_of: str,
    observed_at: str,
    freshness: str,
    status: str,
    provenance: Mapping[str, Any] | None = None,
    failure: SourceFailure | None = None,
) -> SourceRecord:
    return SourceRecord(
        source_type=source_type,
        source_name=source_name,
        source_ref=source_ref,
        as_of=as_of,
        observed_at=observed_at,
        freshness=freshness,
        status=status,
        provenance=dict(provenance or {}),
        failure=failure,
    )


__all__ = [
    "classify_exception",
    "dependency_kind",
    "missing_source_failure",
    "normalize_raw_failure",
    "normalize_source_record",
    "source_failure",
    "source_record",
]
