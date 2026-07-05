"""M4b: Collect CNInfo announcements and write to evidence layer.

Fetches recent event-driven announcements, normalizes them,
and writes to stock_theme_reason_evidence as event evidence.
"""

from __future__ import annotations

import hashlib
import json as _json
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.integrations.a_stock_data.clients.cninfo_client import (
    ANNOUNCEMENT_ENDPOINT,
    SOURCE_NAME,
    CninfoClient,
    RawHttpResult,
)
from stock_processing_service.integrations.a_stock_data.normalizers.cninfo_announcement_normalizer import (
    CninfoAnnouncementNormalizer,
)


def _payload_hash(payload: Any, fallback_text: str = "") -> str:
    if payload is not None:
        raw = _json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    else:
        raw = fallback_text or ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CollectCninfoAnnouncementsJob:
    """Fetch CNInfo announcements, write as event evidence."""

    def __init__(
        self,
        *,
        write_port,
        client: CninfoClient | None = None,
        normalizer: CninfoAnnouncementNormalizer | None = None,
        max_pages: int = 3,
    ) -> None:
        self._write_port = write_port
        self._client = client or CninfoClient()
        self._normalizer = normalizer or CninfoAnnouncementNormalizer()
        self._max_pages = max_pages

    async def execute(self, trade_date: date) -> BuildResult:
        td = trade_date.isoformat()
        warnings: list[str] = []
        all_evidence: list[dict[str, Any]] = []
        raw_snapshot_ids: list[int] = []
        raw_snapshot_errors: list[str] = []

        for page in range(1, self._max_pages + 1):
            try:
                raw = await self._client.fetch_announcements(
                    page_num=page, page_size=30,
                    start_date=trade_date, end_date=trade_date,
                )
                if raw.response_json is None:
                    raw_snapshot_errors.append(
                        f"page {page}: {raw.error_message or 'empty'}"
                    )
                    continue

                rsi = await self._upsert_raw_snapshot(raw)
                if rsi is not None:
                    raw_snapshot_ids.append(rsi)

                evidences = self._normalizer.normalize(raw.response_json, trade_date)
                for ev in evidences:
                    all_evidence.append({
                        "trade_date": ev.trade_date,
                        "stock_code": ev.stock_code,
                        "stock_name": ev.stock_name,
                        "theme_name": ev.announcement_type,
                        "source_name": ev.source_name,
                        "endpoint_key": ev.endpoint_key,
                        "evidence_text": ev.title,
                        "reason_tags": [ev.announcement_type],
                        "matched_reason_tags": [ev.announcement_type],
                        "primary_theme": False,
                        "confidence": 0.3,
                        "resolver_name": "CninfoAnnouncement",
                        "source_trace_id": ev.source_trace_id,
                        "raw_snapshot_id": rsi,
                    })
            except Exception as exc:
                raw_snapshot_errors.append(f"page {page}: {exc}")

        evidence_count = 0
        for row in all_evidence:
            try:
                await self._write_port.upsert_stock_theme_reason_evidence_rows([row])
                evidence_count += 1
            except Exception:
                pass

        diag = self._client.diagnostics
        return BuildResult(
            name="collect_cninfo_announcements",
            trade_date=td,
            affected_rows=evidence_count,
            warnings=warnings,
            metrics={
                "pages_fetched": self._max_pages,
                "raw_announcements": len(all_evidence),
                "evidence_rows": evidence_count,
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
