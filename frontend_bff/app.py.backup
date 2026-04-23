from contextlib import asynccontextmanager
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from datetime import date, datetime
from typing import Any, Optional, Dict, List
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
import os

from frontend_bff.repositories.bff_repository import FrontendBffRepository
from frontend_bff.services.collection_job_manager import CollectionJobManager
from frontend_bff.realtime_service import realtime_service
from frontend_bff.middleware.security_middleware import setup_security_middleware
from stock_service.config import DEFAULT_CONFIG
from stock_service.stock_screener_models import ScreeningStrategy, UserFavorite
from stock_service.repositories.stock_screener_repository import StockScreenerRepository
from stock_service.services.stock_screener_service import ScreeningConfig, StockScreenerService
from stock_service.services.stock_screener_llm_review_service import StockScreenerLlmReviewService
from stock_service.services.strategy_decision_service import StrategyDecisionService, MarketState
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder
from stock_service.services.weak_to_strong_auction_service import WeakToStrongAuctionService

# 自定义JSON编码器处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

# 设置logger
logger = logging.getLogger(__name__)

# 尝试导入SSE推送服务
try:
    from database_service.streams.services.sse_push_service import (
        SSEPushService,
        create_sse_push_service
    )
    SSE_PUSH_SERVICE_AVAILABLE = True
except ImportError as e:
    SSE_PUSH_SERVICE_AVAILABLE = False
    logger.warning(f"无法导入SSEPushService: {e}")
    # 创建存根类
    class SSEPushService:
        def __init__(self, *args, **kwargs):
            pass
        async def start(self):
            pass
        async def stop(self):
            pass
        async def create_sse_event_generator(self, client_info=None):
            # 返回空的生成器
            async def empty_generator():
                while True:
                    await asyncio.sleep(60)
                    yield "event: heartbeat\ndata: {\"status\":\"service_unavailable\"}\n\n"
            return empty_generator()
        async def get_service_stats(self):
            return {"status": "not_available"}
        def get_config(self):
            return {"status": "not_available"}


bff_repo = FrontendBffRepository()
collection_job_manager = CollectionJobManager()
sse_push_service: Optional[SSEPushService] = None
stock_screener_repo = StockScreenerRepository(DEFAULT_CONFIG)
stock_screener_service = StockScreenerService(stock_screener_repo)
stock_screener_llm_review_service = StockScreenerLlmReviewService(stock_screener_repo)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段采用超时+降级策略，避免整个BFF卡死在 startup。
    try:
        await asyncio.wait_for(bff_repo.initialize(), timeout=20)
    except asyncio.TimeoutError:
        logger.error("bff_repo.initialize 超时(20s)，继续以降级模式启动")
    except Exception as exc:
        logger.error(f"bff_repo.initialize 失败，继续以降级模式启动: {exc}")

    # 初始化实时推送服务
    try:
        await asyncio.wait_for(realtime_service.initialize(), timeout=10)
    except asyncio.TimeoutError:
        logger.error("realtime_service.initialize 超时(10s)，实时推送将不可用")
    except Exception as exc:
        logger.error(f"realtime_service.initialize 失败，实时推送将不可用: {exc}")

    # 初始化SSE推送服务
    global sse_push_service
    if SSE_PUSH_SERVICE_AVAILABLE:
        try:
            # 使用默认Redis URL创建SSE推送服务
            sse_push_service = await asyncio.wait_for(
                create_sse_push_service(
                    redis_url="redis://localhost:6379/0",
                    config={
                        "input_stream": "stream:event:feed",
                        "consumer_group": "sse_pushers",
                        "batch_size": 10,
                        "polling_interval": 1
                    }
                ),
                timeout=10,
            )
            logger.info("SSE推送服务初始化成功")
        except asyncio.TimeoutError:
            logger.error("SSE推送服务初始化超时(10s)")
            sse_push_service = None
        except Exception as e:
            logger.error(f"SSE推送服务初始化失败: {e}")
            sse_push_service = None
    else:
        logger.warning("SSE推送服务不可用，实时SSE端点将不可用")

    # 初始化选股器仓库
    try:
        await asyncio.wait_for(stock_screener_repo.initialize(), timeout=10)
    except asyncio.TimeoutError:
        logger.error("stock_screener_repo.initialize 超时(10s)，选股器接口将不可用")
    except Exception as exc:
        logger.error(f"stock_screener_repo.initialize 失败，选股器接口将不可用: {exc}")

    try:
        yield
    finally:
        await bff_repo.close()
        await realtime_service.shutdown()
        await stock_screener_repo.close()
        # 关闭SSE推送服务
        if sse_push_service:
            await sse_push_service.stop()
            logger.info("SSE推送服务已关闭")


