"""AT-R3 market.snapshot operation with lossless degradation/provenance mapping.

Integration point: injected MarketContextExporter-like source. This is lower
than the legacy convenience wrapper and preserves exporter success/failure
states instead of guessing from collapsed fallbacks.
"""

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
from ..provenance import (
    classify_exception,
    missing_source_failure,
    normalize_raw_failure,
    normalize_source_record,
    source_failure,
    source_record,
)

CST = timezone(timedelta(hours=8))


class MarketSnapshotOperation:
    def __init__(self, *, exporter: object | None = None, clock: object | None = None) -> None:
        self._exporter = exporter
        self._clock = clock

    async def execute(self, request: AdapterRequest) -> DomainObservationEnvelope:
        observed_at = self._now()
        trade_date = str(request.arguments.get("trade_date") or observed_at[:10])

        if self._exporter is None:
            failure = source_failure(
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                message="market context exporter not configured",
                source_name="market_context_exporter",
                retryable=True,
            )
            return DomainObservationEnvelope(
                operation=request.operation,
                status="unavailable",
                data_state="empty",
                correlation_id=request.correlation_id,
                provider_request_id=request.idempotency_key,
                observed_at=observed_at,
                payload={},
                source_records=[],
                failures=[failure],
                diagnostics={"ready": False, "reason": "exporter_not_configured"},
            )

        try:
            raw = await self._export(trade_date)
        except Exception as exc:
            status, code, retryable = classify_exception(exc)
            return self._failed(request, observed_at, status, code, "market_context_exporter", exc, retryable=retryable)

        if not isinstance(raw, Mapping):
            failure = source_failure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="market context exporter returned non-object payload",
                source_name="market_context_exporter",
                retryable=False,
            )
            return DomainObservationEnvelope(
                operation=request.operation,
                status="error",
                data_state="empty",
                correlation_id=request.correlation_id,
                provider_request_id=request.idempotency_key,
                observed_at=observed_at,
                payload={},
                source_records=[],
                failures=[failure],
                diagnostics={"raw_type": type(raw).__name__},
            )

        return self._map_raw(request, observed_at, trade_date, dict(raw))

    async def _export(self, trade_date: str) -> Any:
        export = getattr(self._exporter, "export", None)
        if not callable(export):
            raise TypeError("configured exporter has no callable export")
        result = export(trade_date)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _map_raw(self, request: AdapterRequest, observed_at: str, trade_date: str, raw: dict[str, Any]) -> DomainObservationEnvelope:
        source_status = str(raw.get("status") or "")
        raw_as_of = str(raw.get("trade_date") or raw.get("as_of") or trade_date)
        freshness = _freshness(raw, requested_trade_date=trade_date, raw_as_of=raw_as_of)
        missing_sources = [str(item) for item in raw.get("missing_sources", []) if item]
        raw_failures = [normalize_raw_failure(item) for item in raw.get("failures", []) if isinstance(item, Mapping)]
        failures = [missing_source_failure(name) for name in missing_sources]
        failures.extend(raw_failures)
        failures = _dedupe_failures(failures)

        quality = raw.get("quality", {}) if isinstance(raw.get("quality"), Mapping) else {}
        payload = {
            "market_state": raw.get("market_state", {}),
            "themes": raw.get("themes", []),
            "quality": quality,
            "raw_schema_version": raw.get("schema_version"),
            "raw_status": source_status,
        }
        has_useful_payload = bool(payload["themes"] or payload["market_state"])
        source_records = self._source_records(raw_as_of, observed_at, raw, freshness, failures)

        if source_status in {"unavailable", "error"}:
            code = AdapterErrorCode.UPSTREAM_UNAVAILABLE.value if source_status == "unavailable" else AdapterErrorCode.INTERNAL_ERROR.value
            top_failure = source_failure(
                code=code,
                message=str(raw.get("reason") or "market context source failed"),
                source_name="market_context_exporter",
                retryable=source_status == "unavailable",
                details={"diagnostics": raw.get("diagnostics", {}) if isinstance(raw.get("diagnostics"), Mapping) else {}},
            )
            return DomainObservationEnvelope(
                operation=request.operation,
                status="unavailable" if source_status == "unavailable" else "error",
                data_state="empty",
                correlation_id=request.correlation_id,
                provider_request_id=request.idempotency_key,
                observed_at=observed_at,
                payload={},
                source_records=source_records,
                failures=_dedupe_failures([top_failure, *failures]),
                diagnostics={"raw_status": source_status, "reason": raw.get("reason", "")},
            )

        if failures:
            if not has_useful_payload:
                return DomainObservationEnvelope(
                    operation=request.operation,
                    status="unavailable",
                    data_state="empty",
                    correlation_id=request.correlation_id,
                    provider_request_id=request.idempotency_key,
                    observed_at=observed_at,
                    payload={},
                    source_records=source_records,
                    failures=failures,
                    diagnostics={"missing_sources": missing_sources, "raw_status": source_status},
                )
            return DomainObservationEnvelope(
                operation=request.operation,
                status="partial",
                data_state="stale" if freshness == "stale" else "normal",
                correlation_id=request.correlation_id,
                provider_request_id=request.idempotency_key,
                observed_at=observed_at,
                payload=payload,
                source_records=source_records,
                failures=failures,
                diagnostics={"missing_sources": missing_sources, "raw_status": source_status},
            )

        return DomainObservationEnvelope(
            operation=request.operation,
            status="success",
            data_state="stale" if freshness == "stale" else ("normal" if has_useful_payload else "empty"),
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload=payload,
            source_records=source_records,
            failures=[],
            diagnostics={"raw_status": source_status},
        )

    def _source_records(self, raw_as_of: str, observed_at: str, raw: Mapping[str, Any], freshness: str, failures: list[SourceFailure]) -> list[SourceRecord]:
        records = [
            _force_stale_if_needed(
                normalize_source_record(item, default_as_of=raw_as_of, default_observed_at=observed_at, default_freshness=freshness),
                freshness,
            )
            for item in raw.get("source_records", [])
            if isinstance(item, Mapping)
        ]
        if not records:
            records.append(source_record(
                source_type="domain_exporter",
                source_name="market_context_exporter",
                source_ref=f"trade_date={raw_as_of}",
                as_of=raw_as_of,
                observed_at=observed_at,
                freshness=freshness,
                status="success" if str(raw.get("status") or "") not in {"unavailable", "error"} else "failed",
                provenance={"schema_version": raw.get("schema_version", "market-context.v1")},
            ))
        existing_failed = {record.source_name for record in records if record.status == "failed"}
        for failure in failures:
            if failure.source_name in existing_failed:
                continue
            records.append(source_record(
                source_type="dependency",
                source_name=failure.source_name,
                source_ref=f"trade_date={raw_as_of}",
                as_of=raw_as_of,
                observed_at=observed_at,
                freshness=freshness,
                status="failed",
                provenance={},
                failure=failure,
            ))
        return records

    def _failed(self, request: AdapterRequest, observed_at: str, status: str, code: str, source_name: str, exc: BaseException, *, retryable: bool) -> DomainObservationEnvelope:
        failure = source_failure(
            code=code,
            message=f"{type(exc).__name__}: {exc}",
            source_name=source_name,
            retryable=retryable,
        )
        return DomainObservationEnvelope(
            operation=request.operation,
            status=status,
            data_state="empty",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload={},
            source_records=[],
            failures=[failure],
            diagnostics={"error_type": type(exc).__name__},
        )

    def _now(self) -> str:
        if self._clock is not None and hasattr(self._clock, "now"):
            return self._clock.now().isoformat()
        return datetime.now(CST).isoformat()


def _freshness(raw: Mapping[str, Any], *, requested_trade_date: str, raw_as_of: str) -> str:
    marker = str(raw.get("data_state") or raw.get("freshness") or "").lower()
    if marker == "stale" or raw_as_of < requested_trade_date:
        return "stale"
    return "fresh"


def _dedupe_failures(failures: list[SourceFailure]) -> list[SourceFailure]:
    seen: set[tuple[str, str]] = set()
    result: list[SourceFailure] = []
    for failure in failures:
        key = (failure.source_name, failure.code)
        if key in seen:
            continue
        seen.add(key)
        result.append(failure)
    return result


__all__ = ["MarketSnapshotOperation"]


def _force_stale_if_needed(record: SourceRecord, envelope_freshness: str) -> SourceRecord:
    if envelope_freshness != "stale" or record.freshness == "stale":
        return record
    return SourceRecord(
        source_type=record.source_type,
        source_name=record.source_name,
        source_ref=record.source_ref,
        as_of=record.as_of,
        observed_at=record.observed_at,
        freshness="stale",
        status=record.status,
        provenance=record.provenance,
        failure=record.failure,
    )
