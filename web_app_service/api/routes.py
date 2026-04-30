import json
import os
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from web_app_service.core.read_client import StockProcessingReadClient

router = APIRouter()
client = StockProcessingReadClient()
INTEL_SOURCE_BASE_URL = str(os.getenv("INTEL_SOURCE_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
ALLOWED_SSE_EVENTS = {
    "intel_item",
    "heartbeat",
    "stream_state",
    "theme_update",
    "validation_update",
    "error",
}


async def _proxy_json(path: str, params: dict[str, str]) -> dict:
    url = f"{INTEL_SOURCE_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, dict) else {}


async def _proxy_json_safe(path: str, params: dict[str, str]) -> dict:
    try:
        return await _proxy_json(path, params)
    except Exception as exc:
        return {
            "items": [],
            "count": 0,
            "diagnostics": {
                "partial": True,
                "error": str(exc),
                "source": "web_app_service_proxy_safe_fallback",
            },
        }


def _emit_sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _try_parse_event_line(line: str) -> str | None:
    if line.startswith("event:"):
        return line.split(":", 1)[1].strip()
    return None


@router.get("/post_market_snapshot")
async def post_market_snapshot(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_post_market_snapshot(trade_date)).model_dump()


@router.get("/strong_watch")
async def strong_watch(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_strong_watch(trade_date)).model_dump()


@router.get("/w2s_candidates")
async def w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_w2s_candidates(trade_date)).model_dump()


@router.get("/intel/feed")
async def intel_feed(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    type: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    params = {
        "date": date,
        "session": session,
        "type": type,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "limit": str(limit),
    }
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    data = await _proxy_json("/api/intel/feed", query)
    return data if isinstance(data, dict) else {"items": [], "count": 0, "diagnostics": {"partial": True}}


@router.get("/workspace/theme-radar")
async def workspace_theme_radar(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict:
    params = {"date": date, "session": session, "type": "all", "limit": str(limit)}
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    feed = await _proxy_json_safe("/api/intel/feed", query)
    items = list(feed.get("items") or [])
    by_theme: dict[str, dict] = {}
    for item in items:
        theme_names = item.get("theme_names") or []
        subject_key = str(item.get("subject_key") or "")
        for theme_name in theme_names[:3]:
            key = subject_key or str(theme_name)
            row = by_theme.setdefault(
                key,
                {
                    "theme_id": key,
                    "theme_name": str(theme_name),
                    "heat": 0,
                    "stage": "UNKNOWN",
                    "stock_count": 0,
                },
            )
            row["heat"] += 1
            row["stock_count"] = max(row["stock_count"], len(item.get("stock_ids") or []))
    themes = sorted(by_theme.values(), key=lambda x: (-int(x["heat"]), x["theme_name"]))[:limit]
    return {
        "date": date,
        "themes": themes,
        "source": "intel_feed_aggregate",
        "diagnostics": dict(feed.get("diagnostics") or {}),
    }


@router.get("/workspace/intel-context")
async def workspace_intel_context(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    params = {
        "date": date,
        "session": session,
        "type": "all",
        "subject_key": subject_key,
        "stock_id": stock_id,
        "limit": str(limit),
    }
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    feed = await _proxy_json_safe("/api/intel/feed", query)
    return {
        "date": date,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "items": list(feed.get("items") or []),
        "count": int(feed.get("count") or 0),
        "diagnostics": dict(feed.get("diagnostics") or {}),
        "source": "intel_feed_proxy",
    }


@router.get("/workspace/market-validation")
async def workspace_market_validation(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
) -> dict:
    strong_watch_payload = (await client.get_strong_watch(trade_date)).model_dump()
    w2s_payload = (await client.get_w2s_candidates(trade_date)).model_dump()
    sw_stocks = list(strong_watch_payload.get("stocks") or [])
    w2s_candidates = list(w2s_payload.get("candidates") or [])
    stock_view = None
    if stock_id:
        stock_view = next(
            (row for row in sw_stocks if str(row.get("stock_id") or "") == stock_id),
            None,
        )
    return {
        "trade_date": trade_date,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "candidate_level": "observe" if stock_view else "unknown",
        "support_type": "unknown",
        "support_score": None,
        "reject_reasons": [],
        "strong_watch_count": len(sw_stocks),
        "w2s_candidate_count": len(w2s_candidates),
        "stock_validation": stock_view,
        "source": "strong_watch_w2s_aggregate",
    }


@router.get("/intel/stream")
async def intel_stream(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    type: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> StreamingResponse:
    params = {
        "date": date,
        "session": session,
        "type": type,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "limit": str(limit),
    }
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    url = f"{INTEL_SOURCE_BASE_URL}/api/intel/stream"

    async def _proxy_sse() -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=None) as http:
                async with http.stream("GET", url, params=query) as upstream:
                    upstream.raise_for_status()
                    pending_event: str | None = None
                    async for line in upstream.aiter_lines():
                        if line is None:
                            continue
                        event_name = _try_parse_event_line(line)
                        if event_name is not None:
                            if event_name not in ALLOWED_SSE_EVENTS:
                                yield _emit_sse(
                                    "error",
                                    {
                                        "code": "INVALID_EVENT_TYPE",
                                        "message": f"upstream event type not allowed: {event_name}",
                                        "retryable": True,
                                    },
                                )
                                pending_event = "error"
                            else:
                                pending_event = event_name
                            # Preserve event line for downstream consumers.
                            yield f"event: {pending_event}\n".encode("utf-8")
                            continue

                        if line.startswith("data:"):
                            # data line can be forwarded directly.
                            yield (line + "\n").encode("utf-8")
                            continue

                        # keepalive/blank/comment lines
                        yield (line + "\n").encode("utf-8")
        except Exception as exc:
            yield _emit_sse(
                "error",
                {
                    "code": "UPSTREAM_STREAM_ERROR",
                    "message": str(exc),
                    "retryable": True,
                },
            )

    return StreamingResponse(
        _proxy_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
