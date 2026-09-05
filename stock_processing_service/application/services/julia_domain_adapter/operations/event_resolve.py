"""I2A Market-owned canonical market event resolver."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
import os
from typing import Any, Mapping

from ..contracts import (
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    redact_diagnostics,
)
from ..provenance import classify_exception, source_failure, source_record

EVENT_SOURCE_NAME = "event_subject_map→news_event"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_QUERY_LENGTH = 512
MAX_THEME_LENGTH = 256
MAX_DIAGNOSTIC_TEXT_LENGTH = 2048
ALLOWED_ARGUMENTS = frozenset({"query", "normalized_theme", "time_window", "limit"})
OPERATION_SYMBOL = "event_resolve.py:MarketEventResolveOperation.execute"
FAILURE_LAYER = "MarketEventResolveOperation._resolve"
CANDIDATE_FAILURE_LAYER = "MarketEventResolveOperation._candidate"

logger = logging.getLogger("sps.julia_domain_adapter.market_event_resolve")


class MarketEventResolveOperation:
    def __init__(self, *, database_gateway: object | None = None, clock: object | None = None) -> None:
        self._database_gateway = database_gateway
        self._clock = clock

    async def execute(self, request: AdapterRequest) -> DomainObservationEnvelope:
        observed_at = self._now()
        validated = self._validate(request)
        if isinstance(validated, DomainObservationEnvelope):
            return validated
        query, normalized_theme, time_window, limit = validated

        if self._database_gateway is None:
            return self._failure(
                request,
                observed_at,
                message="database gateway not configured",
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                retryable=True,
                diagnostics={"reason": "database_gateway_not_configured"},
            )
        try:
            raw_candidates = await self._resolve(query, normalized_theme, time_window, limit)
        except Exception as exc:
            status, code, retryable = classify_exception(exc)
            diagnostics = {
                "reason": "market_event_resolution_failed",
                "error_type": type(exc).__name__,
                "pre_collapse_failure": self._exception_diagnostics(
                    exc=exc,
                    request=request,
                    observed_at=observed_at,
                    query=query,
                    normalized_theme=normalized_theme,
                    time_window=time_window,
                ),
            }
            logger.error(
                "market event resolve failed operation_symbol=%s failure_layer=%s diagnostics=%s",
                OPERATION_SYMBOL,
                FAILURE_LAYER,
                diagnostics["pre_collapse_failure"],
            )
            return self._failure(
                request,
                observed_at,
                message=self._bounded_text(f"{type(exc).__name__}: {exc}"),
                code=code,
                retryable=retryable,
                diagnostics=diagnostics,
                status=status,
            )
        if not isinstance(raw_candidates, list):
            return self._failure(
                request,
                observed_at,
                message="resolver returned a non-list payload",
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                retryable=False,
                diagnostics={"reason": "invalid_resolver_payload"},
            )

        bounded_candidates = raw_candidates[:limit]
        candidates = []
        try:
            for candidate_index, item in enumerate(bounded_candidates):
                candidates.append(self._candidate(item))
        except Exception as exc:
            matched_subjects = (
                item.get("matched_subjects")
                if isinstance(item, Mapping)
                else None
            )
            candidate_diagnostics = self._exception_diagnostics(
                exc=exc,
                request=request,
                observed_at=observed_at,
                query=query,
                normalized_theme=normalized_theme,
                time_window=time_window,
                failure_layer=CANDIDATE_FAILURE_LAYER,
                candidate_index=candidate_index,
                raw_candidate_count=len(bounded_candidates),
                matched_subjects_type=type(matched_subjects).__name__,
            )
            return self._failure(
                request,
                observed_at,
                message=f"resolver returned invalid candidate: {exc}",
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                retryable=False,
                diagnostics={
                    "reason": "invalid_candidate",
                    "error_type": type(exc).__name__,
                    "pre_collapse_failure": candidate_diagnostics,
                },
            )

        state = "UNRESOLVED" if not candidates else ("RESOLVED" if len(candidates) == 1 else "AMBIGUOUS")
        payload: dict[str, Any] = {
            "state": state,
            "query": query,
            "candidates": candidates,
        }
        if state == "RESOLVED":
            payload["selected_event_id"] = candidates[0]["market_event_id"]
        return DomainObservationEnvelope(
            operation=request.operation,
            status="success",
            data_state="empty" if not candidates else "normal",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload=payload,
            source_records=[self._source_record(candidates, observed_at)],
            failures=[],
            diagnostics={
                "canonical_id_source": "public.news_event.id",
                "candidate_count": len(candidates),
                "limit": limit,
                "normalized_theme": normalized_theme,
                "time_window": time_window,
            },
        )

    def _validate(self, request: AdapterRequest) -> tuple[str, str | None, dict[str, Any], int] | DomainObservationEnvelope:
        observed_at = self._now()
        unsupported = sorted(set(request.arguments) - ALLOWED_ARGUMENTS)
        if unsupported:
            return self._invalid(request, observed_at, f"unsupported arguments: {', '.join(unsupported)}")
        query = request.arguments.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
            return self._invalid(request, observed_at, "query must be a non-empty bounded string")
        normalized_theme = request.arguments.get("normalized_theme")
        if normalized_theme is not None and (
            not isinstance(normalized_theme, str)
            or not normalized_theme.strip()
            or len(normalized_theme) > MAX_THEME_LENGTH
        ):
            return self._invalid(request, observed_at, "normalized_theme must be a non-empty bounded string")
        limit = request.arguments.get("limit", DEFAULT_LIMIT)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
            return self._invalid(request, observed_at, f"limit must be an integer from 1 to {MAX_LIMIT}")
        try:
            time_window = self._time_window(request.arguments.get("time_window"))
        except ValueError as exc:
            return self._invalid(request, observed_at, str(exc))
        return query.strip(), normalized_theme.strip() if normalized_theme is not None else None, time_window, limit

    @staticmethod
    def _time_window(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping) or not {"date", "start_at", "end_at"}.intersection(value):
            raise ValueError("time_window must contain date or start_at/end_at")
        if set(value) - {"date", "start_at", "end_at"}:
            raise ValueError("time_window has unsupported fields")
        if "date" in value and ("start_at" in value or "end_at" in value):
            raise ValueError("time_window cannot mix date with start_at/end_at")
        result: dict[str, Any] = {}
        if "date" in value:
            try:
                result["date"] = date.fromisoformat(str(value["date"]))
            except ValueError as exc:
                raise ValueError("time_window.date must be ISO-8601") from exc
        if {"start_at", "end_at"}.intersection(value):
            if not {"start_at", "end_at"}.issubset(value):
                raise ValueError("time_window requires both start_at and end_at")
            try:
                result["start_at"] = datetime.fromisoformat(str(value["start_at"]))
                result["end_at"] = datetime.fromisoformat(str(value["end_at"]))
            except ValueError as exc:
                raise ValueError("time_window start_at/end_at must be ISO-8601") from exc
            if result["start_at"] >= result["end_at"]:
                raise ValueError("time_window end_at must be after start_at")
        return result

    async def _resolve(
        self,
        query: str,
        normalized_theme: str | None,
        time_window: dict[str, Any],
        limit: int,
    ) -> Any:
        method = getattr(self._database_gateway, "resolve_market_event_candidates", None)
        if not callable(method):
            raise TypeError("database gateway has no callable resolve_market_event_candidates")
        result = method(
            query=query,
            normalized_theme=normalized_theme,
            time_window=time_window,
            limit=limit,
        )
        if asyncio.iscoroutine(result):
            return await result
        return result

    @staticmethod
    def _candidate(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise TypeError("candidate must be an object")
        event_id = raw.get("market_event_id", raw.get("event_id"))
        if isinstance(event_id, bool) or not isinstance(event_id, int):
            raise TypeError("market_event_id must be an integer")
        title = raw.get("title") or raw.get("summary") or f"Event #{event_id}"
        subjects = raw.get("matched_subjects", [])
        if not isinstance(subjects, list):
            raise TypeError("matched_subjects must be an array")
        return {
            "market_event_id": event_id,
            "title": str(title),
            "summary": str(raw.get("summary") or ""),
            "occurred_at": MarketEventResolveOperation._timestamp(
                raw.get("occurred_at", raw.get("event_time", raw.get("created_at")))
            ),
            "matched_subjects": subjects,
        }

    def _exception_diagnostics(
        self,
        *,
        exc: Exception,
        request: AdapterRequest,
        observed_at: str,
        query: str,
        normalized_theme: str | None,
        time_window: dict[str, Any],
        failure_layer: str = FAILURE_LAYER,
        candidate_index: int | None = None,
        raw_candidate_count: int | None = None,
        matched_subjects_type: str | None = None,
    ) -> dict[str, Any]:
        sqlstate = getattr(exc, "sqlstate", None)
        pgcode = getattr(exc, "pgcode", None)
        errno = getattr(exc, "errno", None)
        error_code = getattr(exc, "code", None)
        trace = request.trace_metadata if isinstance(request.trace_metadata, Mapping) else {}
        diagnostics = {
            "operation_symbol": OPERATION_SYMBOL,
            "failure_layer": failure_layer,
            "exception_class": type(exc).__name__,
            "exception_message": self._bounded_text(str(exc)),
            "sqlstate": self._bounded_text(sqlstate) if sqlstate is not None else None,
            "pgcode": self._bounded_text(pgcode) if pgcode is not None else None,
            "errno": self._bounded_text(errno) if errno is not None else None,
            "error_code": self._bounded_text(error_code) if error_code is not None else None,
            "precollapse_provider_status": self._provider_status(exc),
            "process_pid": os.getpid(),
            "observed_at": observed_at,
            "resolver_query": self._bounded_text(query, MAX_QUERY_LENGTH),
            "normalized_theme": (
                self._bounded_text(normalized_theme, MAX_THEME_LENGTH)
                if normalized_theme is not None
                else None
            ),
            "time_window": {
                key: self._bounded_text(time_window[key])
                for key in ("date", "start_at", "end_at")
                if key in time_window
            },
            "correlation_id": self._bounded_text(request.correlation_id),
            "idempotency_id": self._bounded_text(request.idempotency_key),
            "capability_request_id": (
                self._bounded_text(trace["capability_request_id"])
                if trace.get("capability_request_id") is not None
                else None
            ),
            "capability_call_id": None,
        }
        if candidate_index is not None or raw_candidate_count is not None or matched_subjects_type is not None:
            diagnostics.update({
                "candidate_index": candidate_index,
                "raw_candidate_count": raw_candidate_count,
                "matched_subjects_type": matched_subjects_type,
            })
        return diagnostics

    @staticmethod
    def _provider_status(exc: Exception) -> str | None:
        for attribute in ("provider_status", "upstream_status", "status"):
            value = getattr(exc, attribute, None)
            if value is not None:
                return MarketEventResolveOperation._bounded_text(value, 256)
        return None

    @staticmethod
    def _bounded_text(value: Any, limit: int = MAX_DIAGNOSTIC_TEXT_LENGTH) -> str:
        text = str(redact_diagnostics(value))
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)].rstrip() + "..."

    @staticmethod
    def _timestamp(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _invalid(
        self,
        request: AdapterRequest,
        observed_at: str,
        message: str,
    ) -> DomainObservationEnvelope:
        return self._failure(
            request,
            observed_at,
            message=message,
            code=AdapterErrorCode.INVALID_ARGUMENT.value,
            retryable=False,
            diagnostics={"reason": "invalid_arguments"},
            status="error",
        )

    def _failure(
        self,
        request: AdapterRequest,
        observed_at: str,
        *,
        message: str,
        code: str,
        retryable: bool,
        diagnostics: dict[str, Any],
        status: str = "unavailable",
    ) -> DomainObservationEnvelope:
        failure = source_failure(
            source_name=EVENT_SOURCE_NAME,
            message=message,
            code=code,
            retryable=retryable,
            details=diagnostics,
        )
        record = source_record(
            source_type="database",
            source_name=EVENT_SOURCE_NAME,
            source_ref="public.event_subject_map→public.news_event",
            as_of="",
            observed_at=observed_at,
            freshness="unknown",
            status="failed",
            provenance={
                "database": "postgresql",
                "schema": "public",
                "tables": ["event_subject_map", "news_event"],
                "read_boundary": "DatabaseGateway.resolve_market_event_candidates",
            },
            failure=failure,
        )
        return DomainObservationEnvelope(
            operation=request.operation,
            status=status,
            data_state="empty",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload={},
            source_records=[record],
            failures=[failure],
            diagnostics=diagnostics,
        )

    def _source_record(self, candidates: list[dict[str, Any]], observed_at: str) -> Any:
        as_of = next((item["occurred_at"] for item in candidates if item["occurred_at"]), "")
        return source_record(
            source_type="database",
            source_name=EVENT_SOURCE_NAME,
            source_ref="public.event_subject_map→public.news_event",
            as_of=as_of,
            observed_at=observed_at,
            freshness="source_timestamp_based",
            status="success",
            provenance={
                "database": "postgresql",
                "schema": "public",
                "tables": ["event_subject_map", "news_event"],
                "canonical_id": "public.news_event.id",
                "read_boundary": "DatabaseGateway.resolve_market_event_candidates",
                "candidate_ids": [item["market_event_id"] for item in candidates],
            },
        )

    def _now(self) -> str:
        value = self._clock.now() if self._clock is not None else datetime.now().astimezone()
        return value.isoformat()
