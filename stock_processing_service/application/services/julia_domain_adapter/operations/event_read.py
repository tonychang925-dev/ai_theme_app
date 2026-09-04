"""M1A market.event.read operation backed by the canonical event tables."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping

from ..contracts import (
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
)
from ..provenance import classify_exception, source_failure, source_record

CST = timezone(timedelta(hours=8))
EVENT_SOURCE_NAME = "news_event"
RELATION_SOURCE_NAME = "event_subject_map"
EXCLUDED_NOT_PROVEN_FIELDS = (
    "related_symbols",
    "entities",
    "causal_claim",
    "evidence_set",
    "raw_event_json",
    "severity_score",
    "source_weight",
    "lifecycle",
    "market_heat",
    "theme_state",
    "analyst_claims",
)


class MarketEventReadOperation:
    def __init__(self, *, database_gateway: object | None = None, clock: object | None = None) -> None:
        self._database_gateway = database_gateway
        self._clock = clock

    async def execute(self, request: AdapterRequest) -> DomainObservationEnvelope:
        observed_at = self._now()
        raw_event_id = request.arguments.get("event_id")
        if isinstance(raw_event_id, bool) or not isinstance(raw_event_id, int):
            return self._empty(
                request,
                observed_at,
                source_name=EVENT_SOURCE_NAME,
                code=AdapterErrorCode.INVALID_ARGUMENT.value,
                message="event_id must be an integer news_event.id",
                retryable=False,
                diagnostics={"reason": "invalid_event_id", "event_id_type": type(raw_event_id).__name__},
                status="error",
            )

        event_id = int(raw_event_id)
        if self._database_gateway is None:
            return self._empty(
                request,
                observed_at,
                source_name="database_gateway",
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                message="database gateway not configured",
                retryable=True,
                diagnostics={"reason": "database_gateway_not_configured"},
            )

        try:
            raw = await self._read_event(event_id)
        except Exception as exc:
            status, code, retryable = classify_exception(exc)
            return self._empty(
                request,
                observed_at,
                source_name=EVENT_SOURCE_NAME,
                code=code,
                message=f"{type(exc).__name__}: {exc}",
                retryable=retryable,
                diagnostics={"reason": "event_read_failed", "error_type": type(exc).__name__, "event_id": event_id},
                status=status,
            )

        if raw is None:
            return self._empty(
                request,
                observed_at,
                source_name=EVENT_SOURCE_NAME,
                code=AdapterErrorCode.NOT_FOUND.value,
                message=f"news_event not found: {event_id}",
                retryable=False,
                diagnostics={"reason": "event_not_found", "event_id": event_id},
            )
        if not isinstance(raw, Mapping):
            return self._empty(
                request,
                observed_at,
                source_name=EVENT_SOURCE_NAME,
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="database gateway returned non-object event",
                retryable=False,
                diagnostics={"reason": "invalid_event_shape", "raw_type": type(raw).__name__, "event_id": event_id},
            )
        event = dict(raw)
        try:
            source_event_id = int(event["id"])
        except (KeyError, TypeError, ValueError):
            source_event_id = None
        if source_event_id != event_id:
            return self._empty(
                request,
                observed_at,
                source_name=EVENT_SOURCE_NAME,
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="news_event returned an unstable or missing event id",
                retryable=False,
                diagnostics={"reason": "event_id_mismatch", "event_id": event_id},
            )

        relation_failures: list[SourceFailure] = []
        relation_status = "success"
        relations: list[dict[str, Any]] = []
        try:
            raw_relations = await self._read_relations(event_id)
            if not isinstance(raw_relations, list):
                raise TypeError("relation reader returned non-list payload")
            relations = [self._map_relation(item, event_id) for item in raw_relations]
        except Exception as exc:
            _, code, retryable = classify_exception(exc)
            relation_failures.append(source_failure(
                source_name=RELATION_SOURCE_NAME,
                message=f"{type(exc).__name__}: {exc}",
                code=code,
                retryable=retryable,
                details={"event_id": event_id, "error_type": type(exc).__name__},
            ))
            relation_status = "failed"

        event_payload, missing_fields, occurred_at = self._map_event(event, relations)
        if missing_fields:
            relation_failures.append(source_failure(
                source_name=EVENT_SOURCE_NAME,
                message="canonical event contains missing source-backed fields",
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                retryable=False,
                details={"missing_fields": missing_fields, "event_id": event_id},
            ))

        failures = relation_failures
        event_record_status = "partial" if missing_fields else "success"
        payload = {
            "event": event_payload,
            "theme_relations": relations,
            "missing_fields": missing_fields,
        }
        source_records = [
            self._event_source_record(event_id, event, occurred_at, observed_at, event_record_status),
            self._relation_source_record(event_id, relations, observed_at, relation_status, relation_failures[0] if relation_status == "failed" else None),
        ]
        return DomainObservationEnvelope(
            operation=request.operation,
            status="partial" if failures else "success",
            data_state="normal",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload=payload,
            source_records=source_records,
            failures=failures,
            diagnostics={
                "event_id": event_id,
                "excluded_not_proven_fields": list(EXCLUDED_NOT_PROVEN_FIELDS),
                "relation_state": "source_failure" if relation_status == "failed" else ("empty_not_mapped" if not relations else "mapped"),
            },
        )

    async def _read_event(self, event_id: int) -> Any:
        method = getattr(self._database_gateway, "get_news_event_for_match", None)
        if not callable(method):
            raise TypeError("database gateway has no callable get_news_event_for_match")
        result = method(event_id)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _read_relations(self, event_id: int) -> Any:
        method = getattr(self._database_gateway, "get_event_subject_mappings_by_event_ids", None)
        if not callable(method):
            raise TypeError("database gateway has no callable get_event_subject_mappings_by_event_ids")
        result = method([event_id])
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _map_event(self, event: Mapping[str, Any], relations: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str], str]:
        title = event.get("title") if event.get("title") is not None else event.get("summary")
        event_time = event.get("event_time")
        publish_date = event.get("publish_date")
        if event_time is not None:
            source_timestamp = self._timestamp(event_time)
        else:
            source_timestamp = self._timestamp(publish_date, event.get("publish_time"))
        relation_time = self._timestamp(relations[0].get("created_at")) if relations else ""
        occurred_at = self._first_non_empty(
            self._timestamp(event.get("event_time")),
            self._timestamp(event.get("created_at")),
            source_timestamp,
            relation_time,
        )
        payload = {
            "event_id": int(event["id"]),
            "event_type": event.get("event_type"),
            "summary": event.get("summary"),
            "direction": event.get("direction"),
            "confidence": event.get("confidence"),
            "occurred_at": occurred_at or None,
            "title": title,
            "source_category": event.get("source_category") or "news",
            "source_name": event.get("source_name"),
            "source_url": event.get("source_url"),
            "source_trace_id": event.get("source_trace_id"),
            "news_id": event.get("news_id"),
        }
        missing_fields = [name for name in (
            "event_type", "summary", "direction", "confidence", "occurred_at",
            "title", "source_name", "source_url", "source_trace_id",
        ) if payload.get(name) is None]
        return payload, missing_fields, occurred_at

    def _map_relation(self, raw: Any, event_id: int) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise TypeError("relation reader returned a non-object row")
        item = dict(raw)
        try:
            stable_relation_event_id = int(item["event_id"])
        except (KeyError, TypeError, ValueError):
            stable_relation_event_id = None
        if stable_relation_event_id != event_id:
            raise ValueError("relation reader returned an event_id mismatch")
        return {
            "subject_key": item.get("subject_key"),
            "subject_name": item.get("subject_name"),
            "relation_type": item.get("relation_type"),
            "confidence": item.get("confidence"),
            "match_reason": item.get("match_reason"),
            "evidence": item.get("evidence_json"),
            "source": item.get("source"),
            "source_trace_id": item.get("source_trace_id"),
            "created_at": self._timestamp(item.get("created_at")),
            "updated_at": self._timestamp(item.get("updated_at")),
            "run_id": item.get("run_id"),
        }

    def _event_source_record(
        self,
        event_id: int,
        event: Mapping[str, Any],
        as_of: str,
        observed_at: str,
        status: str,
    ) -> SourceRecord:
        failure = SourceFailure(
            code=AdapterErrorCode.SCHEMA_MISMATCH.value,
            message="canonical event contains missing source-backed fields",
            source_name=EVENT_SOURCE_NAME,
            retryable=False,
            details={"event_id": event_id},
        ) if status == "partial" else None
        return source_record(
            source_type="database",
            source_name=EVENT_SOURCE_NAME,
            source_ref=f"public.news_event:id={event_id}",
            as_of=as_of or self._timestamp(event.get("created_at")),
            observed_at=observed_at,
            freshness="source_timestamp_based",
            status=status,
            provenance={
                "database": "postgresql",
                "schema": "public",
                "table": "news_event",
                "row_id": event_id,
                "read_boundary": "DatabaseGateway.get_news_event_for_match",
                "source_trace_id": event.get("source_trace_id"),
            },
            failure=failure,
        )

    def _relation_source_record(
        self,
        event_id: int,
        relations: list[dict[str, Any]],
        observed_at: str,
        status: str,
        failure: SourceFailure | None,
    ) -> SourceRecord:
        run_ids = [str(item.get("run_id") or "") for item in relations]
        return source_record(
            source_type="database",
            source_name=RELATION_SOURCE_NAME,
            source_ref=f"public.event_subject_map:event_id={event_id}",
            as_of=self._timestamp(relations[0].get("updated_at")) if relations else "",
            observed_at=observed_at,
            freshness="source_timestamp_based",
            status=status,
            provenance={
                "database": "postgresql",
                "schema": "public",
                "table": "event_subject_map",
                "event_id": event_id,
                "run_ids": run_ids,
                "read_boundary": "DatabaseGateway.get_event_subject_mappings_by_event_ids",
            },
            failure=failure,
        )

    def _empty(
        self,
        request: AdapterRequest,
        observed_at: str,
        *,
        source_name: str,
        code: str,
        message: str,
        retryable: bool,
        diagnostics: dict[str, Any],
        status: str = "error",
    ) -> DomainObservationEnvelope:
        failure = source_failure(source_name=source_name, message=message, code=code, retryable=retryable, details=diagnostics)
        provenance = {"read_boundary": "DomainIntelligenceAdapter"}
        source_ref = source_name
        if source_name == EVENT_SOURCE_NAME:
            event_id = diagnostics.get("event_id")
            provenance = {
                "database": "postgresql",
                "schema": "public",
                "table": "news_event",
                "read_boundary": "DatabaseGateway.get_news_event_for_match",
                **({"row_id": event_id} if event_id is not None else {}),
            }
            source_ref = f"public.news_event:id={event_id}" if event_id is not None else "public.news_event"
        record = source_record(
            source_type="database",
            source_name=source_name,
            source_ref=source_ref,
            as_of="",
            observed_at=observed_at,
            freshness="unknown",
            status="failed",
            provenance=provenance,
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

    @staticmethod
    def _first_non_empty(*values: str) -> str:
        return next((value for value in values if value), "")

    @staticmethod
    def _timestamp(value: Any, time_component: Any = None) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            result = value
        else:
            text = str(value)
            if not text:
                return ""
            try:
                result = datetime.fromisoformat(text)
            except ValueError:
                return text
        if time_component is not None:
            try:
                result = datetime.combine(result.date(), datetime.strptime(str(time_component), "%H:%M:%S").time(), tzinfo=result.tzinfo)
            except ValueError:
                pass
        if result.tzinfo is None:
            result = result.replace(tzinfo=CST)
        return result.isoformat()

    def _now(self) -> str:
        if self._clock is not None and hasattr(self._clock, "now"):
            return self._clock.now().isoformat()
        return datetime.now(CST).isoformat()


__all__ = ["MarketEventReadOperation"]
