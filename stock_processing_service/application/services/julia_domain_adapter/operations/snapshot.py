"""AT-R2 market.snapshot operation.

Integration point: injected MarketContextExporter-like source. This is lower
than the legacy MCP convenience wrapper and preserves exporter success/failure
states instead of guessing from collapsed fallbacks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping

from ..contracts import (
    ADAPTER_SCHEMA_VERSION,
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
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
            failure = SourceFailure(
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
        except TimeoutError as exc:
            return self._failed(request, observed_at, "unavailable", AdapterErrorCode.UPSTREAM_TIMEOUT.value, "market_context_exporter", exc, retryable=True)
        except Exception as exc:
            return self._failed(request, observed_at, "error", AdapterErrorCode.INTERNAL_ERROR.value, "market_context_exporter", exc, retryable=False)

        if not isinstance(raw, Mapping):
            failure = SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="market context exporter returned non-object payload",
                source_name="market_context_exporter",
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
        missing_sources = [str(item) for item in raw.get("missing_sources", []) if item]
        quality = raw.get("quality", {}) if isinstance(raw.get("quality"), Mapping) else {}
        freshness = "stale" if str(raw.get("data_state") or raw.get("freshness") or "").lower() == "stale" else "fresh"

        payload = {
            "market_state": raw.get("market_state", {}),
            "themes": raw.get("themes", []),
            "quality": quality,
            "raw_schema_version": raw.get("schema_version"),
            "raw_status": source_status,
        }

        source_records = self._source_records(trade_date, observed_at, raw, freshness, missing_sources)
        failures = [
            SourceFailure(
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                message=f"source unavailable: {name}",
                source_name=name,
                retryable=True,
            )
            for name in missing_sources
        ]

        if source_status in {"unavailable", "error"}:
            failure = SourceFailure(
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value if source_status == "unavailable" else AdapterErrorCode.INTERNAL_ERROR.value,
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
                failures=[failure],
                diagnostics={"raw_status": source_status, "reason": raw.get("reason", "")},
            )

        has_useful_payload = bool(payload["themes"] or payload["market_state"])
        if failures:
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

    def _source_records(self, trade_date: str, observed_at: str, raw: Mapping[str, Any], freshness: str, missing_sources: list[str]) -> list[SourceRecord]:
        source_records = [
            SourceRecord(
                source_type="domain_exporter",
                source_name="market_context_exporter",
                source_ref=f"trade_date={trade_date}",
                as_of=str(raw.get("trade_date") or trade_date),
                observed_at=observed_at,
                freshness=freshness,
                status="success" if str(raw.get("status") or "") not in {"unavailable", "error"} else "failed",
                provenance={"schema_version": raw.get("schema_version", "market-context.v1")},
            )
        ]
        for name in missing_sources:
            source_records.append(SourceRecord(
                source_type="dependency",
                source_name=name,
                source_ref=f"trade_date={trade_date}",
                as_of=trade_date,
                observed_at=observed_at,
                freshness=freshness,
                status="failed",
                provenance={},
                failure=SourceFailure(
                    code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
                    message=f"source unavailable: {name}",
                    source_name=name,
                    retryable=True,
                ),
            ))
        return source_records

    def _failed(self, request: AdapterRequest, observed_at: str, status: str, code: str, source_name: str, exc: BaseException, *, retryable: bool) -> DomainObservationEnvelope:
        failure = SourceFailure(
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
