"""Collect Eastmoney stock fund-flow daykline evidence."""

from __future__ import annotations

import hashlib
import json as _json
from datetime import date
from typing import Any

from stock_processing_service.application.services.capital_evidence.stock_fund_flow import (
    EastmoneyStockFundFlowNormalizer,
)
from stock_processing_service.contracts.dto.output_dto import BuildResult
from stock_processing_service.integrations.a_stock_data.clients.eastmoney_fund_flow_client import (
    EastmoneyFundFlowClient,
    RawHttpResult,
)


def _payload_hash(payload: Any, fallback_text: str = "") -> str:
    if payload is not None:
        raw = _json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    else:
        raw = fallback_text or ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CollectEastmoneyFundFlowJob:
    """Fetch given stocks' daily fund-flow evidence and write snapshots."""

    def __init__(
        self,
        *,
        write_port,
        stock_codes: list[str],
        client: EastmoneyFundFlowClient | None = None,
        normalizer: EastmoneyStockFundFlowNormalizer | None = None,
        limit: int = 120,
    ) -> None:
        self._write_port = write_port
        self._stock_codes = [code for code in stock_codes if str(code or "").strip()]
        self._client = client or EastmoneyFundFlowClient()
        self._normalizer = normalizer or EastmoneyStockFundFlowNormalizer()
        self._limit = limit

    async def execute(self, trade_date: date) -> BuildResult:
        warnings: list[str] = []
        total_rows = 0
        raw_snapshot_count = 0

        if not self._stock_codes:
            return BuildResult(
                name="collect_eastmoney_fund_flow",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped",
                warnings=["stock_codes empty"],
            )

        for stock_code in self._stock_codes:
            raw = await self._client.fetch_stock_daykline(stock_code, limit=self._limit)
            if raw.response_json is None:
                warnings.append(f"{stock_code}: {raw.error_message or 'empty response'}")
                continue
            raw_snapshot_id = await self._upsert_raw_snapshot(raw)
            if raw_snapshot_id is not None:
                raw_snapshot_count += 1
            evidence_rows = self._normalizer.normalize_daykline_payload(
                raw.response_json,
                fallback_stock_code=stock_code,
            )
            rows = [item.to_row() for item in evidence_rows]
            for row in rows:
                row["diagnostics"] = {
                    **dict(row.get("diagnostics") or {}),
                    "raw_snapshot_id": raw_snapshot_id,
                }
            fn = getattr(self._write_port, "upsert_stock_fund_flow_snapshot_rows", None)
            if not callable(fn):
                raise RuntimeError("write_port missing upsert_stock_fund_flow_snapshot_rows")
            total_rows += int(await fn(rows) or 0)

        diag = self._client.diagnostics
        return BuildResult(
            name="collect_eastmoney_fund_flow",
            trade_date=trade_date.isoformat(),
            affected_rows=total_rows,
            warnings=warnings,
            metrics={
                "stock_count": len(self._stock_codes),
                "raw_snapshot_count": raw_snapshot_count,
                "source_consecutive_failures": diag.consecutive_failures,
                "source_total_requests": diag.total_requests,
                "source_total_failures": diag.total_failures,
                "source_last_success_at": diag.last_success_at,
            },
        )

    async def _upsert_raw_snapshot(self, raw: RawHttpResult) -> int | None:
        fn = getattr(self._write_port, "upsert_source_raw_snapshot", None)
        if not callable(fn):
            return None
        return await fn(
            {
                "source_name": raw.source_name,
                "endpoint_key": raw.endpoint_key,
                "request_url": raw.request_url,
                "request_params": raw.request_params,
                "response_raw": raw.response_json,
                "response_text": raw.response_text,
                "response_hash": _payload_hash(raw.response_json, raw.response_text),
            }
        )
