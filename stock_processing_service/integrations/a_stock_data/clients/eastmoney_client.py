"""M4a: Eastmoney concept/industry/region block client.

Uses RateLimitedHttpClient per M3 governance — no hand-rolled sleep/retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stock_processing_service.integrations.a_stock_data.clients.rate_limited_http_client import (
    RateLimitedHttpClient,
    RegistryPolicy,
    SourceDiagnostics,
)

SOURCE_NAME = "eastmoney"
CONCEPT_BLOCK_ENDPOINT = "eastmoney_concept_blocks"

EASTMONEY_BASE = "http://push2.eastmoney.com/api/qt"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"

# Block type fs codes
FS_CONCEPT = "m:90+t:3"   # 概念板块
FS_INDUSTRY = "m:90+t:2"  # 行业板块
FS_REGION = "m:90+t:1"    # 地域板块


@dataclass(frozen=True)
class RawHttpResult:
    source_name: str
    endpoint_key: str
    request_url: str
    request_params: dict[str, Any]
    status_code: int
    response_json: Any | None = None
    response_text: str = ""
    error_message: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class EastmoneyClient:
    """Eastmoney concept/industry/region block client.

    Governed by M3 RateLimitedHttpClient for all HTTP calls.
    """

    def __init__(
        self,
        *,
        http_client: RateLimitedHttpClient | None = None,
        policy: RegistryPolicy | None = None,
    ) -> None:
        self._http = http_client or RateLimitedHttpClient(
            source_name=SOURCE_NAME,
            endpoint_key=CONCEPT_BLOCK_ENDPOINT,
            policy=policy or RegistryPolicy(
                min_interval_ms=1000, jitter_ms=300,
                max_retries=1, backoff="linear", timeout_ms=15_000,
                session_reuse=True,
                referer="http://quote.eastmoney.com/",
            ),
        )

    @property
    def diagnostics(self) -> SourceDiagnostics:
        return self._http.diagnostics

    async def fetch_block_list(
        self, block_type: str = "concept", page_size: int = 500,
    ) -> RawHttpResult:
        """Fetch the list of blocks.

        Args:
            block_type: "concept" | "industry" | "region"
            page_size: max blocks per page (default 500)
        """
        fs_map = {"concept": FS_CONCEPT, "industry": FS_INDUSTRY, "region": FS_REGION}
        fs = fs_map.get(block_type, FS_CONCEPT)
        params = {
            "fields": "f12,f14",
            "fltt": 2,
            "pn": 1,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": EM_UT,
            "fid": "f3",
            "fs": fs,
        }
        url = f"{EASTMONEY_BASE}/slist/get"
        return await self._get(url, params)

    async def fetch_block_stocks(
        self, block_code: str, page_size: int = 500,
    ) -> RawHttpResult:
        """Fetch member stocks for a specific block.

        Args:
            block_code: e.g. "BK0001"
            page_size: max stocks per page (default 500)
        """
        params = {
            "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18",
            "fltt": 2,
            "pn": 1,
            "pz": page_size,
            "np": 1,
            "ut": EM_UT,
            "fid": "f3",
            "fs": f"b:{block_code}",
        }
        url = f"{EASTMONEY_BASE}/clist/get"
        return await self._get(url, params)

    async def _get(self, url: str, params: dict) -> RawHttpResult:
        try:
            async with self._http:
                r = await self._http.get(url, params=params)
        except Exception as exc:
            return RawHttpResult(
                source_name=SOURCE_NAME,
                endpoint_key=CONCEPT_BLOCK_ENDPOINT,
                request_url=url,
                request_params=params,
                status_code=0,
                response_text=str(exc),
                error_message=f"{type(exc).__name__}: {exc}",
            )

        response_json: Any | None = None
        try:
            response_json = r.json()
        except ValueError:
            pass

        # Eastmoney returns rc != 0 on auth/rate-limit errors
        error_message = ""
        if isinstance(response_json, dict) and response_json.get("rc") not in (None, 0):
            error_message = f"EM rc={response_json['rc']} rt={response_json.get('rt','?')}"
            response_json = None

        return RawHttpResult(
            source_name=SOURCE_NAME,
            endpoint_key=CONCEPT_BLOCK_ENDPOINT,
            request_url=str(r.url),
            request_params=params,
            status_code=r.status_code,
            response_json=response_json,
            response_text=r.text,
            error_message=error_message,
            headers=dict(r.headers),
        )
