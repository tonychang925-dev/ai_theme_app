"""M3b unit tests for RateLimitedHttpClient (mocked HTTP)."""

from __future__ import annotations

import asyncio
import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stock_processing_service.integrations.a_stock_data.clients.rate_limited_http_client import (
    RateLimitedHttpClient,
    RegistryPolicy,
    SourceDiagnostics,
)


def _policy(**kwargs) -> RegistryPolicy:
    defaults = {
        "min_interval_ms": 50,
        "jitter_ms": 0,
        "max_retries": 0,
        "backoff": "linear",
        "timeout_ms": 5000,
    }
    defaults.update(kwargs)
    return RegistryPolicy(**defaults)


def _ok_response() -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def _error_response(status: int) -> httpx.Response:
    return httpx.Response(status)


# ── min_interval_ms ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_min_interval_respected():
    policy = _policy(min_interval_ms=100, jitter_ms=0, max_retries=0)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    with patch.object(client, "_do_request", return_value=_ok_response()) as mock_req:
        t0 = _time.monotonic()
        async with client:
            await client.get("http://example.com/1")
            await client.get("http://example.com/2")
        elapsed = (_time.monotonic() - t0) * 1000

    assert mock_req.call_count == 2
    assert elapsed >= 90, f"elapsed={elapsed:.0f}ms, expected >= 90ms"


@pytest.mark.asyncio
async def test_jitter_does_not_reduce_below_min():
    policy = _policy(min_interval_ms=100, jitter_ms=50, max_retries=0)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    with patch.object(client, "_do_request", return_value=_ok_response()):
        t0 = _time.monotonic()
        async with client:
            await client.get("http://example.com/1")
            await client.get("http://example.com/2")
        elapsed = (_time.monotonic() - t0) * 1000

    assert elapsed >= 90, f"elapsed={elapsed:.0f}ms with jitter"


# ── max_retries ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retries_on_503():
    policy = _policy(min_interval_ms=10, jitter_ms=0, max_retries=2, backoff="linear")
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    error_503 = httpx.HTTPStatusError(
        "503", request=MagicMock(), response=_error_response(503),
    )
    with patch.object(client, "_do_request", side_effect=error_503):
        async with client:
            try:
                await client.get("http://example.com/503")
            except httpx.HTTPStatusError:
                pass

    assert diag.total_requests == 3  # 1 initial + 2 retries
    assert diag.consecutive_failures == 3


@pytest.mark.asyncio
async def test_no_retry_on_404():
    policy = _policy(min_interval_ms=10, max_retries=2)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    error_404 = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=_error_response(404),
    )
    with patch.object(client, "_do_request", side_effect=error_404):
        async with client:
            try:
                await client.get("http://example.com/404")
            except httpx.HTTPStatusError:
                pass

    assert diag.total_requests == 1
    assert diag.total_failures == 1


@pytest.mark.asyncio
async def test_retries_on_request_transport_error():
    policy = _policy(min_interval_ms=10, jitter_ms=0, max_retries=2, backoff="linear")
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    request = httpx.Request("GET", "http://example.com/transient")
    error = httpx.RemoteProtocolError(
        "Server disconnected without sending a response.",
        request=request,
    )
    with patch.object(client, "_do_request", side_effect=error):
        async with client:
            try:
                await client.get("http://example.com/transient")
            except httpx.RemoteProtocolError:
                pass

    assert diag.total_requests == 3
    assert diag.total_failures == 3


# ── backoff ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_linear_backoff_increases_delay():
    policy = _policy(min_interval_ms=100, jitter_ms=0, max_retries=3, backoff="linear")
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    error = httpx.HTTPStatusError("503", request=MagicMock(), response=_error_response(503))
    t0 = _time.monotonic()
    with patch.object(client, "_do_request", side_effect=error):
        async with client:
            try:
                await client.get("http://example.com/503")
            except httpx.HTTPStatusError:
                pass
    elapsed = (_time.monotonic() - t0) * 1000
    # 4 requests (1 + 3 retries) with linear backoff: sleeps of 100, 200, 300 ms
    assert elapsed >= 500, f"elapsed={elapsed:.0f}ms, expected >= 500ms with backoff"


# ── diagnostics ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diagnostics_counts_success():
    policy = _policy(min_interval_ms=10, jitter_ms=0, max_retries=0)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    with patch.object(client, "_do_request", return_value=_ok_response()):
        async with client:
            await client.get("http://example.com/1")
            await client.get("http://example.com/2")

    assert diag.total_requests == 2
    assert diag.total_failures == 0
    assert diag.consecutive_failures == 0
    assert diag.last_success_at is not None


@pytest.mark.asyncio
async def test_diagnostics_counts_failure():
    policy = _policy(min_interval_ms=10, max_retries=0)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    error_500 = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=_error_response(500),
    )
    with patch.object(client, "_do_request", side_effect=error_500):
        async with client:
            try:
                await client.get("http://example.com/500")
            except httpx.HTTPStatusError:
                pass

    assert diag.total_requests == 1
    assert diag.total_failures == 1
    assert diag.consecutive_failures == 1
    assert diag.last_failure_at is not None
    assert diag.last_error_message is not None


@pytest.mark.asyncio
async def test_consecutive_failures_reset_on_success():
    policy = _policy(min_interval_ms=10, max_retries=0)
    diag = SourceDiagnostics()
    client = RateLimitedHttpClient("test", "test_ep", policy=policy, diagnostics=diag)

    error_500 = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=_error_response(500),
    )
    call_count = 0

    async def _alternating(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise error_500
        return _ok_response()

    with patch.object(client, "_do_request", side_effect=_alternating):
        async with client:
            try:
                await client.get("http://example.com/500")
            except httpx.HTTPStatusError:
                pass
            assert diag.consecutive_failures == 1
            await client.get("http://example.com/ok")
            assert diag.consecutive_failures == 0
            assert diag.total_requests == 2
            assert diag.total_failures == 1
