"""M4a: Collect Eastmoney concept/industry/region block stock mappings.

Design: fetch top-N concept blocks, then fetch member stocks for each.
Results are stored as stock→concept evidence in stock_theme_reason_evidence.

Governed by RateLimitedHttpClient — no hand-rolled sleep/retry.
"""

from __future__ import annotations

import hashlib
import json as _json
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.integrations.a_stock_data.clients.eastmoney_client import (
    CONCEPT_BLOCK_ENDPOINT,
    SOURCE_NAME,
    EastmoneyClient,
    RawHttpResult,
)
from stock_processing_service.integrations.a_stock_data.normalizers.eastmoney_concept_block_normalizer import (
    EastmoneyConceptBlockNormalizer,
)


def _payload_hash(payload: Any, fallback_text: str = "") -> str:
    if payload is not None:
        raw = _json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    else:
        raw = fallback_text or ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CollectEastmoneyConceptBlocksJob:
    """Fetch Eastmoney concept blocks + member stocks, write evidence."""

    def __init__(
        self,
        *,
        write_port,
        client: EastmoneyClient | None = None,
        normalizer: EastmoneyConceptBlockNormalizer | None = None,
        max_blocks: int = 50,
    ) -> None:
        self._write_port = write_port
        self._client = client or EastmoneyClient()
        self._normalizer = normalizer or EastmoneyConceptBlockNormalizer()
        self._max_blocks = max_blocks

    async def execute(self, trade_date: date) -> BuildResult:
        td = trade_date.isoformat()
        warnings: list[str] = []
        total_evidence = 0
        raw_snapshot_ids: list[int] = []
        raw_snapshot_errors: list[str] = []

        # Step 1: Fetch concept block list
        raw_list = await self._client.fetch_block_list("concept", page_size=200)
        if raw_list.response_json is None:
            return BuildResult(
                name="collect_eastmoney_concept_blocks",
                trade_date=td,
                affected_rows=0,
                status="failed",
                warnings=[f"block list failed: {raw_list.error_message or 'empty response'}"],
            )

        # Save raw snapshot for block list
        rsi = await self._upsert_raw_snapshot(raw_list)
        if rsi is not None:
            raw_snapshot_ids.append(rsi)
        else:
            raw_snapshot_errors.append("block_list_raw_snapshot_failed")

        blocks = self._normalizer.normalize_block_list(raw_list.response_json, "concept")
        blocks = blocks[:self._max_blocks]
        warnings.append(f"fetched {len(blocks)} concept blocks")

        # Step 2: For each block, fetch member stocks
        for block in blocks:
            try:
                raw_stocks = await self._client.fetch_block_stocks(block.block_code)
                if raw_stocks.response_json is None:
                    raw_snapshot_errors.append(
                        f"block {block.block_code} stocks: {raw_stocks.error_message or 'empty'}"
                    )
                    continue

                rsi = await self._upsert_raw_snapshot(raw_stocks)
                if rsi is not None:
                    raw_snapshot_ids.append(rsi)

                mappings = self._normalizer.normalize_block_stocks(
                    raw_stocks.response_json,
                    block.block_code,
                    block.block_name,
                    block.block_type,
                    trade_date,
                )
                for m in mappings:
                    await self._write_port.upsert_stock_theme_reason_evidence_rows([{
                        "trade_date": m.trade_date,
                        "stock_code": m.stock_code,
                        "stock_name": m.stock_name,
                        "theme_name": m.block_name,
                        "source_name": m.source_name,
                        "endpoint_key": m.endpoint_key,
                        "evidence_text": f"东财{m.block_type}板块: {m.block_name}",
                        "reason_tags": [m.block_name],
                        "matched_reason_tags": [m.block_name],
                        "primary_theme": False,
                        "confidence": 0.5,
                        "resolver_name": "EastmoneyConceptBlock",
                        "source_trace_id": m.source_trace_id,
                        "raw_snapshot_id": rsi,
                    }])
                    total_evidence += 1
            except Exception as exc:
                raw_snapshot_errors.append(f"block {block.block_code}: {exc}")

        diag = self._client.diagnostics
        return BuildResult(
            name="collect_eastmoney_concept_blocks",
            trade_date=td,
            affected_rows=total_evidence,
            warnings=warnings,
            metrics={
                "blocks_fetched": len(blocks),
                "evidence_rows": total_evidence,
                "raw_snapshot_count": len(raw_snapshot_ids),
                "raw_snapshot_errors": raw_snapshot_errors[:10],
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
        return await fn({
            "source_name": raw.source_name,
            "endpoint_key": raw.endpoint_key,
            "request_url": raw.request_url,
            "request_params": raw.request_params,
            "response_raw": raw.response_json,
            "response_text": raw.response_text,
            "response_hash": _payload_hash(raw.response_json, raw.response_text),
        })
