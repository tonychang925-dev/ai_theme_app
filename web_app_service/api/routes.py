import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web_app_service.core.read_client import StockProcessingReadClient

logger = logging.getLogger(__name__)

router = APIRouter()
client = StockProcessingReadClient()


def _to_float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_theme_stage(item: dict) -> str:
    raw = str(
        item.get("stage")
        or item.get("cycle_stage")
        or item.get("cycle_state")
        or item.get("final_cycle_state")
        or item.get("mainline_state")
        or item.get("status")
        or ""
    ).strip().lower()
    if not raw:
        return "UNKNOWN"
    if raw in {"confirm", "confirmed", "active", "hot", "up"}:
        return "CONFIRMED"
    if raw in {"forming", "new", "observe", "observing", "watch"}:
        return "FORMING"
    if raw in {"fade", "fading", "cooling", "down"}:
        return "FADE"
    return raw.upper()


def _stage_priority(stage: str) -> int:
    normalized = (stage or "UNKNOWN").strip().lower()
    if normalized in ("unknown", "", "none"):
        return 0
    return 1  # 任何有效周期状态优先级都高于 UNKNOWN


def _normalize_theme_name(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return "".join(ch for ch in text if not ch.isspace())


STOCK_PROCESSING_BASE_URL = str(os.getenv("STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090")).rstrip("/")
JYHF_CDP_SERVICE_BASE_URL = str(os.getenv("JYHF_CDP_SERVICE_BASE_URL", "http://127.0.0.1:8095")).rstrip("/")
ALLOWED_SSE_EVENTS = {
    "intel_item",
    "heartbeat",
    "stream_state",
    "theme_update",
    "validation_update",
    "error",
}

RECAP_TYPE_POST_MARKET = "post_market"
RECAP_TYPE_PRE_MARKET = "pre_market"


async def _proxy_stock_processing_json(path: str, params: dict[str, str]) -> dict:
    url = f"{STOCK_PROCESSING_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as http:
            resp = await http.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"upstream unavailable: {exc}") from exc
    return data if isinstance(data, dict) else {}


async def _proxy_stock_processing_post_json(path: str, payload: dict, timeout: float = 120.0) -> dict:
    url = f"{STOCK_PROCESSING_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http:
            resp = await http.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.ReadTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "WEB_APP_UPSTREAM_TIMEOUT",
                "message": f"upstream timeout after {timeout:.0f}s",
                "upstream": url,
                "method": "POST",
            },
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"upstream unavailable: {exc}") from exc
    return data if isinstance(data, dict) else {}


async def _proxy_stock_processing_request_json(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    payload: dict | None = None,
    timeout: float = 120.0,
) -> dict | list:
    url = f"{STOCK_PROCESSING_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http:
            resp = await http.request(method.upper(), url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        detail: object
        try:
            parsed = exc.response.json()
            if isinstance(parsed, dict):
                detail = str(parsed.get("detail", json.dumps(parsed, ensure_ascii=False)))
            else:
                detail = str(parsed)
        except Exception:
            detail = exc.response.text or str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=str(detail)) from exc
    except httpx.ReadTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "WEB_APP_UPSTREAM_TIMEOUT",
                "message": f"upstream timeout after {timeout:.0f}s",
                "upstream": url,
                "method": method.upper(),
            },
        ) from exc
    if isinstance(data, (dict, list)):
        return data
    return {}


async def _proxy_jyhf_cdp_service_json(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    payload: dict | None = None,
    timeout: float = 10.0,
) -> dict:
    url = f"{JYHF_CDP_SERVICE_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http:
            resp = await http.request(method.upper(), url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "JYHF_CDP_SERVICE_UNAVAILABLE",
                "message": str(exc),
                "upstream": url,
            },
        ) from exc
    return data if isinstance(data, dict) else {}


def _emit_sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _try_parse_event_line(line: str) -> str | None:
    if line.startswith("event:"):
        return line.split(":", 1)[1].strip()
    return None


def _validate_sse_payload(event_name: str, payload: dict) -> tuple[bool, str | None]:
    # Minimal field-level contracts for P4.phase1-T06.
    required: dict[str, tuple[str, ...]] = {
        "intel_item": ("item_id", "item_type", "occurred_at", "title"),
        "heartbeat": (),
        "stream_state": ("status",),
        "theme_update": ("subject_key",),
        "validation_update": ("trade_date",),
        "error": ("code", "message"),
    }
    if event_name not in required:
        return False, f"unsupported event type: {event_name}"
    candidate_payload = payload
    # Upstream intel_item may wrap entity under `item`.
    if event_name == "intel_item" and isinstance(payload.get("item"), dict):
        candidate_payload = payload["item"]

    for key in required[event_name]:
        if key not in candidate_payload:
            return False, f"missing required field '{key}' for event '{event_name}'"
    return True, None


async def _intel_stream_proxy(
    request: Request,
    *,
    url: str,
    query: dict[str, str],
    heartbeat_interval: float = 15.0,
    poll_interval: float = 5.0,
) -> AsyncIterator[bytes]:
    try:
        seen_item_ids: set[str] = set()
        elapsed = 0.0
        initialized = False
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as http:
            while True:
                if await request.is_disconnected():
                    return

                resp = await http.get(url, params=query)
                resp.raise_for_status()
                data = resp.json()
                items = list(data.get("items") or []) if isinstance(data, dict) else []

                if not initialized:
                    yield _emit_sse(
                        "stream_state",
                        {"status": "connected", "source": "stock_processing_read_api", "count": len(items)},
                    )
                    initialized = True

                fresh_items: list[dict[str, Any]] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("item_id") or item.get("event_id") or "")
                    if not item_id or item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    fresh_items.append(item)

                for item in reversed(fresh_items):
                    payload = {
                        "event_id": str(item.get("item_id") or item.get("event_id") or ""),
                        "occurred_at": str(item.get("occurred_at") or item.get("event_time") or ""),
                        "event_type": str(item.get("item_type") or item.get("event_type") or "event"),
                        "item": item,
                    }
                    ok, reason = _validate_sse_payload("intel_item", payload)
                    if not ok:
                        yield _emit_sse(
                            "error",
                            {
                                "code": "INVALID_EVENT_PAYLOAD",
                                "message": reason or "payload contract mismatch",
                                "retryable": True,
                                "event_type": "intel_item",
                            },
                        )
                        continue
                    yield _emit_sse("intel_item", payload)

                elapsed += poll_interval
                if elapsed >= heartbeat_interval:
                    yield _emit_sse("heartbeat", {"source": "stock_processing_read_api", "ts": datetime.now(timezone.utc).isoformat()})
                    elapsed = 0.0

                await asyncio.sleep(poll_interval)
    except Exception as exc:
        yield _emit_sse(
            "error",
            {
                "code": "SSE_UPSTREAM_UNREACHABLE",
                "message": str(exc),
                "retryable": True,
                "upstream": url,
            },
        )


def _as_recap_view_model_v2_from_snapshot(snapshot: dict, report_type: str) -> dict:
    trade_date = str(snapshot.get("trade_date") or "")
    snapshot_version = str(snapshot.get("snapshot_version") or "unknown")
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}

    maybe = payload.get("report") or payload.get("recap") or payload.get("market_report")
    if isinstance(maybe, dict):
        sections = maybe.get("sections") if isinstance(maybe.get("sections"), list) else []
        return {
            "report_type": report_type,
            "trade_date": str(maybe.get("trade_date") or trade_date),
            "title": str(maybe.get("title") or ("盘前必读" if report_type == RECAP_TYPE_PRE_MARKET else "盘后复盘")),
            "summary": str(maybe.get("summary") or ""),
            "highlights": [str(x) for x in (maybe.get("highlights") or []) if x is not None],
            "sections": [
                {
                    "heading": str((row or {}).get("heading") or "--"),
                    "items": [str(x) for x in ((row or {}).get("items") or []) if x is not None],
                }
                for row in sections
                if isinstance(row, dict)
            ],
            "source": "recap_v2_report",
            "diagnostics": {
                "snapshot_version": snapshot_version,
            },
        }

    recap_doc = payload.get("recap_doc") if isinstance(payload.get("recap_doc"), dict) else {}
    # 新链格式：recap_doc 内容直接作为 payload 存储（无嵌套 recap_doc key）
    if not recap_doc and isinstance(payload.get("candidate_count"), (int, float)):
        recap_doc = payload
    candidate_count = int(recap_doc.get("candidate_count") or 0)
    strong_watch_input_count = int(recap_doc.get("strong_watch_input_count") or recap_doc.get("strong_watch_input_7d_count") or 0)
    strong_watch_promoted_count = int(recap_doc.get("strong_watch_promoted_count") or 0)
    strong_watch_history_count = int(recap_doc.get("strong_watch_history_count") or 0)

    return {
        "report_type": report_type,
        "trade_date": trade_date,
        "title": "盘前必读（快照映射）" if report_type == RECAP_TYPE_PRE_MARKET else "盘后复盘（快照映射）",
        "summary": f"候选 {candidate_count} | 强势池输入 {strong_watch_input_count} | 晋级 {strong_watch_promoted_count}",
        "highlights": [
            f"snapshot_version: {snapshot_version}",
            f"strong_watch_history_count: {strong_watch_history_count}",
        ],
        "sections": [
            {
                "heading": "强势池与候选概览",
                "items": [
                    f"candidate_count: {candidate_count}",
                    f"strong_watch_input_count: {strong_watch_input_count}",
                    f"strong_watch_promoted_count: {strong_watch_promoted_count}",
                    f"strong_watch_history_count: {strong_watch_history_count}",
                ],
            }
        ],
        "source": "recap_v2_snapshot",
        "diagnostics": {
            "snapshot_version": snapshot_version,
        },
    }


