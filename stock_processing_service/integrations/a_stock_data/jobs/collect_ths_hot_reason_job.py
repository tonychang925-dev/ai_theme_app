from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.integrations.a_stock_data.clients.ths_client import (
    SOURCE_NAME,
    THS_HOT_REASON_ENDPOINT_KEY,
    RawHttpResult,
    ThsClient,
)
from stock_processing_service.integrations.a_stock_data.normalizers.ths_hot_reason_normalizer import (
    ThsHotReasonNormalizer,
)
from stock_processing_service.integrations.a_stock_data.resolvers.reason_theme_resolver import (
    CompositeReasonThemeResolver,
    ReasonThemeResolver,
    theme_match_to_evidence_rows,
)
from stock_processing_service.integrations.a_stock_data.schemas.ths_hot_reason_schema import (
    ThsHotReasonSchemaError,
    validate_ths_hot_reason_payload,
)


def _payload_hash(payload: Any, fallback_text: str = "") -> str:
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    else:
        raw = fallback_text or ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CollectThsHotReasonJob:
    def __init__(
        self,
        *,
        write_port,
        client: ThsClient | None = None,
        normalizer: ThsHotReasonNormalizer | None = None,
        resolver: ReasonThemeResolver | None = None,
    ) -> None:
        self._write_port = write_port
        self._client = client or ThsClient()
        self._normalizer = normalizer or ThsHotReasonNormalizer()
        self._resolver = resolver or CompositeReasonThemeResolver()

    async def execute(self, trade_date: date) -> BuildResult:
        td = trade_date.isoformat()
        try:
            raw = await self._client.fetch_hot_reason(trade_date)
            if raw.status_code >= 400:
                return BuildResult(
                    name="collect_ths_hot_reason",
                    trade_date=td,
                    affected_rows=0,
                    status="failed",
                    warnings=[f"ths_hot_reason HTTP {raw.status_code}"],
                )

            payload = raw.response_json
            if payload is None:
                return BuildResult(
                    name="collect_ths_hot_reason",
                    trade_date=td,
                    affected_rows=0,
                    status="failed",
                    warnings=["ths_hot_reason response is not JSON"],
                )

            warnings = validate_ths_hot_reason_payload(payload)
            raw_snapshot_id = None
            raw_snapshot_error: str | None = None
            try:
                raw_snapshot_id = await self._upsert_raw_snapshot(raw)
            except Exception as exc:
                raw_snapshot_error = str(exc)
            raw_snapshot_written = raw_snapshot_id is not None
            snapshot_rows = self._normalizer.normalize_snapshot_rows(
                payload,
                trade_date=trade_date,
                raw_snapshot_id=raw_snapshot_id,
                source_name=SOURCE_NAME,
            )
            snapshot_count = await self._write_port.upsert_ths_hot_reason_snapshot_rows(snapshot_rows)
            evidence_rows = await self._build_evidence_rows(snapshot_rows, raw_snapshot_id)
            evidence_count = await self._write_port.upsert_stock_theme_reason_evidence_rows(evidence_rows)
            diag = self._client.diagnostics
            return BuildResult(
                name="collect_ths_hot_reason",
                trade_date=td,
                affected_rows=snapshot_count + evidence_count,
                warnings=warnings,
                metrics={
                    "raw_snapshot_id": raw_snapshot_id,
                    "raw_snapshot_written": raw_snapshot_written,
                    "raw_snapshot_error": raw_snapshot_error,
                    "snapshot_rows": snapshot_count,
                    "evidence_rows": evidence_count,
                    "reason_covered_count": len({row["stock_code"] for row in evidence_rows}),
                    # M3 governance diagnostics
                    "source_consecutive_failures": diag.consecutive_failures,
                    "source_total_requests": diag.total_requests,
                    "source_total_failures": diag.total_failures,
                    "source_last_success_at": diag.last_success_at,
                    "source_last_failure_at": diag.last_failure_at,
                },
            )
        except ThsHotReasonSchemaError as exc:
            return BuildResult(
                name="collect_ths_hot_reason",
                trade_date=td,
                affected_rows=0,
                status="failed",
                warnings=[str(exc)],
            )

    async def _upsert_raw_snapshot(self, raw: RawHttpResult) -> int | None:
        fn = getattr(self._write_port, "upsert_source_raw_snapshot", None)
        if not callable(fn):
            return None
        return await fn(
            {
                "source_name": raw.source_name,
                "endpoint_key": raw.endpoint_key,
                "trade_date": raw.trade_date,
                "request_url": raw.request_url,
                "request_params": raw.request_params,
                "response_raw": raw.response_json,
                "response_text": raw.response_text,
                "response_hash": _payload_hash(raw.response_json, raw.response_text),
            }
        )

    async def _build_evidence_rows(
        self,
        snapshot_rows: list[dict[str, Any]],
        raw_snapshot_id: int | None,
    ) -> list[dict[str, Any]]:
        evidence_rows: list[dict[str, Any]] = []
        for row in snapshot_rows:
            match = await self._resolver.resolve(
                list(row.get("reason_tags") or []),
                str(row.get("stock_code") or ""),
                str(row.get("stock_name") or ""),
            )
            evidence_rows.extend(
                theme_match_to_evidence_rows(
                    trade_date=row.get("trade_date"),
                    stock_code=str(row.get("stock_code") or ""),
                    stock_name=str(row.get("stock_name") or ""),
                    reason_raw=str(row.get("reason_raw") or ""),
                    reason_tags=list(row.get("reason_tags") or []),
                    source_name=str(row.get("source_name") or SOURCE_NAME),
                    source_trace_id=str(row.get("source_trace_id") or ""),
                    raw_snapshot_id=raw_snapshot_id,
                    match=match,
                )
            )
        return evidence_rows
