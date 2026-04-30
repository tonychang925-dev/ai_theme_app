"""Gateway-only read client for web_app_service.

Modes:
- stub (default): zero dependency, safe for isolated bootstrap.
- http: call stock_processing_service read APIs (when available).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

from web_app_service.core.contracts import (
    PostMarketSnapshotResponse,
    StrongWatchResponse,
    W2SCandidatesResponse,
)


class StockProcessingReadClient:
    def __init__(self) -> None:
        self._mode = str(os.getenv("WEB_APP_READ_MODE", "stub")).strip().lower()
        self._base_url = str(os.getenv("STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090")).rstrip("/")
        self._timeout = float(os.getenv("WEB_APP_HTTP_TIMEOUT_SEC", "8"))

    async def get_post_market_snapshot(self, trade_date: str) -> PostMarketSnapshotResponse:
        if self._mode != "http":
            return PostMarketSnapshotResponse(
                trade_date=trade_date,
                snapshot_version="stub",
                payload={"note": "pending stock_processing_service read api integration"},
            )
        payload = await self._get_json("/api/v1/post_market_snapshot", {"trade_date": trade_date})
        return PostMarketSnapshotResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            snapshot_version=str(payload.get("snapshot_version", "unknown")),
            payload=dict(payload.get("payload") or {}),
        )

    async def get_strong_watch(self, trade_date: str) -> StrongWatchResponse:
        if self._mode != "http":
            return StrongWatchResponse(trade_date=trade_date, stocks=[])
        payload = await self._get_json("/api/v1/strong_watch", {"trade_date": trade_date})
        return StrongWatchResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            stocks=list(payload.get("stocks") or []),
        )

    async def get_w2s_candidates(self, trade_date: str) -> W2SCandidatesResponse:
        if self._mode != "http":
            return W2SCandidatesResponse(trade_date=trade_date, candidates=[])
        payload = await self._get_json("/api/v1/w2s_candidates", {"trade_date": trade_date})
        return W2SCandidatesResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            candidates=list(payload.get("candidates") or []),
        )

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            q = urlencode(params)
            return {"error": str(exc), "upstream": f"{url}?{q}"}