@router.get("/post_market_snapshot")
async def post_market_snapshot(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_post_market_snapshot(trade_date)).model_dump()


@router.get("/strong_watch")
async def strong_watch(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_strong_watch(trade_date)).model_dump()


@router.get("/w2s_candidates")
async def w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return (await client.get_w2s_candidates(trade_date)).model_dump()


@router.get("/recap")
async def recap(
    date: str = Query(..., description="YYYY-MM-DD"),
    report_type: str = Query(default=RECAP_TYPE_POST_MARKET, pattern="^(pre_market|post_market)$"),
) -> dict:
    snapshot = (await client.get_post_market_snapshot(date)).model_dump()
    payload = dict(snapshot.get("payload") or {})
    if str(snapshot.get("snapshot_version") or "") in {"", "missing"} or not payload:
        raise HTTPException(
            status_code=424,
            detail={
                "code": "SNAPSHOT_MISSING",
                "message": f"post_market_recap_snapshot missing for trade_date={date}",
                "trade_date": date,
                "report_type": report_type,
                "snapshot_version": str(snapshot.get("snapshot_version") or "missing"),
            },
        )
    return _as_recap_view_model_v2_from_snapshot(snapshot, report_type)


@router.get("/recap/defaults")
async def recap_defaults() -> dict:
    return await _proxy_stock_processing_json("/api/v1/recap/defaults", {})


@router.post("/recap/publish-notion")
async def recap_publish_notion(payload: dict) -> dict:
    trade_date = str(payload.get("trade_date") or "").strip()
    if not trade_date:
        raise HTTPException(status_code=400, detail="trade_date is required")

    body = {
        "trade_date": trade_date,
        "force": bool(payload.get("force", False)),
        "dry_run": bool(payload.get("dry_run", False)),
    }

    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/recap/publish-notion",
        payload=body,
        timeout=60.0,
    )

    if isinstance(data, dict):
        return data

    raise HTTPException(status_code=502, detail="invalid notion publish response")


@router.post("/trade-plan/review")
async def trade_plan_review(payload: dict) -> dict:
    trade_date = str(payload.get("trade_date") or "").strip()
    plan_date = str(payload.get("plan_date") or "").strip()
    if not trade_date:
        raise HTTPException(status_code=400, detail="trade_date is required")
    if not plan_date:
        raise HTTPException(status_code=400, detail="plan_date is required")

    body = {
        "trade_date": trade_date,
        "plan_date": plan_date,
        "dry_run": bool(payload.get("dry_run", True)),
        "force": bool(payload.get("force", False)),
    }
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/trade-plan/review",
        payload=body,
        timeout=60.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid trade plan review response")


@router.get("/theme_workspace/{subject_key}")
@router.get("/theme-workspace/{subject_key}")
async def theme_workspace(subject_key: str, request: Request) -> dict:
    params = {k: v for k, v in request.query_params.items()}
    return await _proxy_stock_processing_json(f"/api/v1/theme_workspace/{subject_key}", params)


# ── M4h: Recap Read APIs ──

@router.get("/recap/latest")
async def recap_latest(request: Request) -> dict:
    return await _proxy_stock_processing_json("/api/v1/recap/latest", {})


@router.get("/recap/{trade_date}")
async def recap_by_date(trade_date: str, request: Request) -> dict:
    return await _proxy_stock_processing_json(f"/api/v1/recap/{trade_date}", {})


@router.get("/themes/top")
async def themes_top(
    trade_date: str | None = None,
    limit: int = 10,
    request: Request | None = None,
) -> list[dict]:
    params: dict[str, str] = {}
    if trade_date:
        params["trade_date"] = trade_date
    params["limit"] = str(limit)
    return await _proxy_stock_processing_json("/api/v1/themes/top", params)


@router.get("/leaders/{theme_name}")
async def theme_leaders(
    theme_name: str,
    trade_date: str | None = None,
    limit: int = 10,
    request: Request | None = None,
) -> list[dict]:
    params: dict[str, str] = {}
    if trade_date:
        params["trade_date"] = trade_date
    params["limit"] = str(limit)
    return await _proxy_stock_processing_json(f"/api/v1/leaders/{theme_name}", params)


# ── P1: PostMarket Readiness API ──

