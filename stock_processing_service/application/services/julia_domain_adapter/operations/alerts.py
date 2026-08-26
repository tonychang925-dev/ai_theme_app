"""AT-R2 market.alerts operation.

Integration point: approved workbench snapshot + ApprovedSnapshotValidator +
AnalystIntelligenceExporter. This avoids the legacy convenience wrapper because that wrapper collapses
missing/invalid/exception states into an empty list.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from ..contracts import (
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    SourceFailure,
    SourceRecord,
)

CST = timezone(timedelta(hours=8))
_ATTENTION_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_DEFAULT_MIN_ATTENTION = "HIGH"


class MarketAlertsOperation:
    def __init__(self, *, workbench_base_dir: str | None = None, clock: object | None = None) -> None:
        self._workbench_base_dir = Path(workbench_base_dir) if workbench_base_dir else _default_workbench_base_dir()
        self._clock = clock

    async def execute(self, request: AdapterRequest) -> DomainObservationEnvelope:
        observed_at = self._now()
        trade_date = str(request.arguments.get("trade_date") or observed_at[:10])
        min_attention = str(request.arguments.get("min_attention_level") or _DEFAULT_MIN_ATTENTION).upper()
        if min_attention not in _ATTENTION_RANK:
            failure = SourceFailure(
                code=AdapterErrorCode.INVALID_ARGUMENT.value,
                message=f"invalid min_attention_level: {min_attention}",
                source_name="adapter.arguments",
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
                diagnostics={"allowed_min_attention_level": sorted(_ATTENTION_RANK)},
            )

        wb_dir = self._workbench_base_dir / trade_date
        session_path = wb_dir / "session.json"
        snapshot_path = wb_dir / "snapshot.json"
        source_ref = str(snapshot_path)

        if not session_path.exists() or not snapshot_path.exists():
            missing = "session.json" if not session_path.exists() else "snapshot.json"
            return self._unavailable(
                request,
                observed_at,
                trade_date,
                source_ref,
                reason=f"approved workbench source missing: {missing}",
                code=AdapterErrorCode.UPSTREAM_UNAVAILABLE.value,
            )

        try:
            session = json.loads(session_path.read_text(encoding="utf-8"))
            snap_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return self._error(request, observed_at, trade_date, source_ref, exc, code=AdapterErrorCode.SCHEMA_MISMATCH.value)
        except Exception as exc:
            return self._error(request, observed_at, trade_date, source_ref, exc, code=AdapterErrorCode.INTERNAL_ERROR.value)

        try:
            from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
            from stock_processing_service.application.services.analyst_workbench.snapshot_validator import ApprovedSnapshotValidator
            from stock_processing_service.application.services.analyst_workbench.intelligence_exporter import AnalystIntelligenceExporter

            snapshot = ReviewSnapshot.from_dict(snap_data)
            validation = ApprovedSnapshotValidator().validate(str(session.get("status", "")), snapshot)
        except Exception as exc:
            return self._error(request, observed_at, trade_date, source_ref, exc, code=AdapterErrorCode.INTERNAL_ERROR.value)

        if not validation.valid:
            errors = [str(getattr(item, "value", item)) for item in validation.errors]
            failure = SourceFailure(
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
                message="approved workbench snapshot validation failed",
                source_name="analyst_workbench_snapshot",
                retryable=False,
                details={"validation_errors": errors},
            )
            source = self._source_record(trade_date, observed_at, source_ref, status="failed", failure=failure)
            return DomainObservationEnvelope(
                operation=request.operation,
                status="unavailable",
                data_state="empty",
                correlation_id=request.correlation_id,
                provider_request_id=request.idempotency_key,
                observed_at=observed_at,
                payload={},
                source_records=[source],
                failures=[failure],
                diagnostics={"validation_errors": errors},
            )

        try:
            envelope = AnalystIntelligenceExporter().export(snapshot).to_dict()
        except Exception as exc:
            return self._error(request, observed_at, trade_date, source_ref, exc, code=AdapterErrorCode.INTERNAL_ERROR.value)

        claims = envelope.get("claims", [])
        if not isinstance(claims, list):
            return self._unavailable(
                request,
                observed_at,
                trade_date,
                source_ref,
                reason="exporter claims field is not a list",
                code=AdapterErrorCode.SCHEMA_MISMATCH.value,
            )

        max_rank = _ATTENTION_RANK[min_attention]
        alerts = [
            claim for claim in claims
            if isinstance(claim, dict) and _ATTENTION_RANK.get(str(claim.get("attention_level", "LOW")).upper(), 99) <= max_rank
        ]
        source = self._source_record(
            trade_date,
            observed_at,
            source_ref,
            status="success",
            provenance={
                "validator": "ApprovedSnapshotValidator",
                "exporter": "AnalystIntelligenceExporter",
                "snapshot_version": envelope.get("approval", {}).get("snapshot_version") if isinstance(envelope.get("approval"), dict) else None,
                "snapshot_hash": envelope.get("approval", {}).get("snapshot_hash") if isinstance(envelope.get("approval"), dict) else None,
            },
        )

        return DomainObservationEnvelope(
            operation=request.operation,
            status="success",
            data_state="normal" if alerts else "empty",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload={
                "alerts": alerts,
                "min_attention_level": min_attention,
                "claim_count": len(claims),
                "raw_schema_version": envelope.get("schema_version"),
            },
            source_records=[source],
            failures=[],
            diagnostics={"empty_reason": "no claims at or above requested attention level"} if not alerts else {},
        )

    def _unavailable(self, request: AdapterRequest, observed_at: str, trade_date: str, source_ref: str, *, reason: str, code: str) -> DomainObservationEnvelope:
        failure = SourceFailure(code=code, message=reason, source_name="analyst_workbench_snapshot", retryable=True)
        return DomainObservationEnvelope(
            operation=request.operation,
            status="unavailable",
            data_state="empty",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload={},
            source_records=[self._source_record(trade_date, observed_at, source_ref, status="failed", failure=failure)],
            failures=[failure],
            diagnostics={"reason": reason},
        )

    def _error(self, request: AdapterRequest, observed_at: str, trade_date: str, source_ref: str, exc: BaseException, *, code: str) -> DomainObservationEnvelope:
        failure = SourceFailure(code=code, message=f"{type(exc).__name__}: {exc}", source_name="analyst_workbench_snapshot")
        return DomainObservationEnvelope(
            operation=request.operation,
            status="error",
            data_state="empty",
            correlation_id=request.correlation_id,
            provider_request_id=request.idempotency_key,
            observed_at=observed_at,
            payload={},
            source_records=[self._source_record(trade_date, observed_at, source_ref, status="failed", failure=failure)],
            failures=[failure],
            diagnostics={"error_type": type(exc).__name__},
        )

    def _source_record(self, trade_date: str, observed_at: str, source_ref: str, *, status: str, provenance: dict[str, Any] | None = None, failure: SourceFailure | None = None) -> SourceRecord:
        return SourceRecord(
            source_type="file_store",
            source_name="analyst_workbench_snapshot",
            source_ref=source_ref,
            as_of=trade_date,
            observed_at=observed_at,
            freshness="fresh",
            status=status,
            provenance=provenance or {},
            failure=failure,
        )

    def _now(self) -> str:
        if self._clock is not None and hasattr(self._clock, "now"):
            return self._clock.now().isoformat()
        return datetime.now(CST).isoformat()


def _default_workbench_base_dir() -> Path:
    return Path(__file__).resolve().parents[5] / "tmp" / "analyst_workbench"


__all__ = ["MarketAlertsOperation"]
