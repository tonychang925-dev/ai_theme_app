"""M4b: CNInfo (巨潮资讯) announcement client.

Uses RateLimitedHttpClient per M3 governance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.integrations.a_stock_data.clients.rate_limited_http_client import (
    RateLimitedHttpClient,
    RegistryPolicy,
    SourceDiagnostics,
)

SOURCE_NAME = "cninfo"
ANNOUNCEMENT_ENDPOINT = "cninfo_announcements"
CNINFO_BASE_URL = "http://www.cninfo.com.cn/new/disclosure"


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


class CninfoClient:
    """CNInfo announcement client governed by M3 RateLimitedHttpClient."""

    def __init__(
        self,
        *,
        http_client: RateLimitedHttpClient | None = None,
        policy: RegistryPolicy | None = None,
    ) -> None:
        self._http = http_client or RateLimitedHttpClient(
            source_name=SOURCE_NAME,
            endpoint_key=ANNOUNCEMENT_ENDPOINT,
            policy=policy or RegistryPolicy(
                min_interval_ms=1000, jitter_ms=300,
                max_retries=1, backoff="linear", timeout_ms=20_000,
                referer="http://www.cninfo.com.cn/",
            ),
        )

    @property
    def diagnostics(self) -> SourceDiagnostics:
        return self._http.diagnostics

    async def fetch_announcements(
        self,
        *,
        page_num: int = 1,
        page_size: int = 30,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> RawHttpResult:
        """Fetch recent announcements.

        Args:
            page_num: page number (1-indexed)
            page_size: results per page
            start_date: optional start date filter
            end_date: optional end date filter
        """
        se_date = ""
        if start_date and end_date:
            se_date = f"{start_date.isoformat()}~{end_date.isoformat()}"

        data = {
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "column": "szse_latest",
            "tabName": "latest",
            "seDate": se_date,
        }
        return await self._post(data)

    async def fetch_stock_announcements(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date | None = None,
        page_num: int = 1,
        page_size: int = 30,
    ) -> RawHttpResult:
        """Fetch announcements for a specific stock.

        Args:
            stock_code: 6-digit stock code
            start_date: start date
            end_date: end date (defaults to start_date)
            page_num: page (1-indexed)
            page_size: results per page
        """
        ed = end_date or start_date
        data = {
            "stock": stock_code,
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "column": "szse_latest",
            "tabName": "latest",
            "seDate": f"{start_date.isoformat()}~{ed.isoformat()}",
        }
        return await self._post(data)

    async def _post(self, data: dict) -> RawHttpResult:
        try:
            async with self._http:
                r = await self._http.post(CNINFO_BASE_URL, data=data)
        except Exception as exc:
            return RawHttpResult(
                source_name=SOURCE_NAME,
                endpoint_key=ANNOUNCEMENT_ENDPOINT,
                request_url=CNINFO_BASE_URL,
                request_params=data,
                status_code=0,
                response_text=str(exc),
                error_message=f"{type(exc).__name__}: {exc}",
            )

        response_json: Any | None = None
        try:
            response_json = r.json()
        except ValueError:
            pass

        return RawHttpResult(
            source_name=SOURCE_NAME,
            endpoint_key=ANNOUNCEMENT_ENDPOINT,
            request_url=str(r.url),
            request_params=data,
            status_code=r.status_code,
            response_json=response_json,
            response_text=r.text,
            error_message="",
            headers=dict(r.headers),
        )
