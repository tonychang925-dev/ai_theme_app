from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx


SOURCE_NAME = "ths"
THS_HOT_REASON_ENDPOINT_KEY = "ths_hot_reason"
THS_HOT_REASON_URL = "https://eq.10jqka.com.cn/open/api/hot_list/v1/stock_reason"


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
    headers: dict[str, str] = field(default_factory=dict)


class ThsClient:
    """HTTP client for THS endpoints. It does not normalize or persist data."""

    def __init__(
        self,
        *,
        base_url: str = THS_HOT_REASON_URL,
        timeout_seconds: float = 10.0,
        user_agent: str = "Mozilla/5.0 ai_theme_app/ths-hot-reason",
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def fetch_hot_reason(self, trade_date: date) -> RawHttpResult:
        params = {"date": trade_date.isoformat()}
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://eq.10jqka.com.cn/",
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds, headers=headers, follow_redirects=True) as client:
            response = await client.get(self._base_url, params=params)
        response_json: Any | None = None
        try:
            response_json = response.json()
        except ValueError:
            response_json = None
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

