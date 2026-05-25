"""TDX Market Agent HTTP 客户端 — 不 import mootdx."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("sps.tdx_market.agent_client")


class TdxMarketAgentClient:
    """通过 HTTP 调用本地 tdx_market_agent，不接触 mootdx."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._connected: bool = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    async def get_quote(self, stock_id: str) -> dict[str, Any]:
        return await self._get(f"/quote/{stock_id}")

    async def get_minute(self, stock_id: str) -> dict[str, Any]:
        return await self._get(f"/minute/{stock_id}")

    async def get_bars(
        self, stock_id: str, frequency: int = 9, offset: int = 100,
    ) -> dict[str, Any]:
        return await self._get(f"/bars/{stock_id}", params={"frequency": frequency, "offset": offset})

    async def check_connection(self) -> bool:
        try:
            resp = await self.health()
            self._connected = resp.get("status") == "ok"
            return self._connected
        except Exception as exc:
            logger.warning("agent health check failed: %s", exc)
            self._connected = False
            return False

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            return r.json()
