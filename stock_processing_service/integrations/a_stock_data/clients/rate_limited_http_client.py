"""M3 Data Source Governance: unified rate-limited HTTP client.

All external data source clients (THS, Eastmoney, CNInfo, etc.) use
this single client instead of hand-rolling sleep/retry/headers per job.

Design doc: §13.3 RateLimitedHttpClient
"""

from __future__ import annotations

import asyncio
import random
import time as _time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class SourceDiagnostics:
    """Per-source runtime telemetry."""

    source_name: str = ""
    endpoint_key: str = ""
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error_message: str | None = None
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    rate_limit_hits: int = 0
    last_request_at: float | None = None


@dataclass
class RegistryPolicy:
    """Rate-limit / retry policy loaded from market_data_source_registry."""

    min_interval_ms: int = 500
    jitter_ms: int = 100
    max_retries: int = 2
    backoff: str = "linear"  # "linear" | "exponential"
    timeout_ms: int = 10_000
    session_reuse: bool = False
    ua: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    referer: str = ""


class RateLimitedHttpClient:
    """Unified HTTP client governed by registry policy.

    Usage::

        client = RateLimitedHttpClient(source_name="ths",
                                        endpoint_key="ths_hot_reason")
        async with client:
            result = await client.get("http://...")
    """

    def __init__(
        self,
        source_name: str,
        endpoint_key: str,
        *,
        policy: RegistryPolicy | None = None,
        diagnostics: SourceDiagnostics | None = None,
    ) -> None:
        self._source_name = source_name
        self._endpoint_key = endpoint_key
        self._policy = policy or RegistryPolicy()
        self._diag = diagnostics or SourceDiagnostics(
            source_name=source_name, endpoint_key=endpoint_key,
        )
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()
        self._session: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "RateLimitedHttpClient":
        if self._policy.session_reuse and self._session is None:
            self._session = httpx.AsyncClient(
                timeout=self._policy.timeout_ms / 1000,
                headers=self._default_headers(),
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session:
            await self._session.aclose()
            self._session = None

    # ── public API ──────────────────────────────────────────────

    async def get(
        self, url: str, *, params: dict | None = None, **kwargs: Any,
    ) -> httpx.Response:
        """GET with rate-limit, retry, and diagnostics."""
        return await self._request("GET", url, params=params, **kwargs)

    async def post(
        self, url: str, *, json: dict | None = None, **kwargs: Any,
    ) -> httpx.Response:
        """POST with rate-limit, retry, and diagnostics."""
        return await self._request("POST", url, json=json, **kwargs)

    @property
    def diagnostics(self) -> SourceDiagnostics:
        return self._diag

    # ── internals ───────────────────────────────────────────────

    def _default_headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._policy.ua:
            h["User-Agent"] = self._policy.ua
        if self._policy.referer:
            h["Referer"] = self._policy.referer
        return h

    async def _request(
        self, method: str, url: str, **kwargs: Any,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._policy.max_retries + 1):
            try:
                await self._apply_rate_limit()
                response = await self._do_request(method, url, **kwargs)
                self._record_success()
                return response
            except (httpx.HTTPStatusError, httpx.RequestError,
                    httpx.TimeoutException, ConnectionError,
                    asyncio.TimeoutError) as exc:
                last_exc = exc
                self._record_failure(str(exc))
                if not self._should_retry(attempt, exc):
                    raise
                await asyncio.sleep(self._backoff_delay(attempt))

        # All retries exhausted
        assert last_exc is not None
        raise last_exc

    async def _do_request(
        self, method: str, url: str, **kwargs: Any,
    ) -> httpx.Response:
        if self._session and self._policy.session_reuse:
            resp = await self._session.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(
                timeout=self._policy.timeout_ms / 1000,
                headers=self._default_headers(),
            ) as client:
                resp = await client.request(method, url, **kwargs)
        return resp

    async def _apply_rate_limit(self) -> None:
        async with self._lock:
            now = _time.monotonic()
            elapsed_ms = (now - self._last_request) * 1000
            required_ms = self._policy.min_interval_ms
            if self._policy.jitter_ms:
                required_ms += random.randint(0, self._policy.jitter_ms)
            if elapsed_ms < required_ms:
                sleep_ms = required_ms - elapsed_ms
                await asyncio.sleep(sleep_ms / 1000)
                now = _time.monotonic()
            self._last_request = now

    def _should_retry(self, attempt: int, exc: Exception) -> bool:
        if attempt >= self._policy.max_retries:
            return False
        # Retry on timeout / transient errors; don't retry 4xx
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return status in (429, 502, 503, 504)
        return isinstance(exc, (
            httpx.TimeoutException, httpx.ConnectError,
            ConnectionError, asyncio.TimeoutError,
        ))

    def _backoff_delay(self, attempt: int) -> float:
        base_s = self._policy.min_interval_ms / 1000
        if self._policy.backoff == "exponential":
            return base_s * (2 ** (attempt + 1))
        return base_s * (attempt + 1)  # linear

    def _record_success(self) -> None:
        self._diag.total_requests += 1
        self._diag.consecutive_failures = 0
        self._diag.last_success_at = _time.time()

    def _record_failure(self, message: str) -> None:
        self._diag.total_requests += 1
        self._diag.total_failures += 1
        self._diag.consecutive_failures += 1
        self._diag.last_failure_at = _time.time()
        self._diag.last_error_message = message


def load_policy_from_registry(
    registry_row: dict[str, Any],
) -> RegistryPolicy:
    """Convert a market_data_source_registry row to RegistryPolicy.

    Args:
        registry_row: dict with keys matching the registry table columns.
    """
    rlp = registry_row.get("rate_limit_policy") or {}
    if isinstance(rlp, str):
        import json as _json
        rlp = _json.loads(rlp)

    return RegistryPolicy(
        min_interval_ms=int(rlp.get("min_interval_ms", 500)),
        jitter_ms=int(rlp.get("jitter_ms", 100)),
        max_retries=int(rlp.get("max_retries", 2)),
        backoff=str(rlp.get("backoff", "linear")),
        timeout_ms=int(rlp.get("timeout_ms", 10_000)),
        session_reuse=bool(rlp.get("session_reuse", False)),
    )
