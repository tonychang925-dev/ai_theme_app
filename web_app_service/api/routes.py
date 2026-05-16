import asyncio
import json
import logging
import os
from typing import AsyncIterator

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
    normalized = (stage or "UNKNOWN").upper()
    if normalized == "CONFIRMED":
        return 3
    if normalized == "FORMING":
        return 2
    if normalized == "FADE":
        return 1
    return 0


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
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as http:
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, dict) else {}


async def _proxy_stock_processing_post_json(path: str, payload: dict) -> dict:
    url = f"{STOCK_PROCESSING_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as http:
        resp = await http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
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
            detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
        except Exception:
            detail = exc.response.text or str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
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


@router.get("/theme_workspace/{subject_key}")
@router.get("/theme-workspace/{subject_key}")
async def theme_workspace(subject_key: str, request: Request) -> dict:
    params = {k: v for k, v in request.query_params.items()}
    return await _proxy_stock_processing_json(f"/api/v1/theme_workspace/{subject_key}", params)


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
    return await _proxy_stock_processing_json("/api/v1/collection/status", {"job_id": job_id})


@router.post("/collection/cancel")
async def collection_cancel(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/collection/cancel", payload)


@router.post("/collection/continue")
async def collection_continue(payload: dict) -> dict:
    return await _proxy_stock_processing_post_json("/api/v1/collection/continue", payload)


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


@router.post("/realtime/jyhf-cdp/service/force-stop")
async def jyhf_cdp_service_force_stop(request: Request) -> dict:
    """诊断接口：强杀 8095 端口上的进程（不限 owner），用于清理旧残留。"""
    manager = request.app.state.cdp_manager
    return await manager.force_stop_service()


# ── Realtime Collector（新链由 web_app_service 本地管理，不再代理旧 BFF）──


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


@router.get("/workspace/theme-radar")
async def workspace_theme_radar(
    date: str | None = Query(default=None),
    session: str = Query(default="all"),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict:
    feed = await client.get_intel_feed(
        date=date,
        session=session,
        item_type="all",
        limit=limit,
    )
    items = list(feed.get("items") or [])
    # Root-source stage enrichment: use post-market snapshot recap_doc when available.
    stage_by_subject_key: dict[str, str] = {}
    stage_by_theme_name: dict[str, str] = {}
    if date:
        snapshot = (await client.get_post_market_snapshot(str(date))).model_dump()
        payload = dict(snapshot.get("payload") or {})
        recap_doc = dict(payload.get("recap_doc") or {})

        def _collect_stage_rows(rows: list[dict]) -> None:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sk = str(row.get("subject_key") or "").strip()
                sn = _normalize_theme_name(row.get("subject_name") or row.get("theme_name"))
                stage = _normalize_theme_stage(row)
                if sk and _stage_priority(stage) > _stage_priority(stage_by_subject_key.get(sk, "UNKNOWN")):
                    stage_by_subject_key[sk] = stage
                if sn and _stage_priority(stage) > _stage_priority(stage_by_theme_name.get(sn, "UNKNOWN")):
                    stage_by_theme_name[sn] = stage

        _collect_stage_rows(list(recap_doc.get("strong_watch_history") or []))
        _collect_stage_rows(list(recap_doc.get("top_candidates") or []))

    # Secondary source for stage enrichment: strong_watch/w2s snapshots of same trade_date.
    effective_date = str(date or "")
    strong_watch_payload = (await client.get_strong_watch(effective_date)).model_dump() if effective_date else {"stocks": []}
    w2s_payload = (await client.get_w2s_candidates(effective_date)).model_dump() if effective_date else {"candidates": []}
    for row in list(strong_watch_payload.get("stocks") or []):
        sk = str(row.get("subject_key") or "").strip()
        sn = _normalize_theme_name(row.get("subject_name") or row.get("theme_name"))
        if not sk:
            sk = ""
        stage = _normalize_theme_stage(row)
        if sk and _stage_priority(stage) > _stage_priority(stage_by_subject_key.get(sk, "UNKNOWN")):
            stage_by_subject_key[sk] = stage
        if sn and _stage_priority(stage) > _stage_priority(stage_by_theme_name.get(sn, "UNKNOWN")):
            stage_by_theme_name[sn] = stage
    for row in list(w2s_payload.get("candidates") or []):
        sk = str(row.get("subject_key") or "").strip()
        sn = _normalize_theme_name(row.get("subject_name") or row.get("theme_name"))
        if not sk:
            sk = ""
        stage = _normalize_theme_stage(row)
        if sk and _stage_priority(stage) > _stage_priority(stage_by_subject_key.get(sk, "UNKNOWN")):
            stage_by_subject_key[sk] = stage
        if sn and _stage_priority(stage) > _stage_priority(stage_by_theme_name.get(sn, "UNKNOWN")):
            stage_by_theme_name[sn] = stage
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
            stage = _normalize_theme_stage(item)
            if row["stage"] == "UNKNOWN" and stage != "UNKNOWN":
                row["stage"] = stage
            if row["stage"] == "UNKNOWN" and subject_key:
                sw_stage = stage_by_subject_key.get(subject_key, "UNKNOWN")
                if sw_stage != "UNKNOWN":
                    row["stage"] = sw_stage
            if row["stage"] == "UNKNOWN":
                name_stage = stage_by_theme_name.get(_normalize_theme_name(theme_name), "UNKNOWN")
                if name_stage != "UNKNOWN":
                    row["stage"] = name_stage
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
    feed = await client.get_intel_feed(
        date=date,
        session=session,
        item_type="all",
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )
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
    return {
        "trade_date": trade_date,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "candidate_level": candidate_level,
        "support_type": support_type,
        "support_score": support_score,
        "reject_reasons": reject_reasons,
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
        "feed_date": date,
        "session": session,
        "item_type": type,
        "subject_key": subject_key,
        "stock_id": stock_id,
        "limit": str(limit),
    }
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    url = f"{STOCK_PROCESSING_BASE_URL}/api/v1/intel_feed"

    async def _proxy_sse() -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=15.0, trust_env=False) as http:
                resp = await http.get(url, params=query)
                resp.raise_for_status()
                data = resp.json()
            items = list(data.get("items") or []) if isinstance(data, dict) else []
            yield _emit_sse(
                "stream_state",
                {"status": "connected", "source": "stock_processing_read_api", "count": len(items)},
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
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
            yield _emit_sse("heartbeat", {"source": "stock_processing_read_api"})
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

    return StreamingResponse(
        _proxy_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
