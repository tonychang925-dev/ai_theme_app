"""Gateway-only read client for web_app_service.

Mode:
- http: call stock_processing_service read APIs.
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
        self._base_url = str(os.getenv("STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090")).rstrip("/")
        self._timeout = float(os.getenv("WEB_APP_HTTP_TIMEOUT_SEC", "120"))

    async def get_post_market_snapshot(self, trade_date: str) -> PostMarketSnapshotResponse:
        payload = await self._get_json("/api/v1/post_market_snapshot", {"trade_date": trade_date})
        return PostMarketSnapshotResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            snapshot_version=str(payload.get("snapshot_version", "unknown")),
            payload=dict(payload.get("payload") or {}),
        )

    async def get_strong_watch(
        self,
        trade_date: str,
        *,
        window_days: int | None = None,
        include_removed: bool | None = None,
        latest_per_stock: bool | None = None,
        stock_id: str | None = None,
        limit: int | None = None,
    ) -> StrongWatchResponse:
        payload = await self._get_json(
            "/api/v1/strong_watch",
            {
                "trade_date": trade_date,
                "window_days": window_days,
                "include_removed": include_removed,
                "latest_per_stock": latest_per_stock,
                "stock_id": stock_id,
                "limit": limit,
            },
        )
        return StrongWatchResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            stocks=list(payload.get("stocks") or []),
        )

    async def get_w2s_candidates(self, trade_date: str) -> W2SCandidatesResponse:
        payload = await self._get_json("/api/v1/w2s_candidates", {"trade_date": trade_date})
        return W2SCandidatesResponse(
            trade_date=str(payload.get("trade_date", trade_date)),
            candidates=list(payload.get("candidates") or []),
        )

    async def get_intel_feed(
        self,
        *,
        date: str | None = None,
        session: str = "all",
        item_type: str = "all",
        subject_key: str | None = None,
        stock_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        # 未指定日期时不调用上游（上游要求 feed_date 必填）
        if not date:
            return {
                "items": [],
                "count": 0,
                "date": None,
                "session": session,
                "type": item_type,
                "diagnostics": {"partial": True, "source": "no_date_provided", "hint": "请指定 date 参数"},
            }
        payload = await self._get_json(
            "/api/v1/intel_feed",
            {
                "feed_date": date,
                "session": session,
                "item_type": item_type,
                "subject_key": subject_key,
                "stock_id": stock_id,
                "limit": limit,
            },
        )
        if "items" in payload and "count" in payload:
            return payload
        return {
            "items": [],
            "count": 0,
            "date": date,
            "session": session,
            "type": item_type,
            "diagnostics": {
                "partial": True,
                "source": "stock_processing_read_api_unavailable",
                "upstream_error": payload.get("error"),
                "upstream": payload.get("upstream"),
            },
        }

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """公开的 JSON GET 请求，供路由层直接调用 SPS API。"""
        return await self._get_json(path, params or {})

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=clean_params)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            q = urlencode(clean_params)
            return {"error": str(exc), "upstream": f"{url}?{q}"}