app = FastAPI(
    title="AI投资助理 Frontend BFF",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置安全中间件
setup_security_middleware(app)

# 配置CORS中间件（已在安全中间件中配置，这里保留兼容性）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 添加全局OPTIONS处理器以支持CORS预检请求
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """处理所有OPTIONS预检请求"""
    return {"message": "CORS预检请求已处理"}

# 添加请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"请求: {request.method} {request.url.path}")
    response = await call_next(request)
    if response.status_code == 405:
        logger.warning(f"405错误: {request.method} {request.url.path}")
    return response


class CollectionStartRequest(BaseModel):
    trade_date: str
    options: dict = Field(default_factory=dict)
    tushare_pause_seconds: float = 0.1
    abnormal_filters: dict = Field(default_factory=dict)
    min_turnover_rate: float = 3.0
    min_composite_score: float = 40.0
    tushare_token: str = ""
    jyhf_token: str = ""


class CollectionJobActionRequest(BaseModel):
    job_id: str


class RealtimeCollectorActionRequest(BaseModel):
    with_frontend: bool = False
    restart: bool = False
    force: bool = False


class ScreenerStrategyPayload(BaseModel):
    strategy_name: str
    strategy_type: str
    description: str = ""
    weight_config: dict = Field(default_factory=dict)
    filter_config: dict = Field(default_factory=dict)
    is_active: bool = True


class ScreenerStrategyUpdatePayload(BaseModel):
    strategy_name: Optional[str] = None
    strategy_type: Optional[str] = None
    description: Optional[str] = None
    weight_config: Optional[dict] = None
    filter_config: Optional[dict] = None
    is_active: Optional[bool] = None


class ScreenerExecutePayload(BaseModel):
    strategy_id: str
    trade_date: Optional[str] = None
    limit: int = 100
    min_score: float = 60.0
    auto_tune_min_score: bool = True
    target_min_count: int = 30
    target_max_count: int = 120
    enable_llm_review: bool = False
    llm_top_k: int = 20
    run_stage1: bool = True
    run_stage2: bool = True


class ScreenerFavoritePayload(BaseModel):
    result_id: str
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ScreenerFavoriteUpdatePayload(BaseModel):
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ScreenerExportPayload(BaseModel):
    result_ids: list[str] = Field(default_factory=list)
    format: str = "json"


def _parse_trade_date(value: Optional[str]) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _serialize_screening_result(item: Any) -> dict[str, Any]:
    dimension_scores = getattr(item, "dimension_scores", None)
    if hasattr(dimension_scores, "__dict__"):
        dim_payload = {
            "mainline": float(getattr(dimension_scores, "mainline", 0)),
            "cycle": float(getattr(dimension_scores, "cycle", 0)),
            "leader": float(getattr(dimension_scores, "leader", 0)),
            "technical": float(getattr(dimension_scores, "technical", 0)),
        }
    elif isinstance(dimension_scores, dict):
        dim_payload = dimension_scores
    else:
        dim_payload = {"mainline": 0, "cycle": 0, "leader": 0, "technical": 0}

    return {
        "result_id": getattr(item, "result_id", ""),
        "stock_id": getattr(item, "stock_id", ""),
        "stock_name": getattr(item, "stock_name", ""),
        "composite_score": float(getattr(item, "composite_score", 0)),
        "dimension_scores": dim_payload,
        "rank_position": getattr(item, "rank_position", None),
        "screening_reason": getattr(item, "screening_reason", "") or "",
        "theme_info": getattr(item, "theme_info", None),
    }


def _result_presence(result_payload: dict[str, Any]) -> dict[str, bool]:
    dim = result_payload.get("dimension_scores") or {}
    theme_info = result_payload.get("theme_info") or {}
    has_theme = bool(theme_info.get("subject_key"))
    has_mainline = float(dim.get("mainline", 0) or 0) > 0
    has_cycle = float(dim.get("cycle", 0) or 0) > 0
    has_leader = float(dim.get("leader", 0) or 0) > 0
    has_technical = float(dim.get("technical", 0) or 0) > 0
    return {
        "theme": has_theme,
        "mainline": has_mainline,
        "cycle": has_cycle,
        "leader": has_leader,
        "technical": has_technical,
    }


def _is_weak_to_strong_strategy(strategy: Optional[ScreeningStrategy], strategy_id: str) -> bool:
    sid = (strategy_id or "").lower()
    if sid == "weak_to_strong" or "weak_to_strong" in sid:
        return True
    if not strategy:
        return False
    stype = (getattr(strategy, "strategy_type", "") or "").lower()
    sname = getattr(strategy, "strategy_name", "") or ""
    return stype == "weak_to_strong" or "weak_to_strong" in stype or ("弱转强" in sname)


async def _resolve_prev_trade_date(trade_date: date) -> date:
    pool = await stock_screener_repo._ensure_pool()
    sql = """
    SELECT MAX(trade_date) AS prev_trade_date
    FROM subject_stock_daily_snapshot
    WHERE trade_date < $1::date
    """
    async with pool.acquire() as conn:
        prev_day = await conn.fetchval(sql, trade_date)
    return prev_day or trade_date


async def _fetch_w2s_candidates(next_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    pool = await stock_screener_repo._ensure_pool()
    sql = """
    SELECT
      id,
      trade_date,
      next_trade_date,
      stock_id,
      stock_name,
      subject_key,
      theme_name,
      candidate_score,
      candidate_type,
      weak_type,
      support_type,
      support_strength,
      expected_open_low,
      expected_open_high,
      evidence_json
    FROM weak_to_strong_candidate_pool
    WHERE next_trade_date = $1::date OR trade_date = $1::date
    ORDER BY candidate_score DESC, id ASC
    LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, next_trade_date, max(int(limit), 1))
    return [dict(r) for r in rows]


async def _fetch_w2s_signals(trade_date: date) -> Dict[int, Dict[str, Any]]:
    pool = await stock_screener_repo._ensure_pool()
    sql = """
    SELECT
      candidate_id,
      signal_level,
      decision,
      confirmation_score,
      auction_open_pct,
      auction_close_pct,
      auction_pattern,
      last_minute_grab_score,
      plate_follow_score,
      risk_penalty,
      data_status,
      evidence_json
    FROM weak_to_strong_auction_signal
    WHERE trade_date = $1::date
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date)
    payload: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        payload[int(row["candidate_id"])] = dict(row)
    return payload


async def _has_w2s_snapshot_cache(trade_date: date) -> bool:
    pool = await stock_screener_repo._ensure_pool()
    sql = """
    SELECT 1
    FROM weak_to_strong_candidate_pool c
    JOIN pre_market_auction_snapshot s
      ON split_part(s.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
     AND s.trade_date = c.next_trade_date
    WHERE c.next_trade_date = $1::date
    LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, trade_date)
    return row is not None


def _load_env_file_values() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in (_project_root() / ".env.local", _project_root() / ".env.theme", _project_root() / ".env"):
        if not path.exists():
            continue
        try:
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'").strip()
                if key and value and key not in values:
                    values[key] = value
        except Exception:
            continue
    return values


def _resolve_tushare_token() -> str:
    token = str(os.getenv("TUSHARE_TOKEN") or "").strip()
    if token:
        return token
    env_values = _load_env_file_values()
    return str(env_values.get("TUSHARE_TOKEN") or "").strip()


async def _refresh_w2s_auction_snapshot(trade_date: date) -> None:
    token = _resolve_tushare_token()
    max_stocks = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS", "80") or 80), 1)
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    has_token = bool(token)
    if not has_token and trade_date == now_cn.date():
        raise HTTPException(status_code=400, detail="缺少 TUSHARE_TOKEN，无法执行盘前竞价采集")

    # 历史回放场景：允许无 token 使用已缓存快照，避免 500。
    if not has_token and trade_date < now_cn.date():
        if await _has_w2s_snapshot_cache(trade_date):
            return
        raise HTTPException(
            status_code=400,
            detail="缺少 TUSHARE_TOKEN 且未找到该交易日缓存竞价快照，请先完成日采集或在 .env.theme/.env.local 配置 TUSHARE_TOKEN",
        )

    cmd = [
        sys.executable,
        str(_project_root() / "database_service" / "scripts" / "build_pre_market_auction_snapshot.py"),
        "--trade-date",
        trade_date.isoformat(),
        "--universe-source",
        "weak_to_strong_candidates",
        "--max-stocks",
        str(max_stocks),
    ]
    if has_token:
        cmd.extend(["--token", token])
        cmd.append("--force-refresh")
    result = await _run_cmd(cmd, timeout_sec=120)
    if not result.get("ok"):
        detail = (result.get("stderr") or result.get("stdout") or "竞价采集脚本执行失败").strip()
        # 网络波动 / DNS 失败时，若已存在缓存则降级继续，避免用户无法完成盘前确认。
        if await _has_w2s_snapshot_cache(trade_date):
            logger.warning(f"盘前竞价采集失败，已回退缓存继续执行: trade_date={trade_date}, detail={detail[:300]}")
            return
        if "NameResolutionError" in detail or "Failed to resolve" in detail or "ConnectionError" in detail:
            raise HTTPException(
                status_code=503,
                detail="盘前竞价实时拉取失败（网络/DNS），且无可用缓存。请检查网络后重试，或先完成日采集生成缓存。",
            )
        raise HTTPException(status_code=500, detail=f"盘前竞价采集失败: {detail}")


def _build_w2s_result_row(candidate: Dict[str, Any], signal: Optional[Dict[str, Any]], rank: int) -> Dict[str, Any]:
    candidate_id = int(candidate.get("id") or 0)
    candidate_score = float(candidate.get("candidate_score") or 0.0)
    confirmation_score = float((signal or {}).get("confirmation_score") or 0.0)
    composite = confirmation_score if signal else candidate_score
    signal_level = str((signal or {}).get("signal_level") or "")
    decision = str((signal or {}).get("decision") or "")
    screening_reason = (
        f"阶段一候选: {candidate.get('candidate_type') or '--'} / "
        f"阶段二确认: {signal_level or '--'} {decision or ''}".strip()
    )
    return {
        "result_id": f"w2s_{candidate_id}",
        "stock_id": str(candidate.get("stock_id") or ""),
        "stock_name": str(candidate.get("stock_name") or ""),
        "composite_score": round(composite, 2),
        "dimension_scores": {
            "mainline": 0.0,
            "cycle": round(composite, 2),
            "leader": 0.0,
            "technical": 0.0,
        },
        "rank_position": rank,
        "screening_reason": screening_reason,
        "theme_info": {
            "subject_key": str(candidate.get("subject_key") or ""),
            "theme_name": str(candidate.get("theme_name") or candidate.get("subject_key") or ""),
        },
        "weak_to_strong": {
            "candidate_id": candidate_id,
            "candidate_score": candidate_score,
            "candidate_type": str(candidate.get("candidate_type") or ""),
            "weak_type": str(candidate.get("weak_type") or ""),
            "support_type": str(candidate.get("support_type") or ""),
            "support_strength": float(candidate.get("support_strength") or 0.0),
            "expected_open_low": float(candidate.get("expected_open_low") or 0.0),
            "expected_open_high": float(candidate.get("expected_open_high") or 0.0),
            "signal_level": signal_level,
            "decision": decision,
            "confirmation_score": confirmation_score,
            "auction_open_pct": float((signal or {}).get("auction_open_pct") or 0.0),
            "auction_close_pct": float((signal or {}).get("auction_close_pct") or 0.0),
            "auction_pattern": str((signal or {}).get("auction_pattern") or ""),
            "last_minute_grab_score": float((signal or {}).get("last_minute_grab_score") or 0.0),
            "plate_follow_score": float((signal or {}).get("plate_follow_score") or 0.0),
            "risk_penalty": float((signal or {}).get("risk_penalty") or 0.0),
            "data_status": str((signal or {}).get("data_status") or "missing"),
            "candidate_evidence": candidate.get("evidence_json") or {},
            "signal_evidence": (signal or {}).get("evidence_json") or {},
        },
    }


async def _execute_weak_to_strong_two_stage(payload: ScreenerExecutePayload, trade_date: date) -> Dict[str, Any]:
    started = time.perf_counter()
    strategy = await stock_screener_repo.get_strategy(payload.strategy_id)
    strategy_name = getattr(strategy, "strategy_name", "弱转强策略")

    run_stage1 = bool(payload.run_stage1)
    run_stage2 = bool(payload.run_stage2)
    if not run_stage1 and not run_stage2:
        run_stage2 = True
    stage1_limit = max(int(os.getenv("W2S_STAGE1_MAX_CANDIDATES", "20") or 20), 1)

    # 同交易日盘前阶段二门禁：9:25 前禁止竞价确认，避免拿到不完整竞价数据
    if run_stage2:
        now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
        if trade_date == now_cn.date():
            if now_cn.hour < 9 or (now_cn.hour == 9 and now_cn.minute < 25):
                raise HTTPException(status_code=400, detail="盘前9:25之后才能采集！")

    candidate_builder = WeakToStrongCandidateBuilder()
    auction_service = WeakToStrongAuctionService()

    stage1_summary: Dict[str, Any] = {"status": "skipped", "candidate_count": 0}
    stage2_summary: Dict[str, Any] = {"status": "skipped", "level_count": {"A": 0, "B": 0, "C": 0, "X": 0}}
    try:
        if run_stage1:
            # 盘后选股必须使用“当日盘后数据”，为下一交易日生成候选池。
            source_trade_date = trade_date
            try:
                build_result = await asyncio.wait_for(
                    candidate_builder.build(
                        source_trade_date,
                        next_trade_date=trade_date,
                        max_candidates=stage1_limit,
                    ),
                    timeout=30.0
                )
                stage1_summary = {
                    "status": "success",
                    "source_trade_date": source_trade_date.isoformat(),
                    "candidate_count": int(build_result.total_inserted),
                    "candidate_limit": stage1_limit,
                }
            except asyncio.TimeoutError:
                logger.error(f"弱转强候选构建超时(30s)，跳过构建，使用现有候选池数据")
                stage1_summary = {
                    "status": "timeout",
                    "source_trade_date": source_trade_date.isoformat(),
                    "candidate_count": 0,
                    "candidate_limit": stage1_limit,
                }
            except Exception as e:
                logger.error(f"弱转强候选构建失败: {e}")
                stage1_summary = {
                    "status": "error",
                    "source_trade_date": source_trade_date.isoformat(),
                    "candidate_count": 0,
                    "candidate_limit": stage1_limit,
                    "error": str(e)[:200]
                }

        if run_stage2:
            await _refresh_w2s_auction_snapshot(trade_date)
            confirm_result = await auction_service.confirm(trade_date)
            stage2_summary = {
                "status": "success",
                "total_candidates": int(confirm_result.total_candidates),
                "persisted_count": int(confirm_result.persisted_count),
                "level_count": confirm_result.level_count,
            }
    finally:
        await candidate_builder.close()
        await auction_service.close()

    if run_stage2:
        candidate_limit = 2000
    else:
        candidate_limit = stage1_limit
    candidates = await _fetch_w2s_candidates(trade_date, limit=candidate_limit)
    signals = await _fetch_w2s_signals(trade_date) if run_stage2 else {}
    results: List[Dict[str, Any]] = []
    if run_stage2:
        # 两阶段结果以阶段二信号为主，避免受候选列表 limit 截断导致“有信号但显示0条”。
        candidate_map: Dict[int, Dict[str, Any]] = {
            int(c.get("id") or 0): c for c in candidates if int(c.get("id") or 0) > 0
        }
        sorted_signals = sorted(
            signals.items(),
            key=lambda kv: float((kv[1] or {}).get("confirmation_score") or 0.0),
            reverse=True,
        )
        for candidate_id, signal in sorted_signals:
            candidate = candidate_map.get(int(candidate_id))
            if candidate is None:
                continue
            results.append(_build_w2s_result_row(candidate, signal, len(results) + 1))
    else:
        for idx, candidate in enumerate(candidates, start=1):
            candidate_id = int(candidate.get("id") or 0)
            signal = signals.get(candidate_id)
            results.append(_build_w2s_result_row(candidate, signal, idx))
    results.sort(key=lambda x: float(x.get("composite_score") or 0.0), reverse=True)
    for i, row in enumerate(results, start=1):
        row["rank_position"] = i

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "job_id": f"w2s_{payload.strategy_id}_{trade_date.isoformat()}_{int(time.time())}",
        "status": "completed",
        "results": results,
        "total_count": len(results),
        "trade_date": trade_date.isoformat(),
        "execution_time_ms": elapsed_ms,
        "llm_review_status": "disabled_for_two_stage",
        "llm_summary": {"pass": 0, "watch": 0, "reject": 0, "failed": 0},
        "diagnostics": {
            "two_stage": True,
            "strategy_name": strategy_name,
            "run_stage1": run_stage1,
            "run_stage2": run_stage2,
            "stage1": stage1_summary,
            "stage2": stage2_summary,
            "candidate_pool_count": len(candidates),
            "signal_count": len(signals),
            "display_result_count": len(results),
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "frontend_bff"}


@app.get("/test/timeout")
async def test_timeout(delay: int = Query(default=5, ge=1, le=60)):
    """测试超时的端点"""
    import asyncio
    await asyncio.sleep(delay)
    return {"message": f"延迟 {delay} 秒后响应", "timestamp": datetime.now().isoformat()}


@app.get("/test/error")
async def test_error(status_code: int = Query(default=500, ge=400, le=599)):
    """测试错误响应的端点"""
    raise HTTPException(status_code=status_code, detail=f"测试错误 {status_code}")


@app.get("/test/connection")
async def test_connection():
    """测试连接状态的端点"""
    return {
        "status": "connected",
        "timestamp": datetime.now().isoformat(),
        "server_info": {
            "host": "0.0.0.0",
            "port": 8003,
            "cors_enabled": True
        }
    }


@app.api_route("/api/stock-screener/strategies", methods=["GET", "HEAD"])
async def get_stock_screener_strategies(active_only: bool = Query(default=True)):
    strategies = await stock_screener_repo.get_strategies(active_only=active_only)
    return [
        {
            "strategy_id": s.strategy_id,
            "strategy_name": s.strategy_name,
            "strategy_type": s.strategy_type,
            "description": s.description,
            "weight_config": s.weight_config,
            "filter_config": s.filter_config,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "created_by": s.created_by,
        }
        for s in strategies
    ]


@app.post("/api/stock-screener/strategies")
async def create_stock_screener_strategy(payload: ScreenerStrategyPayload):
    now = datetime.now()
    strategy = ScreeningStrategy(
        strategy_id=f"strategy_{uuid.uuid4().hex[:12]}",
        strategy_name=payload.strategy_name,
        strategy_type=payload.strategy_type,
        description=payload.description,
        weight_config=payload.weight_config or {"mainline": 0.35, "cycle": 0.30, "leader": 0.20, "technical": 0.15},
        filter_config=payload.filter_config or {},
        created_at=now,
        updated_at=now,
        created_by="frontend_bff",
        is_active=payload.is_active,
    )
    created = await stock_screener_repo.create_strategy(strategy)
    if not created:
        raise HTTPException(status_code=500, detail="create strategy failed")
    return {
        "strategy_id": created.strategy_id,
        "strategy_name": created.strategy_name,
        "strategy_type": created.strategy_type,
        "description": created.description,
        "weight_config": created.weight_config,
        "filter_config": created.filter_config,
        "is_active": created.is_active,
        "created_at": created.created_at.isoformat() if created.created_at else None,
        "updated_at": created.updated_at.isoformat() if created.updated_at else None,
    }


@app.put("/api/stock-screener/strategies/{strategy_id}")
async def update_stock_screener_strategy(strategy_id: str, payload: ScreenerStrategyUpdatePayload):
    updates = payload.model_dump(exclude_none=True)
    ok = await stock_screener_repo.update_strategy(strategy_id, updates)
    if not ok:
        raise HTTPException(status_code=404, detail="strategy not found")
    strategy = await stock_screener_repo.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="strategy not found")
    return {
        "strategy_id": strategy.strategy_id,
        "strategy_name": strategy.strategy_name,
        "strategy_type": strategy.strategy_type,
        "description": strategy.description,
        "weight_config": strategy.weight_config,
        "filter_config": strategy.filter_config,
        "is_active": strategy.is_active,
        "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }


@app.delete("/api/stock-screener/strategies/{strategy_id}")
async def delete_stock_screener_strategy(strategy_id: str):
    ok = await stock_screener_repo.delete_strategy(strategy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="strategy not found")
    return {"ok": True, "strategy_id": strategy_id}


@app.post("/api/stock-screener/execute")
async def execute_stock_screener(payload: ScreenerExecutePayload):
    started = time.perf_counter()
    requested_trade_date = _parse_trade_date(payload.trade_date)
    trade_date = requested_trade_date
    fallback_applied = False
    fallback_reason: Optional[str] = None

    strategy = await stock_screener_repo.get_strategy(payload.strategy_id)
    if _is_weak_to_strong_strategy(strategy, payload.strategy_id):
        return await _execute_weak_to_strong_two_stage(payload, trade_date)

    # 1. 市场状态评估 - 先有主线，再有选股
    decision_service = StrategyDecisionService()
    market_state = await decision_service.assess_market_state(trade_date)

    # 如果市场无主线，暂停选股
    if market_state.mode == "standby":
        return {
            "job_id": f"rejected_{trade_date.isoformat()}_{int(time.time())}",
            "status": "rejected",
            "results": [],
            "total_count": 0,
            "trade_date": trade_date.isoformat(),
            "execution_time_ms": int((time.perf_counter() - started) * 1000),
            "llm_review_status": "disabled",
            "llm_summary": {"pass": 0, "watch": 0, "reject": 0, "failed": 0},
            "diagnostics": {
                "requested_trade_date": requested_trade_date.isoformat(),
                "resolved_trade_date": trade_date.isoformat(),
                "fallback_applied": fallback_applied,
                "fallback_reason": fallback_reason,
                "market_state": {
                    "mode": market_state.mode,
                    "action_bias": market_state.action_bias,
                    "position_limit": market_state.position_limit,
                    "market_health_score": market_state.market_health_score,
                    "main_theme_count": market_state.main_theme_count,
                    "reason": market_state.reason
                },
                "rejection_reason": f"市场无主线：{market_state.reason}"
            }
        }

    # 根据市场状态调整选股参数
    # - 进攻模式：高仓位，积极选股
    # - 防守模式：中等仓位，保守选股
    # - 谨慎模式：低仓位，谨慎选股
    market_mode_multiplier = {
        "offensive": 1.0,
        "defensive": 0.7,
        "cautious": 0.5,
        "standby": 0.0
    }.get(market_state.mode, 0.5)

    requested_count = await stock_screener_repo.get_snapshot_stock_count(requested_trade_date)
    if requested_count <= 0:
        fallback_date = await stock_screener_repo.get_latest_snapshot_trade_date(requested_trade_date)
        if fallback_date and fallback_date != requested_trade_date:
            trade_date = fallback_date
            fallback_applied = True
            fallback_reason = (
                f"trade_date={requested_trade_date.isoformat()} 无可用快照，"
                f"自动回退到最近交易日 {trade_date.isoformat()}"
            )

    # 根据市场状态调整选股参数
    # 1. 仓位限制应用到选股数量
    adjusted_limit = int(payload.limit * market_state.position_limit) if payload.limit > 0 else payload.limit
    if adjusted_limit <= 0 and payload.limit > 0:
        adjusted_limit = 1  # 至少选1只股票

    # 2. 根据市场模式调整评分门槛
    # 进攻模式：使用原门槛
    # 防守模式：提高门槛10%
    # 谨慎模式：提高门槛20%
    min_score_adjustment = {
        "offensive": 0.0,
        "defensive": 0.1,
        "cautious": 0.2,
        "standby": 1.0  # 但standby模式已提前返回
    }.get(market_state.mode, 0.0)

    adjusted_min_score = float(payload.min_score) * (1 + min_score_adjustment)

    config = ScreeningConfig(
        strategy_id=payload.strategy_id,
        trade_date=trade_date,
        min_composite_score=adjusted_min_score,
        limit=adjusted_limit,
        auto_tune_min_score=bool(payload.auto_tune_min_score),
        target_min_count=max(int(payload.target_min_count), 1),
        target_max_count=max(int(payload.target_max_count), 1),
        only_main_theme=True,  # 必须从主线中选股，不选杂毛
    )
    try:
        results, run_meta = await asyncio.wait_for(
            stock_screener_service.execute_screening_with_meta(config),
            timeout=60.0  # 60秒超时
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="选股执行超时，请稍后重试")
    except ValueError as e:
        # 例如: 策略不存在
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("选股执行失败 strategy_id=%s trade_date=%s", payload.strategy_id, trade_date)
        raise HTTPException(status_code=500, detail=f"选股执行失败: {e}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    latest_exec = await stock_screener_repo.get_latest_execution(payload.strategy_id, trade_date)
    job_id = (latest_exec or {}).get("execution_id") or f"exec_{payload.strategy_id}_{trade_date.isoformat()}"
    status = (latest_exec or {}).get("status") or "completed"
    execution_time_ms = int((latest_exec or {}).get("execution_time_ms") or elapsed_ms)

    serialized_results = [_serialize_screening_result(item) for item in results]
    presence_list = [_result_presence(x) for x in serialized_results]
    total = len(serialized_results)
    if total > 0:
        coverage = {
            "theme": sum(1 for p in presence_list if p["theme"]) / total,
            "mainline": sum(1 for p in presence_list if p["mainline"]) / total,
            "cycle": sum(1 for p in presence_list if p["cycle"]) / total,
            "leader": sum(1 for p in presence_list if p["leader"]) / total,
            "technical": sum(1 for p in presence_list if p["technical"]) / total,
        }
    else:
        coverage = {"theme": 0.0, "mainline": 0.0, "cycle": 0.0, "leader": 0.0, "technical": 0.0}

    zero_score_count = sum(
        1
        for x in serialized_results
        if float(x.get("composite_score", 0) or 0) <= 0
    )
    missing_dimension_count = {
        "mainline": sum(1 for p in presence_list if not p["mainline"]),
        "cycle": sum(1 for p in presence_list if not p["cycle"]),
        "leader": sum(1 for p in presence_list if not p["leader"]),
        "technical": sum(1 for p in presence_list if not p["technical"]),
    }
    no_data_reason = None
    if int((latest_exec or {}).get("total_stocks") or 0) == 0:
        no_data_reason = f"trade_date={trade_date.isoformat()} 无可筛选股票快照数据"

    llm_review_status = "disabled"
    llm_summary = {"pass": 0, "watch": 0, "reject": 0, "failed": 0}
    if payload.enable_llm_review:
        llm_review_map, llm_review_status, llm_summary = await stock_screener_llm_review_service.review_results(
            execution_id=job_id,
            strategy_id=payload.strategy_id,
            trade_date=trade_date,
            results=results,
            top_k=max(1, min(int(payload.llm_top_k), 100)),
        )
        for item in serialized_results:
            rid = str(item.get("result_id") or "")
            if rid and rid in llm_review_map:
                item["llm_review"] = llm_review_map[rid]

    return {
        "job_id": job_id,
        "status": status,
        "results": serialized_results,
        "total_count": len(results),
        "trade_date": trade_date.isoformat(),
        "execution_time_ms": execution_time_ms,
        "llm_review_status": llm_review_status,
        "llm_summary": llm_summary,
        "diagnostics": {
            "market_state": {
                "mode": market_state.mode,
                "action_bias": market_state.action_bias,
                "position_limit": market_state.position_limit,
                "market_health_score": market_state.market_health_score,
                "main_theme_count": market_state.main_theme_count,
                "reason": market_state.reason
            },
            "requested_trade_date": requested_trade_date.isoformat(),
            "resolved_trade_date": trade_date.isoformat(),
            "fallback_applied": fallback_applied,
            "fallback_reason": fallback_reason,
            "requested_snapshot_stock_count": requested_count,
            "resolved_snapshot_stock_count": int((latest_exec or {}).get("total_stocks") or 0),
            "no_data_reason": no_data_reason,
            "score_tuning": {
                "requested_min_score": run_meta.requested_min_score,
                "tuned_min_score": run_meta.tuned_min_score,
                "auto_tune_applied": run_meta.auto_tune_applied,
                "total_scored": run_meta.total_scored,
                "pre_filter_count": run_meta.pre_filter_count,
                "final_count": run_meta.final_count,
                "target_min_count": run_meta.target_min_count,
                "target_max_count": run_meta.target_max_count,
            },
            "coverage_ratio": coverage,
            "zero_score_count": zero_score_count,
            "missing_dimension_count": missing_dimension_count,
        },
    }


@app.get("/api/stock-screener/executions/{job_id}")
async def get_stock_screener_execution(job_id: str):
    execution = await stock_screener_repo.get_execution(job_id)
    if not execution:
        # 兼容 execute 返回的临时 job_id
        return {
            "job_id": job_id,
            "status": "completed",
            "results": [],
            "total_count": 0,
            "execution_time_ms": 0,
        }
    return {
        "job_id": execution["execution_id"],
        "status": execution["status"],
        "results": [],
        "total_count": int(execution.get("results_count") or 0),
        "execution_time_ms": int(execution.get("execution_time_ms") or 0),
    }


@app.get("/api/stock-screener/results/{result_id}")
async def get_stock_screener_result_detail(result_id: str):
    if result_id.startswith("w2s_"):
        try:
            candidate_id = int(result_id.split("_", 1)[1])
        except Exception:
            raise HTTPException(status_code=400, detail="invalid weak_to_strong result_id")
        service = WeakToStrongAuctionService()
        try:
            replay = await service.get_replay_by_candidate_id(candidate_id)
        finally:
            await service.close()
        if not replay:
            raise HTTPException(status_code=404, detail="result not found")
        signal_evidence = replay.get("signal_evidence") or {}
        score_payload = ((signal_evidence or {}).get("scores") or {})
        return {
            "result_id": result_id,
            "stock_id": replay.get("stock_id", ""),
            "stock_name": replay.get("stock_name", ""),
            "composite_score": float(replay.get("confirmation_score") or replay.get("candidate_score") or 0.0),
            "dimension_scores": {
                "mainline": 0.0,
                "cycle": float(replay.get("confirmation_score") or 0.0),
                "leader": 0.0,
                "technical": 0.0,
            },
            "rank_position": None,
            "screening_reason": f"弱转强两阶段结果：{replay.get('signal_level','')} / {replay.get('decision','')}",
            "theme_info": {},
            "dimension_details": {
                "mainline": {"strength_score": 0, "heat_rank": 0, "capital_attention": 0, "reasoning": ""},
                "cycle": {
                    "stage_score": float(score_payload.get("pattern_stability") or 0.0),
                    "duration_score": float(score_payload.get("last_minute_grab") or 0.0),
                    "stability_score": float(score_payload.get("plate_follow") or 0.0),
                    "reasoning": "",
                },
                "leader": {"position_score": 0, "leading_effect": 0, "capital_recognition": 0, "reasoning": ""},
                "technical": {"abnormal_score": 0, "pattern_score": 0, "volume_price_score": 0, "reasoning": ""},
            },
            "created_at": datetime.now().isoformat(),
            "weak_to_strong_replay": replay,
        }

    detail = await stock_screener_service.get_result_detail(result_id)
    if not detail:
        raise HTTPException(status_code=404, detail="result not found")

    payload = _serialize_screening_result(detail)
    payload["dimension_details"] = getattr(detail, "dimension_details", None)
    payload["created_at"] = detail.created_at.isoformat() if detail.created_at else None
    llm_review = await stock_screener_repo.get_llm_review(result_id)
    if llm_review:
        payload["llm_review"] = llm_review
    return payload


@app.get("/api/stock-screener/history")
async def get_stock_screener_history(
    strategy_id: Optional[str] = Query(default=None),
    trade_date_from: Optional[str] = Query(default=None),
    trade_date_to: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    result = await stock_screener_repo.query_history(
        strategy_id=strategy_id,
        trade_date_from=_parse_trade_date(trade_date_from) if trade_date_from else None,
        trade_date_to=_parse_trade_date(trade_date_to) if trade_date_to else None,
        stock_id=stock_id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return result


@app.get("/api/stock-screener/favorites")
async def get_stock_screener_favorites(user_id: str = Query(default="default")):
    favorites = await stock_screener_repo.get_user_favorites(user_id)
    result_items = []
    for item in favorites:
        result = await stock_screener_repo.get_result(item.result_id)
        if not result:
            continue
        result_items.append(
            {
                "favorite_id": item.favorite_id,
                "result_id": item.result_id,
                "stock_id": result.stock_id,
                "stock_name": result.stock_name,
                "composite_score": float(result.composite_score),
                "notes": item.notes,
                "tags": item.tags,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )
    return result_items


@app.post("/api/stock-screener/favorites")
async def add_stock_screener_favorite(payload: ScreenerFavoritePayload, user_id: str = Query(default="default")):
    favorite = UserFavorite(
        favorite_id=f"fav_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        result_id=payload.result_id,
        notes=payload.notes,
        tags=payload.tags,
        created_at=datetime.now(),
    )
    ok = await stock_screener_repo.add_favorite(favorite)
    if not ok:
        raise HTTPException(status_code=500, detail="add favorite failed")
    result = await stock_screener_repo.get_result(payload.result_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not found")
    return {
        "favorite_id": favorite.favorite_id,
        "result_id": favorite.result_id,
        "stock_id": result.stock_id,
        "stock_name": result.stock_name,
        "composite_score": float(result.composite_score),
        "notes": favorite.notes,
        "tags": favorite.tags,
        "created_at": favorite.created_at.isoformat(),
    }


@app.put("/api/stock-screener/favorites/{favorite_id}")
async def update_stock_screener_favorite(favorite_id: str, payload: ScreenerFavoriteUpdatePayload):
    ok = await stock_screener_repo.update_favorite(favorite_id, payload.notes, payload.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.delete("/api/stock-screener/favorites/{favorite_id}")
async def delete_stock_screener_favorite(favorite_id: str):
    ok = await stock_screener_repo.remove_favorite(favorite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.get("/api/stock-screener/statistics")
async def get_stock_screener_statistics(
    strategy_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
):
    stats = await stock_screener_repo.get_statistics(
        strategy_id=strategy_id,
        date_from=_parse_trade_date(from_date) if from_date else None,
        date_to=_parse_trade_date(to_date) if to_date else None,
    )
    return {
        "total_executions": stats.get("total_results", 0),
        "avg_composite_score": stats.get("avg_composite_score", 0),
        "top_themes": stats.get("top_themes", []),
        "score_distribution": stats.get("score_distribution", []),
    }


@app.post("/api/stock-screener/export")
async def export_stock_screener_results(payload: ScreenerExportPayload):
    export_items = []
    for result_id in payload.result_ids:
        result = await stock_screener_repo.get_result(result_id)
        if not result:
            continue
        export_items.append(_serialize_screening_result(result))

    export_dir = _realtime_log_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    ext = "json" if payload.format not in {"csv", "excel", "json"} else ("csv" if payload.format == "csv" else "json")
    filename = f"stock_screener_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
    file_path = export_dir / filename

    if ext == "csv":
        headers = ["result_id", "stock_id", "stock_name", "composite_score", "rank_position", "screening_reason"]
        lines = [",".join(headers)]
        for item in export_items:
            row = [
                str(item.get("result_id", "")),
                str(item.get("stock_id", "")),
                str(item.get("stock_name", "")),
                str(item.get("composite_score", "")),
                str(item.get("rank_position", "")),
                str(item.get("screening_reason", "")).replace(",", " "),
            ]
            lines.append(",".join(row))
        file_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        file_path.write_text(json.dumps(export_items, ensure_ascii=False, indent=2, cls=DecimalEncoder), encoding="utf-8")

    return {"download_url": str(file_path)}


@app.get("/api/intel/feed")
async def get_intel_feed(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|event_review|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await bff_repo.fetch_intel_feed_view(
        feed_date=date,
        session=session,
        item_type=type,
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )


@app.get("/api/intel/stream")
async def get_intel_stream(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|event_review|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    async def event_generator():
        seen_item_ids: set[str] = set()
        heartbeat_interval = 15
        poll_interval = 5
        elapsed = 0

        while True:
            try:
                payload = await bff_repo.fetch_intel_feed_view(
                    feed_date=date,
                    session=session,
                    item_type=type,
                    subject_key=subject_key,
                    stock_id=stock_id,
                    limit=limit,
                )
                items = payload.get("items", [])
                fresh_items = []
                for item in items:
                    item_id = str(item.get("item_id") or "")
                    if not item_id or item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    fresh_items.append(item)

                for item in reversed(fresh_items):
                    body = {
                        "event_id": item.get("item_id"),
                        "occurred_at": item.get("occurred_at"),
                        "event_type": item.get("item_type"),
                        "item": item,
                    }
                    yield f"event: intel_item\ndata: {json.dumps(body, ensure_ascii=False, cls=DecimalEncoder)}\n\n"

                elapsed += poll_interval
                if elapsed >= heartbeat_interval:
                    yield "event: heartbeat\ndata: {\"status\":\"ok\"}\n\n"
                    elapsed = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                payload = {"status": "error", "message": str(exc)}
                yield f"event: heartbeat\ndata: {json.dumps(payload, ensure_ascii=False, cls=DecimalEncoder)}\n\n"

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/intel/stream/realtime")
async def get_intel_stream_realtime(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|event_review|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    实时SSE端点 - 直接从Redis Stream消费事件

    此端点直接从stream:event:feed消费事件，提供真正的实时推送。
    如果SSE推送服务不可用，将返回服务不可用错误。

    注意：参数主要用于客户端标识，实际事件过滤在Stream层面进行。
    """
    if not sse_push_service:
        raise HTTPException(
            status_code=503,
            detail="实时SSE推送服务不可用，请使用 /api/intel/stream 端点"
        )

    async def event_generator():
        try:
            # 创建客户端信息
            client_info = {
                "date": date,
                "session": session,
                "type": type,
                "subject_key": subject_key,
                "stock_id": stock_id,
                "limit": limit,
                "connected_at": datetime.now().isoformat()
            }

            # 获取SSE事件生成器
            sse_generator = sse_push_service.create_sse_event_generator(client_info)

            # 流式传输SSE事件
            async for sse_event in sse_generator:
                yield sse_event

        except asyncio.CancelledError:
            logger.info("SSE客户端连接被取消")
            raise
        except Exception as e:
            logger.error(f"SSE事件生成器错误: {e}")
            # 发送错误事件
            error_event = {
                "event_type": "error",
                "data": {
                    "message": f"SSE服务错误: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            }
            error_sse = f"event: {error_event['event_type']}\ndata: {json.dumps(error_event['data'], ensure_ascii=False, cls=DecimalEncoder)}\n\n"
            yield error_sse

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/theme-workspace/{subject_key}")
async def get_theme_workspace(
    subject_key: str,
    trade_date: Optional[str] = Query(default=None),
    include_history: bool = Query(default=True),
    include_children: bool = Query(default=True),
    include_stocks: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    stock_mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    history_limit: int = Query(default=20, ge=1, le=200),
    children_limit: int = Query(default=50, ge=1, le=500),
    stocks_limit: int = Query(default=50, ge=1, le=500),
):
    payload = await bff_repo.fetch_theme_workspace_view(
        subject_key=subject_key,
        trade_date=trade_date,
        include_history=include_history,
        include_children=include_children,
        include_stocks=include_stocks,
        include_leaders=include_leaders,
        stock_mapping_scope=stock_mapping_scope,
        history_limit=history_limit,
        children_limit=children_limit,
        stocks_limit=stocks_limit,
    )
    if not payload:
        raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")
    return payload


@app.get("/api/stock-workspace/{stock_id}")
async def get_stock_workspace(
    stock_id: str,
    include_themes: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    themes_limit: int = Query(default=50, ge=1, le=500),
):
    payload = await bff_repo.fetch_stock_workspace_view(
        stock_id=stock_id,
        include_themes=include_themes,
        include_leaders=include_leaders,
        mapping_scope=mapping_scope,
        themes_limit=themes_limit,
    )
    if not payload:
        raise HTTPException(status_code=404, detail=f"stock workspace not found for stock_id={stock_id}")
    return payload


@app.get("/api/recap")
async def get_recap(
    date: str = Query(...),
    report_type: str = Query(default="post_market", pattern="^(pre_market|post_market)$"),
):
    return await bff_repo.fetch_recap_view(
        trade_date=date,
        report_type=report_type,
    )


@app.get("/api/recap/defaults")
async def get_recap_defaults():
    return await bff_repo.fetch_recap_defaults()


@app.get("/api/collection/availability")
async def get_collection_availability(trade_date: Optional[str] = Query(default=None)):
    return collection_job_manager.availability(trade_date)


@app.post("/api/collection/start")
async def start_collection(payload: CollectionStartRequest):
    availability = collection_job_manager.availability(payload.trade_date)
    if not availability["allowed"]:
        raise HTTPException(status_code=400, detail=availability["message"])
    job = collection_job_manager.create_job(payload.trade_date, payload.model_dump())
    return job.to_dict()


@app.get("/api/collection/status")
async def get_collection_status(job_id: str = Query(...)):
    job = collection_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/collection/cancel")
async def cancel_collection(payload: CollectionJobActionRequest):
    job = await collection_job_manager.cancel_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/collection/continue")
async def continue_collection(payload: CollectionJobActionRequest):
    job = await collection_job_manager.continue_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _realtime_log_dir() -> Path:
    return Path("/tmp/ai_theme_realtime")


def _build_start_cmd(with_frontend: bool, restart: bool) -> list[str]:
    cmd = ["bash", str(_project_root() / "scripts" / "run_realtime_stack.sh")]
    if with_frontend:
        cmd.append("--with-frontend")
    if restart:
        cmd.append("--restart")
    return cmd


def _build_stop_cmd(with_frontend: bool, force: bool) -> list[str]:
    cmd = ["bash", str(_project_root() / "scripts" / "stop_realtime_stack.sh")]
    if with_frontend:
        cmd.append("--with-frontend")
    if force:
        cmd.append("--force")
    return cmd


async def _run_cmd(cmd: list[str], timeout_sec: int) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(_project_root()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "ALLOW_REALTIME_AUTO_THEME_CREATE": "false"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail=f"command timeout after {timeout_sec}s")
    return {
        "ok": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "command": cmd,
    }


@app.get("/api/realtime/collector/status")
async def get_realtime_collector_status():
    result = await _run_cmd(
        ["bash", str(_project_root() / "scripts" / "status_realtime_stack.sh")],
        timeout_sec=30,
    )
    return result


@app.post("/api/realtime/collector/start")
async def start_realtime_collector(payload: RealtimeCollectorActionRequest):
    result = await _run_cmd(
        _build_start_cmd(with_frontend=payload.with_frontend, restart=payload.restart),
        timeout_sec=150,
    )
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/api/realtime/collector/stop")
async def stop_realtime_collector(payload: RealtimeCollectorActionRequest):
    result = await _run_cmd(
        _build_stop_cmd(with_frontend=payload.with_frontend, force=payload.force),
        timeout_sec=60,
    )
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


def _extract_log_line_timestamp(line: str) -> Optional[float]:
    text = (line or "").strip()
    if len(text) < 19:
        return None
    # 支持日志前缀如: 2026-04-11 09:40:12,754 - ...
    candidate = text[:19]
    try:
        # 日志时间按本地时区写入，这里按本地时间解析，避免UTC偏移导致误判。
        dt = datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except ValueError:
        return None


@app.get("/api/realtime/collector/logs")
async def get_realtime_collector_logs(
    lines: int = Query(default=200, ge=20, le=2000),
    max_age_minutes: int = Query(default=180, ge=10, le=1440),
):
    log_dir = _realtime_log_dir()
    files = [
        log_dir / "start_services.log",
        log_dir / "frontend_bff_8003.log",
        log_dir / "frontend_vite.log",
    ]
    payload: dict[str, list[str]] = {}
    cutoff_ts = time.time() - (max_age_minutes * 60)
    for file_path in files:
        if not file_path.exists():
            payload[file_path.name] = []
            continue
        try:
            file_stat = file_path.stat()
            # 多取一些尾部再做时间过滤，避免过滤后结果过少。
            raw_content = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_tail = raw_content[-max(lines * 4, lines):]
            filtered: list[str] = []
            for row in recent_tail:
                ts = _extract_log_line_timestamp(row)
                if ts is not None and ts < cutoff_ts:
                    continue
                filtered.append(row)

            if not filtered and file_stat.st_mtime < cutoff_ts:
                stale_dt = datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                filtered = [f"[stale] 日志文件最近更新时间: {stale_dt}，当前未检测到最新日志输出"]

            payload[file_path.name] = filtered[-lines:]
        except Exception as exc:
            payload[file_path.name] = [f"[error] {exc}"]
    return {
        "log_dir": str(log_dir),
        "lines": lines,
        "max_age_minutes": max_age_minutes,
        "files": payload,
    }


# ============================================================================
# 实时推送服务接口
# ============================================================================

@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """
    WebSocket实时推送接口（可选高级功能）

    高级客户端可以通过此接口订阅Redis Stream的实时事件，支持双向通信。
    注意：主要实时数据通道为Server-Sent Events (SSE) /api/intel/stream。
    此WebSocket接口为可选功能，用于需要客户端->服务器命令的场景。

    支持的命令：
    - {"command": "subscribe", "stream": "stream:event:feed"}
    - {"command": "unsubscribe", "stream": "stream:event:feed"}
    - {"command": "list_subscriptions"}
    - {"command": "ping"}
    - {"command": "get_stats"}
    """
    await realtime_service.handle_websocket_connection(websocket)


@app.get("/api/realtime/stats")
async def get_realtime_stats():
    """
    获取实时推送服务统计信息

    返回当前连接数、订阅统计、服务状态等信息。
    """
    return realtime_service.get_stats()


@app.get("/api/realtime/streams")
async def get_available_streams():
    """
    获取可用的实时Stream列表和实时通信协议说明

    返回系统支持订阅的Redis Stream列表。
    主要实时数据通道为Server-Sent Events (SSE) /api/intel/stream。
    WebSocket /ws/realtime 为可选高级功能，支持双向通信。
    """
    return {
        "available_streams": [
            {
                "name": "stream:event:feed",
                "description": "事件流 - 包含所有AI提取的结构化事件",
                "example_event_types": ["theme_move", "new_theme", "stock_move"]
            },
            {
                "name": "stream:theme:feed",
                "description": "主题流 - 包含主题热度变化和生命周期事件",
                "example_event_types": ["theme_rank_change", "theme_emergence", "theme_decay"]
            },
            {
                "name": "stream:news:feed",
                "description": "新闻流 - 包含原始新闻和新闻处理事件",
                "example_event_types": ["news_ingested", "news_processed", "news_clustered"]
            },
            {
                "name": "stream:stock:feed",
                "description": "股票流 - 包含股票异动和资金流向事件",
                "example_event_types": ["stock_abnormal", "money_flow", "dragon_tiger"]
            }
        ],
        "primary_realtime_channel": {
            "type": "server_sent_events",
            "endpoint": "/api/intel/stream",
            "description": "主要实时数据通道，单向服务器到客户端推送"
        },
        "advanced_realtime_channels": {
            "websocket": {
                "endpoint": "/ws/realtime",
                "description": "可选高级功能，支持双向通信",
                "supported_commands": ["subscribe", "unsubscribe", "list_subscriptions", "ping", "get_stats"]
            }
        }
    }
