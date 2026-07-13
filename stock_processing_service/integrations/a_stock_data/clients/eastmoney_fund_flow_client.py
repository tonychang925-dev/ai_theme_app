"""Eastmoney stock fund-flow client.

PR4.2.31c-3 collector source. This client only fetches raw day-level fund-flow
payloads. It does not interpret the values as institution or hot-money flows.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from stock_processing_service.integrations.a_stock_data.clients.rate_limited_http_client import (
    RateLimitedHttpClient,
    RegistryPolicy,
    SourceDiagnostics,
)


SOURCE_NAME = "eastmoney_fund_flow"
DAYKLINE_ENDPOINT = "eastmoney_stock_fflow_daykline"
EASTMONEY_DAYKLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
DAYKLINE_FIELDS1 = "f1,f2,f3,f7"
DAYKLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
EASTMONEY_FUND_FLOW_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
}


def default_fund_flow_policy() -> RegistryPolicy:
    """Conservative policy for Eastmoney fund-flow daykline endpoint."""
    return RegistryPolicy(
        min_interval_ms=2500,
        jitter_ms=1500,
        max_retries=3,
        backoff="exponential",
        timeout_ms=15_000,
        session_reuse=True,
        referer="https://quote.eastmoney.com/",
        accept="*/*",
    )


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


def secid_from_stock_code(stock_code: str) -> str:
    code = stock_code.strip().upper().split(".")[0]
    market = "1" if code.startswith("6") else "0"
    return f"{market}.{code}"


def build_daykline_params(stock_code: str, limit: int = 120) -> dict[str, Any]:
    """Build request params aligned with the Eastmoney push2his daykline client."""
    return {
        "secid": secid_from_stock_code(stock_code),
        "lmt": str(limit),
        "fields1": DAYKLINE_FIELDS1,
        "fields2": DAYKLINE_FIELDS2,
    }


class EastmoneyFundFlowClient:
    """Fetch Eastmoney stock fflow daykline payloads."""

    def __init__(
        self,
        *,
        http_client: RateLimitedHttpClient | None = None,
        policy: RegistryPolicy | None = None,
    ) -> None:
        self._http = http_client or RateLimitedHttpClient(
            source_name=SOURCE_NAME,
            endpoint_key=DAYKLINE_ENDPOINT,
            policy=policy or default_fund_flow_policy(),
        )

    @property
    def diagnostics(self) -> SourceDiagnostics:
        return self._http.diagnostics

    async def fetch_stock_daykline(self, stock_code: str, limit: int = 120) -> RawHttpResult:
        params = build_daykline_params(stock_code, limit=limit)
        try:
            async with self._http:
                response = await self._http.get(
                    EASTMONEY_DAYKLINE_URL,
                    params=params,
                    headers=EASTMONEY_FUND_FLOW_HEADERS,
                )
                response.raise_for_status()
        except Exception as exc:
            return RawHttpResult(
                source_name=SOURCE_NAME,
                endpoint_key=DAYKLINE_ENDPOINT,
                request_url=EASTMONEY_DAYKLINE_URL,
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
            endpoint_key=DAYKLINE_ENDPOINT,
            request_url=str(response.url),
            request_params=params,
            status_code=response.status_code,
            response_json=response_json,
            response_text=response.text,
            headers=dict(response.headers),
        )
