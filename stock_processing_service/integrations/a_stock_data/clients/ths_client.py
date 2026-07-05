"""M3: THS client migrated to RateLimitedHttpClient + registry governance.

Design doc: §13.4 M3-T04
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


SOURCE_NAME = "ths"
THS_HOT_REASON_ENDPOINT_KEY = "ths_hot_reason"
THS_HOT_REASON_URL = (
    "http://zx.10jqka.com.cn/event/api/getharden/"
    "date/{date}/orderby/date/orderway/desc/charset/GBK/"
)


@dataclass(frozen=True)
class RawHttpResult:
    source_name: str
    endpoint_key: str
    trade_date: date
    request_url: str
    request_params: dict[str, Any]
    status_code: int
    response_json: Any | None = None
    response_text: str = ""
    error_message: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class ThsClient:
    """HTTP client for THS endpoints, governed by registry + rate limiter.

    Uses RateLimitedHttpClient for all HTTP calls — no hand-rolled
    sleep/retry/headers.  Backward-compatible with existing callers
    that don't pass an http_client.
    """

    def __init__(
        self,
        *,
        base_url: str = THS_HOT_REASON_URL,
        http_client: RateLimitedHttpClient | None = None,
        policy: RegistryPolicy | None = None,
    ) -> None:
        self._base_url = base_url
        self._http = http_client or RateLimitedHttpClient(
            source_name=SOURCE_NAME,
            endpoint_key=THS_HOT_REASON_ENDPOINT_KEY,
            policy=policy,
        )

    @property
    def diagnostics(self) -> SourceDiagnostics:
        return self._http.diagnostics

    async def fetch_hot_reason(self, trade_date: date) -> RawHttpResult:
        url = self._base_url.format(date=trade_date.isoformat())
        params: dict[str, Any] = {}
        try:
            async with self._http:
                response = await self._http.get(url, params=params)
        except Exception as exc:
            return RawHttpResult(
                source_name=SOURCE_NAME,
                endpoint_key=THS_HOT_REASON_ENDPOINT_KEY,
                trade_date=trade_date,
                request_url=url,
                request_params=params,
                status_code=0,
                response_text=str(exc),
                error_message=f"{type(exc).__name__}: {exc}",
            )

        response_json: Any | None = None
        try:
            response_json = response.json()
        except ValueError:
            pass

        return RawHttpResult(
            source_name=SOURCE_NAME,
            endpoint_key=THS_HOT_REASON_ENDPOINT_KEY,
            trade_date=trade_date,
            request_url=str(response.url),
            request_params=params,
            status_code=response.status_code,
            response_json=response_json,
            response_text=response.text,
            headers=dict(response.headers),
        )