@router.get("/post-market/derived-data/readiness")
async def get_post_market_readiness(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """查询盘后复盘派生数据 readiness 状态。BFF 代理 → SPS。"""
    return await _proxy_stock_processing_json(
        "/api/v1/post-market/derived-data/readiness",
        {"date": date},
    )


@router.get("/post-market/jobs/status")
async def get_post_market_jobs_status(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    """查询盘后复盘各阶段任务状态。BFF 代理 → SPS。"""
    return await _proxy_stock_processing_json(
        "/api/v1/post-market/jobs/status",
        {"date": date},
    )


@router.post("/post-market/derived-data/generate")
async def generate_post_market_derived_data(payload: dict | None = None) -> dict:
    """生成每日动态复盘派生数据。BFF 代理 → SPS。"""
    return await _proxy_stock_processing_post_json(
        "/api/v1/post-market/derived-data/generate",
        payload or {},
        timeout=600.0,
    )


@router.post("/post-market/recap/generate")
async def generate_post_market_recap(payload: dict | None = None) -> dict:
    """生成盘后复盘报告快照。BFF 代理 → SPS。

    force=true 时使用 async_mode=true 异步提交，立即返回 202 accepted。
    """
    p = dict(payload or {})
    force = bool(p.get("force", False))
    if force:
        p["async_mode"] = True
        return await _proxy_stock_processing_post_json(
            "/api/v1/post-market/recap/generate",
            p,
            timeout=15.0,
        )
    return await _proxy_stock_processing_post_json(
        "/api/v1/post-market/recap/generate",
        p,
        timeout=300.0,
    )


@router.get("/post-market/recap/generate/status")
async def get_post_market_recap_generate_status(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    snapshot_version: str = Query(""),
) -> dict:
    """查询重新复盘任务状态。BFF 代理 → SPS。"""
    return await _proxy_stock_processing_json(
        "/api/v1/post-market/recap/generate/status",
        {"trade_date": trade_date, "snapshot_version": snapshot_version},
    )


@router.get("/daily-review")
async def daily_review(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return await _proxy_stock_processing_json(
        "/api/v1/daily_review",
        {"trade_date": date},
    )


@router.post("/daily-review/generate")
async def daily_review_generate(payload: dict | None = None) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/daily_review/generate", payload or {})


@router.get("/daily-review-v2")
async def daily_review_v2(date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return await _proxy_stock_processing_json(
        "/api/v2/daily-review-v2",
        {"date": date},
    )


@router.post("/post-market/daily-review-v2/generate")
async def daily_review_v2_generate(payload: dict | None = None) -> dict:
    return await _proxy_stock_processing_post_json(
        "/api/v2/post-market/daily-review-v2/generate",
        payload or {},
        timeout=180.0,
    )


@router.get("/stock_workspace/{stock_id}")
@router.get("/stock-workspace/{stock_id}")
async def stock_workspace(stock_id: str, request: Request) -> dict:
    params = {k: v for k, v in request.query_params.items()}
    return await _proxy_stock_processing_json(f"/api/v1/stock/workspace/{stock_id}", params)


@router.get("/mobile/defaults")
async def mobile_defaults() -> dict:
    return await _proxy_stock_processing_json("/api/v1/mobile/defaults", {})


@router.get("/mobile/recap")
async def mobile_recap(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return await _proxy_stock_processing_json("/api/v1/mobile/recap", {"trade_date": trade_date})


@router.get("/mobile/screener/latest")
async def mobile_screener(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    strategy: str = Query("weak_to_strong"),
) -> dict:
    return await _proxy_stock_processing_json(
        "/api/v1/mobile/screener/latest",
        {"trade_date": trade_date, "strategy": strategy},
    )


@router.post("/mobile/news-recommend")
async def mobile_news_recommend(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/mobile/news-recommend", payload)


@router.get("/stock-screener/strategies")
async def stock_screener_strategies(active_only: bool = Query(default=True)) -> list[dict]:
    payload = await _proxy_stock_processing_request_json(
        "GET",
        "/api/v1/stock-screener/strategies",
        params={"active_only": str(active_only).lower()},
    )
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    raise HTTPException(status_code=502, detail="invalid stock-screener strategies response")


@router.post("/stock-screener/execute")
async def stock_screener_execute(payload: dict) -> dict:
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/stock-screener/execute",
        payload=payload,
        timeout=120.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener execute response")


@router.get("/stock-screener/executions/{job_id}")
async def stock_screener_execution(job_id: str) -> dict:
    data = await _proxy_stock_processing_request_json(
        "GET",
        f"/api/v1/stock-screener/executions/{job_id}",
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener execution response")


@router.get("/stock-screener/results/{result_id}")
async def stock_screener_result(
    result_id: str,
    view: str | None = Query(default=None),
) -> dict:
    params = {"view": view} if view else None
    data = await _proxy_stock_processing_request_json(
        "GET",
        f"/api/v1/stock-screener/results/{result_id}",
        params=params,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener result response")


@router.get("/stock-screener/history")
async def stock_screener_history(
    strategy_id: str | None = Query(default=None),
    trade_date_from: str | None = Query(default=None),
    trade_date_to: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    params = {
        "strategy_id": strategy_id,
        "trade_date_from": trade_date_from,
        "trade_date_to": trade_date_to,
        "stock_id": stock_id,
        "min_score": min_score,
        "limit": limit,
        "offset": offset,
    }
    data = await _proxy_stock_processing_request_json("GET", "/api/v1/stock-screener/history", params=params)
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener history response")


@router.get("/stock-screener/favorites")
async def stock_screener_favorites(user_id: str = Query(default="default")) -> list:
    data = await _proxy_stock_processing_request_json(
        "GET",
        "/api/v1/stock-screener/favorites",
        params={"user_id": user_id},
    )
    if isinstance(data, list):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener favorites response")


@router.post("/stock-screener/favorites")
async def stock_screener_add_favorite(payload: dict, user_id: str = Query(default="default")) -> dict:
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/stock-screener/favorites",
        params={"user_id": user_id},
        payload=payload,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener add-favorite response")


@router.put("/stock-screener/favorites/{favorite_id}")
async def stock_screener_update_favorite(favorite_id: str, payload: dict) -> dict:
    data = await _proxy_stock_processing_request_json(
        "PUT",
        f"/api/v1/stock-screener/favorites/{favorite_id}",
        payload=payload,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener update-favorite response")


@router.delete("/stock-screener/favorites/{favorite_id}")
async def stock_screener_delete_favorite(favorite_id: str) -> dict:
    data = await _proxy_stock_processing_request_json(
        "DELETE",
        f"/api/v1/stock-screener/favorites/{favorite_id}",
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener delete-favorite response")


@router.get("/stock-screener/statistics")
async def stock_screener_statistics(
    strategy_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict:
    params = {"strategy_id": strategy_id, "from": from_date, "to": to_date}
    data = await _proxy_stock_processing_request_json("GET", "/api/v1/stock-screener/statistics", params=params)
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener statistics response")


@router.post("/stock-screener/export")
async def stock_screener_export(payload: dict) -> dict:
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/stock-screener/export",
        payload=payload,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid stock-screener export response")


@router.get("/collection/availability")
async def collection_availability(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
) -> dict:
    try:
        payload = await _proxy_stock_processing_json(
            "/api/v1/collection/availability",
            {"trade_date": trade_date or ""},
        )
    except Exception as exc:
        return {
            "allowed": False,
            "server_time": "",
            "message": "采集窗口状态获取失败，请检查上游服务",
            "diagnostics": {
                "code": "WEB_APP_UPSTREAM_UNREACHABLE",
                "message": str(exc),
                "upstream": f"{STOCK_PROCESSING_BASE_URL}/api/v1/collection/availability",
            },
        }
    return payload


@router.post("/collection/start")
async def collection_start(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/collection/start", payload)


@router.get("/collection/status")
async def collection_status(job_id: str = Query(...)) -> dict:
    try:
        return await _proxy_stock_processing_request_json("GET", "/api/v1/collection/status", params={"job_id": job_id}, timeout=120.0)
    except HTTPException as exc:
        if exc.status_code == 502:
            return {"status": "running", "progress_percent": -1, "tasks": [],
                    "message": "SPS busy, retrying...", "diagnostics": {"code": "BFF_TIMEOUT_WAITING_SPS"}}
        raise


@router.post("/collection/cancel")
async def collection_cancel(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/collection/cancel", payload)


@router.post("/collection/continue")
async def collection_continue(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/collection/continue", payload)


# ── 通用 SPS 代理（替代前端直连 /api/v1/* → :8090）──

@router.get("/pre_market_brief")
async def proxy_pre_market_brief(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict:
    return await _proxy_stock_processing_json("/api/v1/pre_market_brief", {"trade_date": trade_date})


@router.post("/pre_market_brief/publish-notion")
async def proxy_pre_market_brief_publish(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/pre_market_brief/publish-notion", payload)


# ── Phase 6A: Review queue CRUD ──

@router.get("/review-queue/events")
async def proxy_review_queue_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> dict:
    params = {"page": str(page), "page_size": str(page_size)}
    if status:
        params["status"] = status
    if source:
        params["source"] = source
    return await _proxy_stock_processing_json("/api/v1/review-queue/events", params)


@router.get("/review-queue/events/{review_id}")
async def proxy_review_queue_detail(review_id: int) -> dict:
    return await _proxy_stock_processing_json(f"/api/v1/review-queue/events/{review_id}", {})


@router.post("/review-queue/events/{review_id}/confirm")
async def proxy_review_queue_confirm(review_id: int, payload: dict | None = None) -> dict:
    return await _proxy_stock_processing_post_json(f"/api/v1/review-queue/events/{review_id}/confirm", payload or {})


@router.delete("/review-queue/events/{review_id}")
async def proxy_review_queue_delete(review_id: int) -> dict:
    return await _proxy_stock_processing_request_json(
        "DELETE", f"/api/v1/review-queue/events/{review_id}",
    )


@router.post("/review-queue/events/batch-delete")
async def proxy_review_queue_batch_delete(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/review-queue/events/batch-delete", payload)


@router.post("/review-queue/clear-pending")
async def proxy_review_queue_clear_pending() -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/review-queue/clear-pending", {})


@router.post("/review-queue/import-pending")
async def proxy_review_queue_import_pending() -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/review-queue/import-pending", {})


# ── PR-12.5: Mainline Review Proxy Routes ──

@router.get("/mainline-review/queue")
async def proxy_mainline_review_queue(
    trade_date: str | None = None, status: str | None = None, limit: int = 200,
) -> dict:
    params = {}
    if trade_date: params["trade_date"] = trade_date
    if status: params["status"] = status
    params["limit"] = str(limit)
    return await _proxy_stock_processing_json("/api/v2/mainline-review/queue", params)


@router.get("/mainline-review/registry")
async def proxy_mainline_review_registry(trade_date: str | None = None, limit: int = 100) -> dict:
    params = {}
    if trade_date: params["trade_date"] = trade_date
    params["limit"] = str(limit)
    return await _proxy_stock_processing_json("/api/v2/mainline-review/registry", params)


@router.post("/mainline-review/import-candidates")
async def proxy_mainline_import_candidates(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v2/mainline-review/import-candidates", payload, timeout=60.0)


@router.post("/mainline-review/{review_id}/decision")
async def proxy_mainline_review_decision(review_id: str, payload: dict) -> dict:
    return await _proxy_stock_processing_post_json(
        f"/api/v2/mainline-review/{review_id}/decision", payload, timeout=15.0)


# ── PR-13D: 指数采集代理 ──

@router.post("/index-kline/collect")
async def proxy_index_kline_collect(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json(
        "/api/v1/index-kline/collect", payload, timeout=120.0)


@router.get("/index-kline/status")
async def proxy_index_kline_status(trade_date: str = "") -> dict:
    return await _proxy_stock_processing_json(
        "/api/v1/index-kline/status", {"trade_date": trade_date})


@router.get("/index-technical/daily")
async def proxy_index_technical_daily(trade_date: str = "") -> list[dict]:
    return await _proxy_stock_processing_json(
        "/api/v1/index-technical/daily", {"trade_date": trade_date})


@router.get("/realtime/jyhf-cdp/status")
async def jyhf_cdp_collector_status(request: Request):
    manager = request.app.state.cdp_manager
    result = await manager.get_status()
    # BFF fingerprint — shows which BFF instance served this response
    result["bff_pid"] = os.getpid()
    result["bff_port"] = int(os.getenv("WEB_PORT", "8000"))
    result["manager_id"] = id(manager)
    logger.warning(
        "JYHF_STATUS_RESULT host=%s client=%s web_pid=%s manager_id=%s sr=%s owner=%s cr=%s cdc=%s cap=%s",
        request.headers.get("host"), request.client, os.getpid(), id(manager),
        result.get("service_running"), result.get("service_owner"),
        result.get("collector_running"), result.get("cdp_connected"),
        str(result.get("last_capture_at", "-"))[:30] if result.get("last_capture_at") else "-",
    )
    return JSONResponse(content=result, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@router.post("/realtime/jyhf-cdp/start")
async def jyhf_cdp_collector_start(request: Request, payload: dict | None = None) -> dict:
    manager = request.app.state.cdp_manager
    logger.warning(
        "JYHF_START_REQUEST host=%s client=%s web_pid=%s manager_id=%s port=%s",
        request.headers.get("host"), request.client, os.getpid(), id(manager),
        getattr(manager, "_port", "?"),
    )
    result = await manager.start_collector(payload or {})
    logger.warning(
        "JYHF_START_RESULT ok=%s sr=%s owner=%s cr=%s cdc=%s cap=%s",
        result.get("ok"), result.get("service_running"), result.get("service_owner"),
        result.get("collector_running"), result.get("cdp_connected"),
        str(result.get("last_capture_at", "-"))[:30] if result.get("last_capture_at") else "-",
    )
    return result


@router.get("/debug/local-httpx-8095")
async def debug_local_httpx_8095(request: Request) -> dict:
    """临时诊断：复现 BFF→127.0.0.1:8095 的 HTTP 连通性"""
    import socket as _socket
    import httpx as _httpx

    manager = request.app.state.cdp_manager
    bff_pid = os.getpid()
    manager_id = id(manager)
    target = "http://127.0.0.1:8095/status"

    # 1. port pid
    port_pid = await asyncio.to_thread(manager._find_pid_by_port_blocking)

    # 2. env vars
    proxy_vars = {}
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        proxy_vars[v] = os.environ.get(v, "")

    # 3. httpx trust_env=True
    httpx_trust_true_result = {"ok": False, "error": ""}
    try:
        async with _httpx.AsyncClient(timeout=10.0, trust_env=True) as c:
            r = await c.get(target)
            d = r.json() if isinstance(r.json(), dict) else {}
            httpx_trust_true_result = {
                "ok": True,
                "status_code": r.status_code,
                "cdp_connected": d.get("cdp_connected"),
            }
    except Exception as exc:
        httpx_trust_true_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # 4. httpx trust_env=False
    httpx_trust_false_result = {"ok": False, "error": ""}
    try:
        async with _httpx.AsyncClient(timeout=10.0, trust_env=False) as c:
            r = await c.get(target)
            d = r.json() if isinstance(r.json(), dict) else {}
            httpx_trust_false_result = {
                "ok": True,
                "status_code": r.status_code,
                "cdp_connected": d.get("cdp_connected"),
            }
    except Exception as exc:
        httpx_trust_false_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # 5. raw socket
    socket_result = {"ok": False, "error": ""}
    try:
        sock = _socket.create_connection(("127.0.0.1", 8095), timeout=3)
        socket_result = {"ok": True, "peer": sock.getpeername()}
        sock.close()
    except Exception as exc:
        socket_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # 6. get_status for comparison
    status = await manager.get_status()

    return {
        "bff_pid": bff_pid,
        "manager_id": manager_id,
        "port_pid": port_pid,
        "target": target,
        "env_proxy": proxy_vars,
        "httpx_trust_env_true": httpx_trust_true_result,
        "httpx_trust_env_false": httpx_trust_false_result,
        "socket_connect": socket_result,
        "get_status": {
            "service_running": status.get("service_running"),
            "http_alive": status.get("http_alive"),
            "http_error": status.get("http_error"),
            "popen_alive": status.get("popen_alive"),
        },
        "verdict": "PROXY_BUG" if (not httpx_trust_true_result["ok"] and httpx_trust_false_result["ok"])
                   else "NETWORK_BUG" if (not socket_result["ok"])
                   else "LOGIC_BUG" if (httpx_trust_false_result["ok"] and not status.get("http_alive"))
                   else "ALL_OK",
    }


@router.post("/realtime/jyhf-cdp/stop")
async def jyhf_cdp_collector_stop(request: Request, payload: dict | None = None) -> dict:
    manager = request.app.state.cdp_manager
    stop_service = bool((payload or {}).get("stop_service", True))
    return await manager.stop_collector(stop_service=stop_service)


@router.get("/realtime/jyhf-cdp/logs")
async def jyhf_cdp_collector_logs(request: Request, lines: int = Query(default=300, ge=20, le=2000)) -> dict:
    manager = request.app.state.cdp_manager
    return await manager.get_logs(lines=lines)


@router.post("/realtime/jyhf-cdp/service/stop")
async def jyhf_cdp_service_stop(request: Request) -> dict:
    manager = request.app.state.cdp_manager
    return await manager.stop_service()


# ── P2-B-4: JYHF 竞价采集 ──

@router.get("/realtime/jyhf-auction/status")
async def jyhf_auction_status(request: Request) -> dict:
    mgr = request.app.state.auction_manager
    return mgr.status()


@router.get("/realtime/jyhf-auction/logs")
async def jyhf_auction_logs(request: Request, lines: int = Query(default=200, ge=20, le=2000)) -> dict:
    mgr = request.app.state.auction_manager
    return mgr.get_logs(lines=lines)


@router.post("/realtime/jyhf-auction/start")
async def jyhf_auction_start(request: Request, payload: dict | None = None) -> dict:
    mgr = request.app.state.auction_manager
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    trade_date = (payload or {}).get("trade_date", str(now.date()))
    # candidate_date 默认用今天，采集器内部会自动取 DB 最新候选（处理周末/节假日）
    candidate_date = (payload or {}).get("candidate_date", str(now.date()))
    return await mgr.start(trade_date, candidate_date)


@router.post("/realtime/jyhf-auction/stop")
async def jyhf_auction_stop(request: Request) -> dict:
    mgr = request.app.state.auction_manager
    return await mgr.stop()


# ── P0-C2: 统一状态聚合接口，替代多个独立轮询 ──

# new-chain 状态缓存：SPS 8090 频繁超时导致 status-bundle 被拖死时兜底
_new_chain_cache: dict = {
    "data": None,        # 最近一次成功的 SPS 响应
    "ts": 0.0,           # 成功时间戳
    "max_age_s": 60,     # 缓存有效期
    "failures": 0,       # 连续失败次数
    "circuit_open_until": 0.0,  # 熔断结束时间（跳过 SPS 调用）
}


@router.get("/realtime/status-bundle")
async def realtime_status_bundle(request: Request) -> dict:
    """单次返回 new-chain + JYHF CDP + auction 状态，减少轮询次数。"""
    import asyncio as _asyncio
    import time as _time

    async def _new_chain():
        now_ts = _time.time()

        # 熔断：连续失败 2 次后跳过 SPS 调用 30s，避免每次 4s 超时拖死 bundle
        if _new_chain_cache["failures"] >= 2 and now_ts < _new_chain_cache["circuit_open_until"]:
            cached = _new_chain_cache["data"]
            if cached:
                cached = dict(cached)
                cached["_cached"] = True
                cached["_circuit_open"] = True
                cached["_cache_age_s"] = round(now_ts - _new_chain_cache["ts"], 1)
                return cached
            return {"running": False, "error": "circuit open — SPS unreachable", "_circuit_open": True}

        try:
            async with httpx.AsyncClient(timeout=4.0, trust_env=False) as c:
                r = await c.get(f"{STOCK_PROCESSING_BASE_URL}/api/v1/realtime/status")
                r.raise_for_status()
                data = r.json()
                _new_chain_cache["data"] = data
                _new_chain_cache["ts"] = now_ts
                _new_chain_cache["failures"] = 0
                _new_chain_cache["circuit_open_until"] = 0.0
                return data
        except Exception as exc:
            _new_chain_cache["failures"] += 1
            if _new_chain_cache["failures"] >= 2:
                _new_chain_cache["circuit_open_until"] = now_ts + 30  # 熔断 30s
            # 缓存兜底：SPS 不可达时返回最后已知状态
            cached = _new_chain_cache["data"]
            if cached and (now_ts - _new_chain_cache["ts"]) < _new_chain_cache["max_age_s"]:
                cached = dict(cached)
                cached["_cached"] = True
                cached["_cache_age_s"] = round(now_ts - _new_chain_cache["ts"], 1)
                return cached
            return {"running": False, "error": str(exc)}

    async def _cdp_status():
        try:
            return await request.app.state.cdp_manager.get_status()
        except Exception as exc:
            return {"error": str(exc)}

    async def _auction_status():
        return request.app.state.auction_manager.status()

    try:
        async with _asyncio.timeout(7.0):
            new_chain, cdp, auction = await _asyncio.gather(
                _new_chain(), _cdp_status(), _auction_status(),
                return_exceptions=True,
            )
    except TimeoutError:
        # 整体超时：返回缓存或降级响应
        cached = _new_chain_cache["data"]
        new_chain = (dict(cached) if cached else {"running": False, "error": "bundle timeout"}) if cached else {"running": False, "error": "bundle timeout"}
        cdp = {"error": "bundle timeout"}
        auction = request.app.state.auction_manager.status()

    return {
        "new_chain": new_chain if isinstance(new_chain, dict) else {"error": str(new_chain)},
        "jyhf_cdp": cdp if isinstance(cdp, dict) else {"error": str(cdp)},
        "jyhf_auction": auction if isinstance(auction, dict) else {"error": str(auction)},
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    }


@router.post("/realtime/jyhf-cdp/service/force-stop")
async def jyhf_cdp_service_force_stop(request: Request) -> dict:
    """诊断接口：强杀 8095 端口上的进程（不限 owner），用于清理旧残留。"""
    manager = request.app.state.cdp_manager
    return await manager.force_stop_service()


# ── Realtime Collector ──


# legacy compatibility only; frontend must use /collector/*
@router.get("/realtime/new-chain/status")
async def realtime_new_chain_status() -> dict:
    data = await _proxy_stock_processing_request_json(
        "GET",
        "/api/v1/realtime/status",
        timeout=15.0,
    )
    result = data if isinstance(data, dict) else {"running": False, "last_error": "invalid SPS realtime status response"}
    result["deprecated"] = True
    result["use"] = "/api/v2/realtime/collector/status"
    return result


# legacy compatibility only; frontend must use /collector/*
@router.post("/realtime/new-chain/start")
async def realtime_new_chain_start() -> dict:
    data = await _proxy_stock_processing_request_json(
        "GET",
        "/api/v1/realtime/start",
        timeout=60.0,
    )
    result = data if isinstance(data, dict) else {"ok": False, "status": "invalid_response"}
    result["deprecated"] = True
    result["use"] = "/api/v2/realtime/collector/start"
    return result


# legacy compatibility only; frontend must use /collector/*
@router.post("/realtime/new-chain/stop")
async def realtime_new_chain_stop(request: Request) -> dict:
    """LEGACY: 直接通过 pidfile 停止实时采集子进程，不依赖 SPS。

    实时子进程生命周期已收口到 SPS，BFF 不再自己管理。
    frontend must use /api/v2/realtime/collector/stop.
    """
    manager = request.app.state.realtime_stack_manager
    # 降级为 SPS /realtime/stop 代理，不再自行 stop_pipeline
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            r = await client.get(f"{STOCK_PROCESSING_BASE_URL}/api/v1/realtime/stop")
            data = r.json()
    except Exception as exc:
        data = {"ok": False, "status": "error", "error": str(exc)}
    data["deprecated"] = True
    data["use"] = "/api/v2/realtime/collector/stop"
    return data


@router.get("/realtime/collector/status")
async def realtime_collector_status(request: Request) -> dict:
    manager = request.app.state.realtime_stack_manager
    return await manager.status()


@router.post("/realtime/collector/start")
async def realtime_collector_start(request: Request, payload: dict | None = None) -> dict:
    manager = request.app.state.realtime_stack_manager
    return await manager.start(payload or {})


@router.post("/realtime/collector/stop")
async def realtime_collector_stop(request: Request, payload: dict | None = None) -> dict:
    manager = request.app.state.realtime_stack_manager
    return await manager.stop(payload or {})


@router.get("/realtime/collector/logs")
async def realtime_collector_logs(
    request: Request,
    lines: int = Query(default=200, ge=20, le=2000),
    max_age_minutes: int = Query(default=180, ge=10, le=1440),
) -> dict:
    manager = request.app.state.realtime_stack_manager
    return await manager.logs(lines=lines, max_age_minutes=max_age_minutes)


# ── P4-2A: Realtime Business Orchestrator（只读状态 + dry_run tick）──


@router.get("/realtime/orchestrator/status")
async def orchestrator_status(request: Request, now: str | None = Query(default=None)) -> dict:
    """返回 orchestrator 当前状态：交易阶段、各服务 readiness、blockers。

    只读，不启动/停止任何服务。

    Query params:
        now: ISO datetime override for simulating trading phases (dev only).
             e.g. ?now=2026-05-29T09:11:00+08:00 or ?now=09:11
    """
    orch = request.app.state.realtime_business_orchestrator
    try:
        async with asyncio.timeout(8.0):
            status = await orch.get_status(now_override=now)
            return _orchestrator_status_to_dict(status)
    except Exception as exc:
        return _orchestrator_fallback(f"status timeout: {exc}")


@router.post("/realtime/orchestrator/tick")
async def orchestrator_tick(request: Request, payload: dict | None = None) -> dict:
    """触发一次诊断 tick。

    dry_run=true（默认）：只输出 planned_actions，不执行 start/stop。

    Body:
        {"dry_run": true, "now_override": "2026-05-29T09:11:00+08:00"}
    """
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", True))
    now_override = payload.get("now_override")
    orch = request.app.state.realtime_business_orchestrator
    try:
        async with asyncio.timeout(8.0):
            status = await orch.tick(dry_run=dry_run, now_override=now_override)
            return _orchestrator_status_to_dict(status)
    except Exception as exc:
        return _orchestrator_fallback(f"tick timeout: {exc}")


def _orchestrator_fallback(error: str) -> dict:
    """Return a safe fallback when orchestrator is unreachable."""
    return {
        "enabled": False,
        "actions_enabled": False,
        "dry_run": True,
        "dry_run_forced": False,
        "dry_run_forced_reason": "",
        "now_override": None,
        "trade_date": "",
        "phase": "orchestrator_unavailable",
        "phase_label": "编排器不可用",
        "now_cn": "",
        "tick_seq": 0,
        "is_trade_day": False,
        "services": {},
        "planned_actions": [],
        "executed_actions": [],
        "global_blockers": [error],
        "tick_duration_ms": 0,
        "error": error,
    }


def _orchestrator_status_to_dict(status) -> dict:
    """Serialize OrchestratorStatus to JSON-safe dict."""
    def _svc_to_dict(svc) -> dict:
        return {
            "name": svc.name,
            "enabled": svc.enabled,
            "desired_state": svc.desired_state,
            "observed_state": svc.observed_state,
            "owner": svc.owner,
            "dependencies": svc.dependencies,
            "blockers": svc.blockers,
            "evidence": svc.evidence,
            "last_action": svc.last_action,
            "last_error": svc.last_error,
            "next_retry_at": svc.next_retry_at,
        }

    return {
        "enabled": status.enabled,
        "actions_enabled": status.actions_enabled,
        "dry_run": status.dry_run,
        "dry_run_forced": status.dry_run_forced,
        "dry_run_forced_reason": status.dry_run_forced_reason,
        "now_override": status.now_override,
        "trade_date": status.trade_date,
        "phase": status.phase,
        "phase_label": status.phase_label,
        "now_cn": status.now_cn,
        "tick_seq": status.tick_seq,
        "is_trade_day": status.is_trade_day,
        "services": {k: _svc_to_dict(v) for k, v in status.services.items()},
        "planned_actions": status.planned_actions,
        "executed_actions": status.executed_actions,
        "global_blockers": status.global_blockers,
        "runtime_dependencies": status.runtime_dependencies,
        "tick_duration_ms": status.tick_duration_ms,
    }


# ── P4-2C: Orchestrator enable/disable/reset/audit ──


@router.post("/realtime/orchestrator/enable")
async def orchestrator_enable(request: Request, payload: dict | None = None) -> dict:
    """启用自动编排 tick loop。

    Body: {"actions_enabled": false}
      - actions_enabled=false: 只自动诊断，不执行 start/stop
      - actions_enabled=true:  诊断 + 执行白名单动作
    """
    payload = payload or {}
    actions_enabled = bool(payload.get("actions_enabled", False))
    orch = request.app.state.realtime_business_orchestrator
    return await orch.enable(actions_enabled=actions_enabled)


@router.post("/realtime/orchestrator/disable")
async def orchestrator_disable(request: Request) -> dict:
    """禁用自动编排 tick loop。"""
    orch = request.app.state.realtime_business_orchestrator
    return await orch.disable()


@router.post("/realtime/orchestrator/reset-action-history")
async def orchestrator_reset_actions(request: Request) -> dict:
    """重置 action history / retry state / circuit breaker（调试用）。"""
    orch = request.app.state.realtime_business_orchestrator
    return await orch.reset_action_history()


@router.get("/realtime/orchestrator/audit")
async def orchestrator_audit(request: Request, limit: int = 50) -> list[dict]:
    """查看近期 audit log。"""
    orch = request.app.state.realtime_business_orchestrator
    return await orch.get_audit_log(limit=limit)


# ── P4-2G: Database Health & Data Freshness Diagnostics ──


_DB_HEALTH_WATCH_TABLES = [
    ("news_raw", "created_at"),
    ("event_review_queue", "created_at"),
    ("jyhf_market_raw_capture", "captured_at"),
]
_DB_FRESHNESS_WARN_SEC = int(os.getenv("DB_FRESHNESS_WARN_SEC", "1800"))
_DB_FRESHNESS_BLOCK_SEC = int(os.getenv("DB_FRESHNESS_BLOCK_SEC", "7200"))


async def _db_health_snapshot() -> dict:
    """只读数据库运行态诊断。不允许 COUNT(*)/写入/长事务。"""
    import asyncpg
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    TZ_CN = _tz(_td(hours=8))
    checked_at = _dt.now(TZ_CN).isoformat()
    blockers: list[str] = []
    db_state = "unknown"

    write_db = os.getenv("PG_DATABASE") or os.getenv("POSTGRES_DATABASE") or "stock_data_test"
    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = int(os.getenv("PG_PORT", "5432"))
    pg_user = os.getenv("PG_USERNAME", "postgres")
    pg_pass = os.getenv("PG_PASSWORD", "")
    same_db = True
    read_db = write_db

    # ── 1. Connection check ──
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=pg_host, port=pg_port, database=write_db,
                user=pg_user, password=pg_pass,
                timeout=3, command_timeout=2,
            ),
            timeout=3.0,
        )
        t0 = time.time()
        await conn.execute("SELECT 1")
        latency_ms = int((time.time() - t0) * 1000)
        db_state = "ready" if latency_ms <= 100 else ("degraded" if latency_ms <= 500 else "blocked")
        if latency_ms > 100:
            blockers.append(f"db latency elevated: {latency_ms}ms")
    except Exception as exc:
        return {
            "ok": False, "state": "blocked", "db_state": "blocked",
            "checked_at": checked_at, "latency_ms": None,
            "write_db": write_db, "read_db": read_db, "same_db": same_db,
            "blockers": [f"database connect failed: {exc}"],
            "server": {}, "tables": {},
        }

    try:
        # ── 2. Server info ──
        server_info: dict[str, Any] = {}
        pool_state = "ready"
        lock_state = "ready"

        try:
            row = await conn.fetchrow("SELECT version()")
            server_info["version"] = row[0] if row else "?"
        except Exception:
            server_info["version"] = "?"
        server_info["current_database"] = write_db
        server_info["current_user"] = pg_user

        # Connection counts
        try:
            row = await conn.fetchrow(
                "SELECT count(*) AS total, count(*) FILTER (WHERE state='active') AS active, "
                "count(*) FILTER (WHERE state='idle') AS idle, "
                "count(*) FILTER (WHERE state='idle in transaction') AS idle_in_tx, "
                "count(*) FILTER (WHERE wait_event IS NOT NULL) AS waiting "
                "FROM pg_stat_activity WHERE datname=current_database()"
            )
            server_info["active_connections"] = row["active"] if row else 0
            server_info["idle_connections"] = row["idle"] if row else 0
            server_info["idle_in_transaction"] = row["idle_in_tx"] if row else 0
            server_info["waiting_queries"] = row["waiting"] if row else 0
            if row and row["idle_in_tx"] and row["idle_in_tx"] > 0:
                pool_state = "degraded"
                blockers.append(f"idle in transaction: {row['idle_in_tx']}")
            if row and row["waiting"] and row["waiting"] > 0:
                lock_state = "degraded"
                blockers.append(f"waiting queries: {row['waiting']}")
        except Exception as exc:
            blockers.append(f"pg_stat_activity failed: {exc}")

        # Waiting query samples (top 5)
        waiting_samples: list[dict] = []
        try:
            rows = await conn.fetch(
                "SELECT pid, usename, application_name, state, wait_event_type, wait_event, "
                "now()-query_start AS query_age, left(query, 200) AS query "
                "FROM pg_stat_activity "
                "WHERE wait_event IS NOT NULL AND datname=current_database() "
                "ORDER BY query_start NULLS LAST LIMIT 5"
            )
            for r in rows:
                waiting_samples.append({
                    "pid": r["pid"],
                    "user": r["usename"],
                    "app": r["application_name"],
                    "state": r["state"],
                    "wait_type": r["wait_event_type"],
                    "wait_event": r["wait_event"],
                    "query_age": str(r["query_age"]) if r["query_age"] else None,
                    "query": r["query"],
                })
        except Exception:
            pass
            blockers.append(f"pg_stat_activity failed: {exc}")

        # Max connections
        try:
            row = await conn.fetchrow("SHOW max_connections")
            server_info["max_connections"] = int(row[0]) if row else 0
        except Exception:
            server_info["max_connections"] = 0

        # ── 3. Lock waits ──
        try:
            row = await conn.fetchrow("SELECT count(*) AS n FROM pg_locks WHERE NOT granted")
            waiting_locks = row["n"] if row else 0
            server_info["waiting_locks"] = waiting_locks
            if waiting_locks >= 10:
                lock_state = "blocked"
                blockers.append(f"lock waits critical: {waiting_locks}")
            elif waiting_locks > 0:
                lock_state = "degraded"
                blockers.append(f"lock waits: {waiting_locks}")
        except Exception as exc:
            blockers.append(f"pg_locks check failed: {exc}")
            server_info["waiting_locks"] = -1

        # ── 4. Table checks ──
        tables: dict[str, dict] = {}
        schema_state = "ready"
        freshness_state = "ready"

        for table_name, time_col in _DB_HEALTH_WATCH_TABLES:
            t_state = "ready"
            t_blockers: list[str] = []
            try:
                exists_row = await conn.fetchrow(
                    "SELECT to_regclass($1)::text", f"public.{table_name}"
                )
                exists = bool(exists_row and exists_row[0])
                if not exists:
                    schema_state = "degraded"
                    t_state = "blocked"
                    t_blockers.append(f"table {table_name} does not exist")
                    tables[table_name] = {"exists": False, "state": t_state, "blockers": t_blockers}
                    continue

                # Row estimate
                try:
                    est = await conn.fetchrow(
                        "SELECT reltuples::bigint FROM pg_class WHERE oid=$1::regclass",
                        f"public.{table_name}",
                    )
                    estimated_rows = est[0] if est else 0
                except Exception:
                    estimated_rows = -1

                # Latest row timestamp
                latest_at = None
                age_sec = None
                try:
                    ts_row = await conn.fetchrow(
                        f'SELECT "{time_col}" FROM "{table_name}" ORDER BY "{time_col}" DESC LIMIT 1'
                    )
                    if ts_row and ts_row[0]:
                        latest_at = ts_row[0].isoformat() if hasattr(ts_row[0], "isoformat") else str(ts_row[0])
                        age_sec = int((_dt.now(TZ_CN) - ts_row[0]).total_seconds())
                except Exception:
                    pass

                if age_sec is not None:
                    if age_sec > _DB_FRESHNESS_BLOCK_SEC:
                        t_state = "blocked"
                        t_blockers.append(f"data stale: {age_sec}s old (block>{_DB_FRESHNESS_BLOCK_SEC}s)")
                        if freshness_state != "blocked":
                            freshness_state = "degraded"
                    elif age_sec > _DB_FRESHNESS_WARN_SEC:
                        t_state = "degraded"
                        t_blockers.append(f"data stale: {age_sec}s old (warn>{_DB_FRESHNESS_WARN_SEC}s)")
                        if freshness_state == "ready":
                            freshness_state = "degraded"

                tables[table_name] = {
                    "exists": True,
                    "estimated_rows": estimated_rows,
                    "latest_at": latest_at,
                    "age_sec": age_sec,
                    "state": t_state,
                    "blockers": t_blockers,
                }
            except Exception as exc:
                tables[table_name] = {"exists": False, "state": "blocked", "blockers": [str(exc)]}
                if schema_state == "ready":
                    schema_state = "degraded"

        # Aggregate overall
        overall = db_state
        for s in [pool_state, schema_state, freshness_state, lock_state]:
            if s == "blocked":
                overall = "blocked"
                break
            elif s == "degraded" and overall != "blocked":
                overall = "degraded"

        return {
            "ok": True,
            "state": overall,
            "db_state": db_state,
            "pool_state": pool_state,
            "schema_state": schema_state,
            "freshness_state": freshness_state,
            "lock_state": lock_state,
            "checked_at": checked_at,
            "latency_ms": latency_ms,
            "write_db": write_db,
            "read_db": read_db,
            "same_db": same_db,
            "server": server_info,
            "tables": tables,
            "waiting_samples": waiting_samples,
            "blockers": blockers,
        }
    finally:
        try:
            await conn.close()
        except Exception:
            pass


@router.get("/runtime/db-health")
async def runtime_db_health():
    """数据库运行态健康诊断。

    只读，短超时，不 COUNT(*)，不写数据。"""
    try:
        async with asyncio.timeout(2.0):
            return await _db_health_snapshot()
    except Exception as exc:
        return {
            "ok": False, "state": "blocked", "db_state": "blocked",
            "checked_at": "", "latency_ms": None,
            "write_db": os.getenv("PG_DATABASE", "stock_data_test"),
            "read_db": os.getenv("PG_DATABASE", "stock_data_test"),
            "same_db": True,
            "blockers": [f"db health timeout: {exc}"],
            "server": {}, "tables": {},
        }


# ── P4-2G end ──


@router.get("/intel/feed")
async def intel_feed(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    type: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    data = await client.get_intel_feed(
        date=date,
        session=session,
        item_type=type,
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )
    if isinstance(data, dict):
        # Phase 4E: 过滤 cninfo_announcement（公告/研报走独立 intel 管线，不混入新闻事件流）
        items = [i for i in (data.get("items") or []) if i.get("source_channel") != "cninfo_announcement"]
        data["items"] = items
        data["count"] = len(items)
    return data if isinstance(data, dict) else {"items": [], "count": 0, "diagnostics": {"partial": True}}


@router.get("/intel/feed/defaults")
async def intel_feed_defaults() -> dict:
    """返回情报台最近有数据的日期。"""
    try:
        data = await _proxy_stock_processing_json("/api/v1/intel_feed/defaults", {})
        return data if isinstance(data, dict) else {"latest_intel_date": None}
    except Exception:
        return {"latest_intel_date": None}


@router.get("/intel/strong-stocks/watch")
@router.get("/strong_watch/watch")
async def intel_strong_stocks_watch(
    date: str | None = Query(default=None),
    window_days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=1000, ge=1, le=5000),
    latest_per_stock: bool = Query(default=False),
    include_removed: bool = Query(default=False),
    stock_id: str | None = Query(default=None),
) -> dict:
    trade_date = date or ""
    payload = (
        await client.get_strong_watch(
            trade_date,
            window_days=window_days,
            include_removed=include_removed,
            latest_per_stock=latest_per_stock,
            stock_id=stock_id,
            limit=limit,
        )
    ).model_dump()
    stocks = list(payload.get("stocks") or [])
    trade_dates = sorted({str(row.get("trade_date") or "") for row in stocks if str(row.get("trade_date") or "").strip()})
    date_from = trade_dates[0] if trade_dates else trade_date
    date_to = trade_dates[-1] if trade_dates else trade_date
    return {
        "date_from": date_from,
        "date_to": date_to,
        "window_days": window_days,
        "latest_per_stock": latest_per_stock,
        "include_removed": include_removed,
        "count": len(stocks),
        "items": stocks,
        "diagnostics": {
            "partial": False,
            "source": "stock_processing_read_api",
            "mode": "windowed_history",
        },
    }

# ── workspace 端点缓存：SPS 慢时避免重复阻塞，30s TTL ──
_workspace_cache: dict[str, dict] = {}  # key -> {"data": ..., "ts": float}


def _ws_cache_get(key: str, ttl: float = 30.0) -> dict | None:
    import time as _time
    entry = _workspace_cache.get(key)
    if entry and (_time.time() - entry["ts"]) < ttl:
        cached = dict(entry["data"])
        cached["_cached"] = True
        cached["_cache_age_s"] = round(_time.time() - entry["ts"], 1)
        return cached
    return None


def _ws_cache_set(key: str, data: dict) -> None:
    import time as _time
    _workspace_cache[key] = {"data": data, "ts": _time.time()}


@router.get("/workspace/theme-radar")
async def workspace_theme_radar(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict:
    # 缓存命中直接返回，避免 SPS 慢时重复阻塞
    _ck = f"theme_radar:{date}:{session}:{limit}"
    _cached = _ws_cache_get(_ck, ttl=20.0)
    if _cached is not None:
        return _cached

    # 并发获取 intel feed + daily_review
    feed_task = client.get_intel_feed(date=date, session=session, item_type="all", limit=limit)
    dr_task = client.get_json("/api/v1/daily_review", {"trade_date": date}) if date else None

    feed_result, dr_result = await asyncio.gather(
        feed_task,
        dr_task or asyncio.sleep(0),
        return_exceptions=True,
    )
    feed = feed_result if isinstance(feed_result, dict) else {}
    items = [i for i in (feed.get("items") or []) if i.get("source_channel") != "cninfo_announcement"]

    stage_by_subject_key: dict[str, str] = {}
    stage_by_theme_name: dict[str, str] = {}
    stock_count_by_subject_key: dict[str, int] = {}
    stock_count_by_theme_name: dict[str, int] = {}
    daily_review: dict[str, Any] = {}
    if isinstance(dr_result, dict):
        try:
            daily_review = dr_result
            for tr in daily_review.get("theme_reviews") or []:
                sk = str(tr.get("subject_key") or "").strip()
                tn = str(tr.get("theme_name") or "").strip()
                stage = str(tr.get("final_cycle_state") or "")
                sc = len(tr.get("leader_stocks") or [])
                if sk:
                    if _stage_priority(stage) > _stage_priority(stage_by_subject_key.get(sk, "UNKNOWN")):
                        stage_by_subject_key[sk] = stage
                    stock_count_by_subject_key[sk] = max(stock_count_by_subject_key.get(sk, 0), sc)
                if tn:
                    if _stage_priority(stage) > _stage_priority(stage_by_theme_name.get(tn, "UNKNOWN")):
                        stage_by_theme_name[tn] = stage
                    stock_count_by_theme_name[tn] = max(stock_count_by_theme_name.get(tn, 0), sc)
        except Exception:
            pass

    by_theme: dict[str, dict] = {}
    for item in items:
        theme_names = item.get("theme_names") or []
        theme_subject_keys = item.get("theme_subject_keys") or []
        subject_key = str(item.get("subject_key") or "")
        # 用 theme_subject_keys 做桥接匹配 daily-review 的 stage/stock_count
        matched_stage = "UNKNOWN"
        matched_stock_count = 0
        for tsk in theme_subject_keys:
            tsk = str(tsk).strip()
            if tsk and tsk in stage_by_subject_key and matched_stage == "UNKNOWN":
                matched_stage = stage_by_subject_key[tsk]
            if tsk and tsk in stock_count_by_subject_key:
                matched_stock_count = max(matched_stock_count, stock_count_by_subject_key[tsk])
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
                    "_subject_keys": [],
                },
            )
            row["heat"] += 1
            # 累积所有 theme_subject_keys，用于后续回填
            for tsk in theme_subject_keys:
                tsk = str(tsk).strip()
                if tsk and tsk not in row["_subject_keys"]:
                    row["_subject_keys"].append(tsk)
            # stage: theme_subject_keys 桥接 > subject_key > theme_name
            if row["stage"] == "UNKNOWN" and matched_stage != "UNKNOWN":
                row["stage"] = matched_stage
            if row["stage"] == "UNKNOWN" and subject_key:
                row["stage"] = stage_by_subject_key.get(subject_key, "UNKNOWN")
            if row["stage"] == "UNKNOWN":
                row["stage"] = stage_by_theme_name.get(_normalize_theme_name(theme_name), "UNKNOWN")
            # stock_count: theme_subject_keys 桥接 > subject_key > theme_name
            if matched_stock_count > 0:
                row["stock_count"] = max(row["stock_count"], matched_stock_count)
            if subject_key and subject_key in stock_count_by_subject_key:
                row["stock_count"] = max(row["stock_count"], stock_count_by_subject_key[subject_key])
            if row["stock_count"] == 0 and _normalize_theme_name(theme_name) in stock_count_by_theme_name:
                row["stock_count"] = max(row["stock_count"], stock_count_by_theme_name[_normalize_theme_name(theme_name)])
            # 兜底：intel item 自身的 stock_ids
            row["stock_count"] = max(row["stock_count"], len(item.get("stock_ids") or []))
    # 注入 daily-review 中有周期数据但无新闻的主题（heat=0，排在有新闻的主题之后）
    daily_review_sks_seen: set[str] = set()
    for row in by_theme.values():
        if row.get("stage") != "UNKNOWN":
            daily_review_sks_seen.add(str(row.get("theme_id") or ""))
    for tr in (daily_review.get("theme_reviews") or []):
        sk = str(tr.get("subject_key") or "").strip()
        tn = str(tr.get("theme_name") or "").strip()
        if not sk or not tn:
            continue
        if sk in daily_review_sks_seen:
            continue
        by_theme.setdefault(sk, {
            "theme_id": sk,
            "theme_name": tn,
            "heat": 0,
            "stage": str(tr.get("final_cycle_state") or "UNKNOWN"),
            "stock_count": len(tr.get("leader_stocks") or []),
        })

    # 对 stage 仍为 UNKNOWN 的主题，通过 theme_subject_keys 并发查询最近周期状态
    unknown_themes = [t for t in by_theme.values() if t["stage"] == "UNKNOWN"]
    MAX_FALLBACK = 3
    fallback_tasks: list[tuple[str, dict]] = []  # (sk, theme_row)
    seen_sks: set[str] = set()
    for t in unknown_themes:
        if len(fallback_tasks) >= MAX_FALLBACK:
            break
        sks = t.pop("_subject_keys", []) or []
        for sk in sks:
            if len(fallback_tasks) >= MAX_FALLBACK:
                break
            sk = str(sk).strip()
            if not sk or sk in seen_sks:
                continue
            seen_sks.add(sk)
            fallback_tasks.append((sk, t))

    async def _fetch_one(sk: str) -> tuple[str, dict[str, Any]]:
        try:
            tw = await client.get_json(f"/api/v1/theme/workspace/{sk}")
            return (sk, tw)
        except Exception:
            return (sk, {})

    if fallback_tasks:
        results = await asyncio.gather(*[_fetch_one(sk) for sk, _ in fallback_tasks], return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                continue
            sk, tw = result
            t = fallback_tasks[i][1]
            summary = (tw.get("analytics") or {}).get("summary") or {}
            recent_stage = str(summary.get("final_cycle_state") or "")
            if recent_stage and _stage_priority(recent_stage) > _stage_priority(t["stage"]):
                t["stage"] = recent_stage
            ls = (tw.get("analytics") or {}).get("leader_stocks") or []
            if ls:
                t["stock_count"] = max(t["stock_count"], len(ls))

    themes = sorted(by_theme.values(), key=lambda x: (-int(x["heat"]), x["theme_name"]))[:limit]
    result = {
        "date": date,
        "themes": themes,
        "source": "intel_feed_daily_review_merge",
        "diagnostics": dict(feed.get("diagnostics") or {}),
    }
    _ws_cache_set(_ck, result)
    return result


@router.get("/workspace/intel-context")
async def workspace_intel_context(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    _ck = f"intel_ctx:{date}:{session}:{subject_key}:{stock_id}:{limit}"
    _cached = _ws_cache_get(_ck, ttl=20.0)
    if _cached is not None:
        return _cached

    feed = await client.get_intel_feed(
        date=date,
        session=session,
        item_type="all",
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )
    items = [i for i in (feed.get("items") or []) if i.get("source_channel") != "cninfo_announcement"]
    result = {
        "date": date,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "items": items,
        "count": len(items),
        "diagnostics": dict(feed.get("diagnostics") or {}),
        "source": "intel_feed_proxy",
    }
    _ws_cache_set(_ck, result)
    return result


@router.get("/workspace/market-validation")
async def workspace_market_validation(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
) -> dict:
    _ck = f"mkt_val:{trade_date}:{subject_key}:{stock_id}"
    _cached = _ws_cache_get(_ck, ttl=20.0)
    if _cached is not None:
        return _cached

    import asyncio as _asyncio
    sw_task = _asyncio.create_task(client.get_strong_watch(trade_date))
    w2s_task = _asyncio.create_task(client.get_w2s_candidates(trade_date))
    strong_watch_payload = (await sw_task).model_dump()
    w2s_payload = (await w2s_task).model_dump()
    sw_stocks = list(strong_watch_payload.get("stocks") or [])
    w2s_candidates = list(w2s_payload.get("candidates") or [])
    stock_view = None
    if stock_id:
        stock_view = next(
            (row for row in sw_stocks if str(row.get("stock_id") or "") == stock_id),
            None,
        )
    candidate_view = None
    if stock_id:
        candidate_view = next(
            (row for row in w2s_candidates if str(row.get("stock_id") or "") == stock_id),
            None,
        )

    # Prefer stock-specific values; otherwise derive summary-level signal from top candidate.
    top_candidate = w2s_candidates[0] if w2s_candidates else None
    top_watch = sw_stocks[0] if sw_stocks else None
    chosen = candidate_view or top_candidate or stock_view or top_watch or {}
    if w2s_candidates:
        default_level = "observe"
    elif sw_stocks:
        default_level = "observe"
    else:
        default_level = "unknown"
    candidate_level = str(
        chosen.get("candidate_level")
        or chosen.get("transition_type")
        or default_level
    )
    support_type = str(chosen.get("support_type") or "unknown")
    support_score = _to_float_or_none(chosen.get("support_score"))
    reject_reasons = list(chosen.get("reject_reasons") or [])

    # 主题级验证：从 daily-review 或历史数据获取
    theme_validation = None
    if subject_key:
        try:
            daily_review = await client.get_json("/api/v1/daily_review", {"trade_date": trade_date})
            for tr in daily_review.get("theme_reviews") or []:
                if str(tr.get("subject_key") or "") == subject_key:
                    theme_validation = {
                        "theme_name": tr.get("theme_name"),
                        "cycle_stage": tr.get("final_cycle_state"),
                        "mainline_strength": tr.get("mainline_strength_score"),
                        "fade_risk": tr.get("fade_risk_score"),
                        "mainline_alive": tr.get("final_mainline_alive"),
                        "leader_stocks": [
                            {"name": ls.get("stock_name"), "score": ls.get("leader_composite_score"), "pct_chg": ls.get("pct_chg")}
                            for ls in (tr.get("leader_stocks") or [])[:5]
                        ],
                    }
                    break
            if not theme_validation:
                tw = await client.get_json(f"/api/v1/theme/workspace/{subject_key}")
                s = (tw.get("analytics") or {}).get("summary") or {}
                theme_validation = {
                    "theme_name": s.get("theme_name"),
                    "cycle_stage": s.get("final_cycle_state"),
                    "mainline_strength": float(s.get("mainline_strength_score") or 0),
                    "fade_risk": float(s.get("fade_risk_score") or 0),
                    "mainline_alive": s.get("final_mainline_alive"),
                    "leader_stocks": [],
                    "source": "historical",
                }
        except Exception:
            pass

    result = {
        "trade_date": trade_date,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "candidate_level": candidate_level,
        "support_type": support_type,
        "support_score": support_score,
        "reject_reasons": reject_reasons,
        "strong_watch_count": len(sw_stocks),
        "strong_watch_source": "strong_watch_api",
        "w2s_candidate_count": len(w2s_candidates),
        "stock_validation": stock_view,
        "theme_validation": theme_validation,
    }
    if not sw_stocks:
        result["diagnostics"] = {
            "strong_watch_empty": True,
            "strong_watch_source": "strong_watch_api",
            "error_code": "STRONG_WATCH_API_EMPTY",
            "message": "No fallback applied. Check strong_watch API / DB read model.",
        }
    _ws_cache_set(_ck, result)
    return result


@router.get("/intel/stream")
async def intel_stream(
    request: Request,
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    type: str = Query(default="all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> StreamingResponse:
    params = {
        "feed_date": date,
        "session": session,
        "item_type": type,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "limit": str(limit),
    }
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    url = f"{STOCK_PROCESSING_BASE_URL}/api/v1/intel_feed"

    return StreamingResponse(
        _intel_stream_proxy(request, url=url, query=query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── P1-I-1b: W2S 竞价弱转强告警 SSE ──


@router.get("/realtime/w2s-alerts/stream")
async def w2s_alerts_stream(request: Request, last_id: str = Query(default="0-0")) -> StreamingResponse:
    """SSE 代理: W2S 竞价确认告警 → stock_processing_service."""
    url = f"{STOCK_PROCESSING_BASE_URL}/api/v1/w2s-alerts/stream?last_id={last_id}"

    async def _proxy_stream():
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=3600, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as upstream:
                    if upstream.status != 200:
                        yield f"event: error\ndata: {json.dumps({'error': f'upstream returned {upstream.status}'})}\n\n"
                        return
                    async for line in upstream.content:
                        decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                        yield decoded + "\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _proxy_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── P1-H: K线支撑告警 SSE ──


@router.get("/realtime/kline-alerts/stream")
async def kline_alerts_stream(request: Request, last_id: str = Query(default="0-0")) -> StreamingResponse:
    """SSE 代理: K线支撑位告警 → stock_processing_service."""
    url = f"{STOCK_PROCESSING_BASE_URL}/api/v1/kline-alerts/stream?last_id={last_id}"

    async def _proxy_stream():
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=3600, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as upstream:
                    if upstream.status != 200:
                        yield f"event: error\ndata: {json.dumps({'error': f'upstream returned {upstream.status}'})}\n\n"
                        return
                    async for line in upstream.content:
                        decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                        yield decoded + "\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _proxy_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── W2S Backtest Proxy Endpoints ──

@router.post("/backtest/w2s/data-quality")
async def backtest_w2s_data_quality(payload: dict) -> dict:
    """Proxy: Check data quality before W2S backtest."""
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/backtest/w2s/data-quality",
        payload=payload,
        timeout=120.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest data-quality response")


@router.post("/backtest/w2s/build-feature-snapshot")
async def backtest_w2s_build_feature_snapshot(payload: dict) -> dict:
    """Proxy: Build W2S feature snapshots."""
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/backtest/w2s/build-feature-snapshot",
        payload=payload,
        timeout=600.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest build-feature-snapshot response")


@router.post("/backtest/w2s/validate-signals")
async def backtest_w2s_validate_signals(payload: dict) -> dict:
    """Proxy: Validate W2S signals."""
    data = await _proxy_stock_processing_request_json(
        "POST",
        "/api/v1/backtest/w2s/validate-signals",
        payload=payload,
        timeout=600.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest validate-signals response")


@router.get("/backtest/w2s/runs/{run_id}")
async def backtest_w2s_get_run(run_id: str) -> dict:
    """Proxy: Get W2S backtest run metadata."""
    data = await _proxy_stock_processing_request_json(
        "GET",
        f"/api/v1/backtest/w2s/runs/{run_id}",
        timeout=30.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest run response")


@router.get("/backtest/w2s/runs/{run_id}/summary")
async def backtest_w2s_get_run_summary(run_id: str) -> dict:
    """Proxy: Get W2S validation summary."""
    data = await _proxy_stock_processing_request_json(
        "GET",
        f"/api/v1/backtest/w2s/runs/{run_id}/summary",
        timeout=30.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest summary response")


@router.get("/backtest/w2s/runs/{run_id}/signals")
async def backtest_w2s_get_run_signals(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    confirm_level: str | None = Query(default=None),
    confirm_source: str | None = Query(default=None),
    experiment_id: str | None = Query(default=None),
) -> dict:
    """Proxy: Get W2S signal details."""
    params = {
        "limit": limit,
        "offset": offset,
    }
    if confirm_level:
        params["confirm_level"] = confirm_level
    if confirm_source:
        params["confirm_source"] = confirm_source
    if experiment_id:
        params["experiment_id"] = experiment_id

    data = await _proxy_stock_processing_request_json(
        "GET",
        f"/api/v1/backtest/w2s/runs/{run_id}/signals",
        params=params,
        timeout=30.0,
    )
    if isinstance(data, dict):
        return data
    raise HTTPException(status_code=502, detail="invalid backtest signals response")
