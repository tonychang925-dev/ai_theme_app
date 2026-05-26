"""久赢恒丰行情 API 客户端 — httpx + JWT."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("sps.jyhf_market.api_client")


class JyhfMarketApiClient:
    """统一封装 3 个 P1-A 行情接口。"""

    def __init__(self, token_provider, base_url: str, timeout: float = 10.0, max_retries: int = 1):
        self._token = token_provider
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    async def get_index_realtime(self) -> dict[str, Any]:
        return await self._get("/api/app/realtime/index")

    async def get_stock_realtime(self, stock_id: str) -> dict[str, Any]:
        return await self._get(f"/api/app/stock/realtime/{stock_id}")

    async def get_subject_stocks_realtime(
        self, subject_id: str, sort: str = "pctChg", sort_type: str = "desc", start: int = 0, end: int = 50
    ) -> dict[str, Any]:
        from datetime import date
        params = {
            "sort": sort, "sortType": sort_type,
            "date": str(date.today()), "subjectId": subject_id,
            "start": start, "end": end,
        }
        return await self._get("/api/app/stock/realtime-by-subject/v2", params)

    async def get_stock_daily(self, stock_id: str, days: int = 120) -> dict[str, Any]:
        """P1 §4.2 — 个股日线 OHLCV 多日历史。

        对应已验证接口: GET /api/app/data/one-stock-daily
        返回字段: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        """
        return await self._get("/api/app/data/one-stock-daily", params={
            "stockId": stock_id,
            "platform": "pc",
            "searchStockType": "one",
            "days": str(days),
        })

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        headers = self._build_headers()

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                    r = await client.get(url, headers=headers, params=params or {})
                if r.status_code in (401, 403):
                    logger.warning("Token rejected, attempting refresh")
                    if self._token.force_refresh():
                        headers = self._build_headers()
                        continue
                r.raise_for_status()
                return {"_status": r.status_code, "_url": str(r.url), **r.json()}
            except httpx.HTTPStatusError as exc:
                logger.warning("HTTP %s for %s", exc.response.status_code, path)
                if attempt == self._max_retries:
                    raise
            except Exception as exc:
                logger.warning("Request failed for %s: %s", path, exc)
                if attempt == self._max_retries:
                    raise

        raise RuntimeError(f"API call failed: {path}")

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.get_token()}",
            "Content-Type": "application/json",
        }
