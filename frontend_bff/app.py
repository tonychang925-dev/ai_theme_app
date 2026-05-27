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
import httpx
import os

from frontend_bff.repositories.bff_repository import FrontendBffRepository
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

# P3 grey rollout flags (BFF-side only)
DAILY_SNAPSHOT_FLAG = "stock_processing_service.daily_snapshot.enabled"
PRE_MARKET_FLAG = "stock_processing_service.pre_market.enabled"
POST_MARKET_FLAG = "stock_processing_service.post_market.enabled"
QUALITY_GATE_REPORT_PATH = Path(os.getenv("QUALITY_GATE_REPORT_PATH", "tmp/quality_gate/gate_report.json"))


def _env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, str(default))).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _read_quality_gate_report() -> dict[str, Any]:
    if not QUALITY_GATE_REPORT_PATH.exists():
        return {"gate_passed": False, "reason": f"missing gate report: {QUALITY_GATE_REPORT_PATH}"}
    try:
        return json.loads(QUALITY_GATE_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"gate_passed": False, "reason": f"invalid gate report: {exc}"}


def _require_gate_for_flag(flag_name: str) -> None:
    if not _env_flag(flag_name, default=False):
        return
    report = _read_quality_gate_report()
    if not bool(report.get("gate_passed", False)):
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"quality gate not passed, block rollout flag={flag_name}",
                "gate_report_path": str(QUALITY_GATE_REPORT_PATH),
                "gate_report": report,
            },
        )


# 自定义JSON编码器处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

# 设置logger
logger = logging.getLogger(__name__)
WEB_APP_SERVICE_BASE_URL = str(os.getenv("WEB_APP_SERVICE_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
STOCK_PROCESSING_BASE_URL = str(os.getenv("STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090")).rstrip("/")
JYHF_CDP_SERVICE_BASE_URL = str(os.getenv("JYHF_CDP_SERVICE_BASE_URL", "http://127.0.0.1:8095")).rstrip("/")

def _sps_base_url() -> str:
    return STOCK_PROCESSING_BASE_URL

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


class PublishNotionProxyPayload(BaseModel):
    trade_date: str
    force: bool = False
    dry_run: bool = False


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
    candidate_trade_date: Optional[str] = None
    confirm_trade_date: Optional[str] = None
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


def _looks_like_numeric_theme_name(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.isdigit()


async def _resolve_theme_name_map(subject_keys: List[str], trade_date: Optional[date] = None) -> Dict[str, str]:
    return await bff_repo.resolve_theme_name_map(subject_keys, trade_date)


async def _normalize_result_theme_names(results: List[dict[str, Any]], trade_date: Optional[date] = None) -> None:
    subject_keys: List[str] = []
    for item in results:
        theme_info = item.get("theme_info") or {}
        subject_key = str(theme_info.get("subject_key") or "").strip()
        if subject_key:
            subject_keys.append(subject_key)
    theme_map = await _resolve_theme_name_map(subject_keys, trade_date)
    if not theme_map:
        return
    for item in results:
        theme_info = item.get("theme_info")
        if not isinstance(theme_info, dict):
            continue
        subject_key = str(theme_info.get("subject_key") or "").strip()
        if not subject_key:
            continue
        current_name = str(theme_info.get("theme_name") or "").strip()
        if not current_name or _looks_like_numeric_theme_name(current_name):
            theme_info["theme_name"] = theme_map.get(subject_key, subject_key)


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
    return await bff_repo.resolve_prev_trade_date(trade_date)


async def _resolve_next_trade_date(trade_date: date) -> date:
    next_day = await bff_repo.resolve_next_trade_date(trade_date)
    if not next_day:
        raise HTTPException(
            status_code=400,
            detail=f"未找到 {trade_date.isoformat()} 之后的下一个交易日，无法执行盘前确认",
        )
    return next_day


async def _infer_confirm_trade_date_from_candidate_trade_date(candidate_trade_date: date) -> Optional[date]:
    return await bff_repo.infer_confirm_trade_date_from_candidate_trade_date(candidate_trade_date)


async def _fetch_w2s_candidates(next_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    return await bff_repo.fetch_w2s_candidates_by_trade_date(
        candidate_trade_date=next_trade_date,
        limit=limit,
    )


async def _fetch_w2s_candidates_for_confirm_date(confirm_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    return await bff_repo.fetch_w2s_candidates_for_confirm_date(
        confirm_trade_date=confirm_trade_date,
        limit=limit,
    )


async def _count_w2s_candidates_for_confirm_date(confirm_trade_date: date) -> int:
    return await bff_repo.count_w2s_candidates_for_confirm_date(confirm_trade_date)


async def _count_w2s_formal_candidates_for_confirm_date(confirm_trade_date: date) -> int:
    return await bff_repo.count_w2s_formal_candidates_for_confirm_date(confirm_trade_date)


async def _fetch_w2s_candidates_by_ids(candidate_ids: List[int]) -> List[Dict[str, Any]]:
    return await bff_repo.fetch_w2s_candidates_by_ids(candidate_ids)


async def _fetch_w2s_signals(trade_date: date) -> Dict[int, Dict[str, Any]]:
    return await bff_repo.fetch_w2s_signals(trade_date)


async def _get_w2s_snapshot_coverage(trade_date: date) -> Dict[str, int]:
    return await bff_repo.get_w2s_snapshot_coverage(trade_date)


async def _has_w2s_snapshot_cache(trade_date: date) -> bool:
    coverage = await _get_w2s_snapshot_coverage(trade_date)
    candidate_cnt = int(coverage.get("candidate_cnt") or 0)
    snapshot_hit_cnt = int(coverage.get("snapshot_hit_cnt") or 0)
    # 候选为0时视为已满足，无需额外快照。
    if candidate_cnt <= 0:
        return True
    return snapshot_hit_cnt >= candidate_cnt


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


def _to_business_candidate_type(candidate_type: Any) -> str:
    code = str(candidate_type or "").strip().lower()
    mapping = {
        "strong_trend_repair": "强趋势回踩修复",
        "trend_repair": "趋势修复",
        "gap_support": "缺口承接位",
        "previous_low": "前低承接位",
        "previous_close": "昨收承接位",
        "fibonacci_support": "斐波那契承接位",
    }
    if code in mapping:
        return mapping[code]
    if code.startswith("pivot_"):
        return f"关键枢轴承接位（{code.replace('pivot_', '').upper()}）"
    if not code:
        return "--"
    return str(candidate_type)


def _to_business_decision(decision: Any) -> str:
    code = str(decision or "").strip().lower()
    mapping = {
        "confirmed": "通过",
        "watch": "观察",
        "reject": "不通过",
        "no_decision": "待判定",
    }
    return mapping.get(code, str(decision or ""))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _extract_w2s_detail_scores(replay: Dict[str, Any]) -> Dict[str, float]:
    candidate_evidence = replay.get("candidate_evidence") or {}
    signal_evidence = replay.get("signal_evidence") or {}
    cycle_values = ((candidate_evidence.get("cycle_diagnostics") or {}).get("values") or {})
    candidate_breakdown = ((candidate_evidence.get("scores") or {}).get("breakdown") or {})

    mainline_strength = _safe_float(
        replay.get("mainline_strength_score"),
        _safe_float(cycle_values.get("mainline_strength_score"), 0.0),
    )
    leader_score = _safe_float(cycle_values.get("leader_alive_score"), 0.0)
    support_strength = _safe_float(replay.get("support_strength"), _safe_float(cycle_values.get("support_strength"), 0.0))
    candidate_score = _safe_float(replay.get("candidate_score"), _safe_float(candidate_breakdown.get("candidate_score"), 0.0))
    confirmation_score = _safe_float(replay.get("confirmation_score"), _safe_float((signal_evidence.get("scores") or {}).get("confirmation_score"), 0.0))

    return {
        "mainline_strength": max(0.0, min(mainline_strength, 100.0)),
        "leader_score": max(0.0, min(leader_score, 100.0)),
        "support_strength": max(0.0, min(support_strength, 100.0)),
        "candidate_score": max(0.0, min(candidate_score, 100.0)),
        "confirmation_score": max(0.0, min(confirmation_score, 100.0)),
    }


async def _refresh_w2s_auction_snapshot(trade_date: date, min_required_stocks: int = 0) -> None:
    token = _resolve_tushare_token()
    base_max_stocks = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS", "80") or 80), 1)
    hard_cap = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS_HARD_CAP", "2000") or 2000), 1)
    dynamic_required = max(int(min_required_stocks or 0), 0)
    max_stocks = min(max(base_max_stocks, dynamic_required), hard_cap)
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
    candidate_type_raw = str(candidate.get("candidate_type") or "")
    candidate_type_label = _to_business_candidate_type(candidate_type_raw)
    decision_label = _to_business_decision(decision)
    screening_reason = (
        f"阶段一入池依据：{candidate_type_label}；"
        f"阶段二竞价确认：{signal_level or '--'} {decision_label}".strip()
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
            "candidate_type": candidate_type_raw,
            "candidate_type_label": candidate_type_label,
            "weak_type": str(candidate.get("weak_type") or ""),
            "support_type": str(candidate.get("support_type") or ""),
            "support_strength": float(candidate.get("support_strength") or 0.0),
            "expected_open_low": float(candidate.get("expected_open_low") or 0.0),
            "expected_open_high": float(candidate.get("expected_open_high") or 0.0),
            "signal_level": signal_level,
            "decision": decision,
            "decision_label": decision_label,
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
    hard_stage1_limit = 10
    default_stage1_limit = min(max(int(os.getenv("W2S_STAGE1_MAX_CANDIDATES", "10") or 10), 1), hard_stage1_limit)
    requested_stage1_limit = int(payload.limit or 0)
    if requested_stage1_limit > 0:
        stage1_limit = min(max(requested_stage1_limit, 1), hard_stage1_limit)
    else:
        stage1_limit = default_stage1_limit

    # 双日期协议：
    # - candidate_trade_date：盘后候选生成日
    # - confirm_trade_date：盘前确认日（候选 next_trade_date）
    candidate_trade_date = _parse_trade_date(payload.candidate_trade_date or payload.trade_date)
    requested_confirm_trade_date = (
        _parse_trade_date(payload.confirm_trade_date)
        if payload.confirm_trade_date
        else None
    )
    if requested_confirm_trade_date:
        confirm_trade_date = requested_confirm_trade_date
    elif run_stage1:
        confirm_trade_date = await _resolve_next_trade_date(candidate_trade_date)
    else:
        # 兼容旧前端：若仅传 trade_date，先按 confirm_date 尝试；无候选则回退按 candidate_date 推断。
        confirm_trade_date = candidate_trade_date
        strict_candidates = await _fetch_w2s_candidates_for_confirm_date(confirm_trade_date, limit=1)
        if not strict_candidates:
            inferred_confirm = await _infer_confirm_trade_date_from_candidate_trade_date(candidate_trade_date)
            if inferred_confirm:
                confirm_trade_date = inferred_confirm

    # 同交易日盘前阶段二门禁：9:25 前禁止竞价确认，避免拿到不完整竞价数据
    if run_stage2:
        now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
        if confirm_trade_date == now_cn.date():
            if now_cn.hour < 9 or (now_cn.hour == 9 and now_cn.minute < 25):
                raise HTTPException(status_code=400, detail="盘前9:25之后才能采集！")

    candidate_builder = WeakToStrongCandidateBuilder()
    auction_service = WeakToStrongAuctionService()

    stage1_summary: Dict[str, Any] = {"status": "skipped", "candidate_count": 0}
    stage2_summary: Dict[str, Any] = {"status": "skipped", "level_count": {"A": 0, "B": 0, "C": 0, "X": 0}}
    try:
        if run_stage1:
            # 盘后阶段：使用 candidate_trade_date 的收盘截面，为 confirm_trade_date 生成候选池。
            source_trade_date = candidate_trade_date
            now_cn_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            prefer_cached_historical = str(os.getenv("W2S_PREFER_CACHED_HISTORICAL", "1")).lower() in {"1", "true", "yes", "on"}
            should_try_cached_first = prefer_cached_historical and source_trade_date < now_cn_date
            if should_try_cached_first:
                existing_count = await _count_w2s_candidates_for_confirm_date(confirm_trade_date)
                if existing_count > 0:
                    stage1_summary = {
                        "status": "cached",
                        "source_trade_date": source_trade_date.isoformat(),
                        "next_trade_date": confirm_trade_date.isoformat(),
                        "candidate_count": existing_count,
                        "candidate_limit": stage1_limit,
                        "cache_policy": "historical_prefer_cached",
                    }
                else:
                    stage1_summary = {"status": "cache_miss"}
            if stage1_summary.get("status") == "cached":
                logger.info(
                    "弱转强盘后候选命中历史缓存: candidate_trade_date=%s confirm_trade_date=%s count=%s",
                    source_trade_date.isoformat(),
                    confirm_trade_date.isoformat(),
                    stage1_summary.get("candidate_count"),
                )
            else:
                try:
                    build_result = await asyncio.wait_for(
                        candidate_builder.build(
                            source_trade_date,
                            next_trade_date=confirm_trade_date,
                            max_candidates=stage1_limit,
                        ),
                        timeout=30.0
                    )
                    stage1_summary = {
                        "status": "success",
                        "source_trade_date": source_trade_date.isoformat(),
                        "next_trade_date": confirm_trade_date.isoformat(),
                        "candidate_count": int(build_result.total_inserted),
                        "candidate_limit": stage1_limit,
                    }
                except asyncio.TimeoutError:
                    logger.error(f"弱转强候选构建超时(30s)，跳过构建，使用现有候选池数据")
                    stage1_summary = {
                        "status": "timeout",
                        "source_trade_date": source_trade_date.isoformat(),
                        "next_trade_date": confirm_trade_date.isoformat(),
                        "candidate_count": 0,
                        "candidate_limit": stage1_limit,
                    }
                except Exception as e:
                    logger.error(f"弱转强候选构建失败: {e}")
                    stage1_summary = {
                        "status": "error",
                        "source_trade_date": source_trade_date.isoformat(),
                        "next_trade_date": confirm_trade_date.isoformat(),
                        "candidate_count": 0,
                        "candidate_limit": stage1_limit,
                        "error": str(e)[:200]
                    }

        if run_stage2:
            now_cn = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            refresh_historical = str(os.getenv("W2S_REFRESH_HISTORICAL", "0")).lower() in {"1", "true", "yes", "on"}
            formal_candidate_count = await _count_w2s_formal_candidates_for_confirm_date(confirm_trade_date)
            coverage_before = await _get_w2s_snapshot_coverage(confirm_trade_date)
            is_full_coverage_before = int(coverage_before.get("snapshot_hit_cnt") or 0) >= int(coverage_before.get("candidate_cnt") or 0)
            should_refresh_snapshot = (
                confirm_trade_date >= now_cn
                or refresh_historical
                or not is_full_coverage_before
            )
            if should_refresh_snapshot:
                await _refresh_w2s_auction_snapshot(
                    confirm_trade_date,
                    min_required_stocks=formal_candidate_count,
                )
            coverage_after = await _get_w2s_snapshot_coverage(confirm_trade_date)
            confirm_result = await auction_service.confirm(confirm_trade_date)
            stage2_summary = {
                "status": "success",
                "confirm_trade_date": confirm_trade_date.isoformat(),
                "snapshot_refresh_skipped": not should_refresh_snapshot,
                "snapshot_candidate_cnt": int(coverage_after.get("candidate_cnt") or 0),
                "snapshot_hit_cnt": int(coverage_after.get("snapshot_hit_cnt") or 0),
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
    if run_stage2:
        # 阶段二严格口径：候选必须来自 next_trade_date = confirm_trade_date
        candidates = await _fetch_w2s_candidates_for_confirm_date(confirm_trade_date, limit=candidate_limit)
    else:
        # 阶段一展示优先与阶段二保持同口径：next_trade_date = confirm_trade_date
        # 仅在历史兼容场景（严格口径空）时才回退到旧口径，避免页面出现“跳变”。
        candidates = await _fetch_w2s_candidates_for_confirm_date(confirm_trade_date, limit=candidate_limit)
        if not candidates:
            candidates = await _fetch_w2s_candidates(candidate_trade_date, limit=candidate_limit)
    signals = await _fetch_w2s_signals(confirm_trade_date) if run_stage2 else {}
    results: List[Dict[str, Any]] = []
    if run_stage2:
        # 两阶段结果以阶段二信号为主，避免受候选列表 limit 截断导致“有信号但显示0条”。
        candidate_map: Dict[int, Dict[str, Any]] = {
            int(c.get("id") or 0): c for c in candidates if int(c.get("id") or 0) > 0
        }
        if signals:
            missing_candidate_ids = [cid for cid in signals.keys() if cid not in candidate_map]
            if missing_candidate_ids:
                for row in await _fetch_w2s_candidates_by_ids(missing_candidate_ids):
                    cid = int(row.get("id") or 0)
                    if cid > 0:
                        candidate_map[cid] = row
        sorted_signals = sorted(
            signals.items(),
            key=lambda kv: float((kv[1] or {}).get("confirmation_score") or 0.0),
            reverse=True,
        )
        included_candidate_ids: set[int] = set()
        for candidate_id, signal in sorted_signals:
            candidate = candidate_map.get(int(candidate_id))
            if candidate is None:
                continue
            signal_level = str((signal or {}).get("signal_level") or "").upper()
            decision = str((signal or {}).get("decision") or "").lower()
            results.append(_build_w2s_result_row(candidate, signal, len(results) + 1))
            included_candidate_ids.add(int(candidate_id))

        # observe_only 候选不参与正式竞价信号，但必须保留在结果中供用户继续观察。
        for candidate in sorted(
            candidates,
            key=lambda c: float(c.get("candidate_score") or 0.0),
            reverse=True,
        ):
            candidate_id = int(candidate.get("id") or 0)
            if candidate_id <= 0 or candidate_id in included_candidate_ids:
                continue
            if str(candidate.get("pool_entry_type") or "").lower() != "observe_only":
                continue
            results.append(_build_w2s_result_row(candidate, None, len(results) + 1))
    else:
        for idx, candidate in enumerate(candidates, start=1):
            candidate_id = int(candidate.get("id") or 0)
            signal = signals.get(candidate_id)
            results.append(_build_w2s_result_row(candidate, signal, idx))
    results.sort(key=lambda x: float(x.get("composite_score") or 0.0), reverse=True)
    for i, row in enumerate(results, start=1):
        row["rank_position"] = i

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    effective_trade_date = confirm_trade_date if run_stage2 else candidate_trade_date
    await _normalize_result_theme_names(results, effective_trade_date)
    confirm_input_candidate_count = int(stage2_summary.get("total_candidates") or 0) if run_stage2 else 0
    return {
        "job_id": f"w2s_{payload.strategy_id}_{effective_trade_date.isoformat()}_{int(time.time())}",
        "status": "completed",
        "results": results,
        "total_count": len(results),
        "trade_date": effective_trade_date.isoformat(),
        "execution_time_ms": elapsed_ms,
        "llm_review_status": "disabled_for_two_stage",
        "llm_summary": {"pass": 0, "watch": 0, "reject": 0, "failed": 0},
        "diagnostics": {
            "two_stage": True,
            "strategy_name": strategy_name,
            "run_stage1": run_stage1,
            "run_stage2": run_stage2,
            "candidate_trade_date": candidate_trade_date.isoformat(),
            "confirm_trade_date": confirm_trade_date.isoformat(),
            "snapshot_trade_date": confirm_trade_date.isoformat(),
            "stage1": stage1_summary,
            "stage2": stage2_summary,
            "candidate_pool_count": len(candidates),
            "confirm_input_candidate_count": confirm_input_candidate_count,
            "confirm_filtered_out_count": max(len(candidates) - confirm_input_candidate_count, 0) if run_stage2 else 0,
            "snapshot_hit_count": int(stage2_summary.get("total_candidates") or 0) if run_stage2 else 0,
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
@app.api_route("/api/v2/stock-screener/strategies", methods=["GET", "HEAD"])
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
@app.post("/api/v2/stock-screener/strategies")
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
@app.put("/api/v2/stock-screener/strategies/{strategy_id}")
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
@app.delete("/api/v2/stock-screener/strategies/{strategy_id}")
async def delete_stock_screener_strategy(strategy_id: str):
    ok = await stock_screener_repo.delete_strategy(strategy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="strategy not found")
    return {"ok": True, "strategy_id": strategy_id}


@app.post("/api/stock-screener/execute")
@app.post("/api/v2/stock-screener/execute")
async def execute_stock_screener(payload: ScreenerExecutePayload):
    started = time.perf_counter()
    requested_trade_date = _parse_trade_date(payload.trade_date)
    trade_date = requested_trade_date
    fallback_applied = False
    fallback_reason: Optional[str] = None

    strategy = await stock_screener_repo.get_strategy(payload.strategy_id)
    if _is_weak_to_strong_strategy(strategy, payload.strategy_id):
        weak_to_strong_date = _parse_trade_date(payload.candidate_trade_date or payload.trade_date)
        return await _execute_weak_to_strong_two_stage(payload, weak_to_strong_date)

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
    await _normalize_result_theme_names(serialized_results, trade_date)
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
@app.get("/api/v2/stock-screener/executions/{job_id}")
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
@app.get("/api/v2/stock-screener/results/{result_id}")
async def get_stock_screener_result_detail(
    result_id: str,
    view: Optional[str] = Query(default=None, description="详情视角：candidate|confirm"),
):
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
        detail_view = str(view or "").strip().lower()
        if detail_view not in {"candidate", "confirm"}:
            detail_view = "confirm" if replay.get("signal_level") else "candidate"

        signal_evidence = replay.get("signal_evidence") or {}
        score_payload = ((signal_evidence or {}).get("scores") or {})
        detail_scores = _extract_w2s_detail_scores(replay)
        candidate_score = detail_scores["candidate_score"]
        confirmation_score = detail_scores["confirmation_score"]
        cycle_score = confirmation_score if detail_view == "confirm" and confirmation_score > 0 else candidate_score
        mainline_strength = detail_scores["mainline_strength"]
        leader_score = detail_scores["leader_score"]
        support_strength = detail_scores["support_strength"]
        technical_score = support_strength
        composite_score = round((mainline_strength * 0.35) + (cycle_score * 0.30) + (leader_score * 0.20) + (technical_score * 0.15), 2)

        payload = {
            "result_id": result_id,
            "stock_id": replay.get("stock_id", ""),
            "stock_name": replay.get("stock_name", ""),
            "composite_score": composite_score,
            "dimension_scores": {
                "mainline": round(mainline_strength, 2),
                "cycle": cycle_score,
                "leader": round(leader_score, 2),
                "technical": round(technical_score, 2),
            },
            "rank_position": None,
            "theme_info": {
                "subject_key": str(replay.get("subject_key") or ""),
                "theme_name": str(replay.get("theme_name") or replay.get("subject_key") or ""),
            },
            "dimension_details": {
                "mainline": {
                    "strength_score": round(mainline_strength, 2),
                    "heat_rank": 0.0,
                    "capital_attention": 0.0,
                    "reasoning": "来自候选池主线强度评分（mainline_strength_score）。",
                },
                "cycle": {
                    "stage_score": float(score_payload.get("pattern_stability") or 0.0) if detail_view == "confirm" else candidate_score,
                    "duration_score": float(score_payload.get("last_minute_grab") or 0.0) if detail_view == "confirm" else 0.0,
                    "stability_score": float(score_payload.get("plate_follow") or 0.0) if detail_view == "confirm" else 0.0,
                    "reasoning": (
                        "盘前确认视角：在昨日候选基础上叠加今日竞价确认分。"
                        if detail_view == "confirm"
                        else "盘后候选视角：仅展示昨日入池依据与候选分。"
                    ),
                },
                "leader": {
                    "position_score": round(leader_score, 2),
                    "leading_effect": round(leader_score, 2),
                    "capital_recognition": 0.0,
                    "reasoning": "来自候选证据中的龙头存活分（leader_alive_score）。",
                },
                "technical": {
                    "abnormal_score": 0.0,
                    "pattern_score": round(support_strength, 2),
                    "volume_price_score": round(support_strength, 2),
                    "reasoning": "技术形态分以K线支撑强度（support_strength）为核心。",
                },
            },
            "created_at": datetime.now().isoformat(),
            "weak_to_strong_replay": replay,
        }
        replay_candidate_type = replay.get("candidate_type") or replay.get("pool_entry_type") or ""
        replay_decision = replay.get("decision") or ""
        candidate_reason = (
            f"阶段一入池依据：{_to_business_candidate_type(replay_candidate_type)}；"
            f"候选分：{candidate_score:.2f}"
        )
        confirm_reason = (
            f"{candidate_reason}；"
            f"阶段二竞价确认：{replay.get('signal_level', '--')} {_to_business_decision(replay_decision)}；"
            f"确认分：{confirmation_score:.2f}"
        )
        payload["screening_reason"] = confirm_reason if detail_view == "confirm" else candidate_reason
        payload["weak_to_strong"] = {
            "detail_view": detail_view,
            "candidate_type": str(replay_candidate_type or ""),
            "candidate_type_label": _to_business_candidate_type(replay_candidate_type),
            "decision": str(replay_decision or ""),
            "decision_label": _to_business_decision(replay_decision),
            "signal_level": str(replay.get("signal_level") or ""),
            "confirmation_score": confirmation_score,
            "candidate_score": candidate_score,
            "support_type": str(replay.get("support_type") or ""),
            "support_strength": support_strength,
            "candidate_trade_date": str(replay.get("candidate_trade_date") or ""),
            "confirm_trade_date": str(replay.get("confirm_trade_date") or ""),
        }
        replay_trade_date = replay.get("confirm_trade_date") or replay.get("trade_date")
        parsed_replay_trade_date = _parse_trade_date(str(replay_trade_date)) if replay_trade_date else None
        await _normalize_result_theme_names([payload], parsed_replay_trade_date)
        return payload

    detail = await stock_screener_service.get_result_detail(result_id)
    if not detail:
        raise HTTPException(status_code=404, detail="result not found")

    payload = _serialize_screening_result(detail)
    await _normalize_result_theme_names([payload], detail.trade_date if getattr(detail, "trade_date", None) else None)
    payload["dimension_details"] = getattr(detail, "dimension_details", None)
    payload["created_at"] = detail.created_at.isoformat() if detail.created_at else None
    llm_review = await stock_screener_repo.get_llm_review(result_id)
    if llm_review:
        payload["llm_review"] = llm_review
    return payload


@app.get("/api/stock-screener/history")
@app.get("/api/v2/stock-screener/history")
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
@app.get("/api/v2/stock-screener/favorites")
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
@app.post("/api/v2/stock-screener/favorites")
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
@app.put("/api/v2/stock-screener/favorites/{favorite_id}")
async def update_stock_screener_favorite(favorite_id: str, payload: ScreenerFavoriteUpdatePayload):
    ok = await stock_screener_repo.update_favorite(favorite_id, payload.notes, payload.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.delete("/api/stock-screener/favorites/{favorite_id}")
@app.delete("/api/v2/stock-screener/favorites/{favorite_id}")
async def delete_stock_screener_favorite(favorite_id: str):
    ok = await stock_screener_repo.remove_favorite(favorite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.get("/api/stock-screener/statistics")
@app.get("/api/v2/stock-screener/statistics")
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
@app.post("/api/v2/stock-screener/export")
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
@app.get("/api/v2/intel/feed")
async def get_intel_feed(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    _require_gate_for_flag(DAILY_SNAPSHOT_FLAG)
    # 代理到 SPS /api/v1/intel_feed
    feed_date = date
    if not feed_date:
        try:
            defaults_url = f"{_sps_base_url()}/api/v1/intel_feed/defaults"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(defaults_url)
                resp.raise_for_status()
                feed_date = resp.json().get("latest_intel_date")
        except Exception:
            feed_date = None
    if not feed_date:
        return {"items": [], "count": 0, "date": None, "session": session, "type": type,
                "diagnostics": {"partial": True, "source": "no_date_available"}}

    url = f"{_sps_base_url()}/api/v1/intel_feed"
    params = {"feed_date": feed_date, "session": session, "item_type": type,
              "subject_key": subject_key, "stock_id": stock_id, "limit": limit}
    q = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=q)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"items": [], "count": 0, "date": feed_date, "session": session, "type": type,
                "diagnostics": {"partial": True, "source": "sps_unavailable"}}


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump()
    return model.dict()


@app.get("/api/intel/strong-stocks/watch")
@app.get("/api/v2/intel/strong-stocks/watch")
@app.get("/api/v2/strong_watch/watch")
async def get_strong_stock_watch(
    date: Optional[str] = Query(default=None),
    window_days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=1000, ge=1, le=5000),
    latest_per_stock: bool = Query(default=True),
    include_removed: bool = Query(default=False),
    stock_id: Optional[str] = Query(default=None),
):
    try:
        return await bff_repo.fetch_strong_stock_watch_view(
            trade_date=date,
            window_days=window_days,
            limit=limit,
            latest_per_stock=latest_per_stock,
            include_removed=include_removed,
            stock_id=stock_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/intel/stream")
@app.get("/api/v2/intel/stream")
async def get_intel_stream(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    _require_gate_for_flag(DAILY_SNAPSHOT_FLAG)
    async def event_generator():
        seen_item_ids: set[str] = set()
        heartbeat_interval = 15
        poll_interval = 5
        elapsed = 0
        sps_url = f"{_sps_base_url()}/api/v1/intel_feed"

        async def _poll_sps():
            params = {"feed_date": date, "session": session, "item_type": type,
                      "subject_key": subject_key, "stock_id": stock_id, "limit": limit}
            q = {k: v for k, v in params.items() if v is not None and v != ""}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(sps_url, params=q)
                resp.raise_for_status()
                return resp.json()

        while True:
            try:
                payload = await _poll_sps()
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
@app.get("/api/v2/intel/stream/realtime")
async def get_intel_stream_realtime(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|event_review|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    _require_gate_for_flag(DAILY_SNAPSHOT_FLAG)
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


async def _proxy_web_app_v2(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{WEB_APP_SERVICE_BASE_URL}{path}"
    q = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url, params=q)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "WEB_APP_UPSTREAM_UNREACHABLE",
                "message": str(exc),
                "upstream": url,
            },
        )


@app.get("/api/v2/workspace/theme-radar")
async def proxy_workspace_theme_radar(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all"),
    limit: int = Query(default=30, ge=1, le=200),
):
    return await _proxy_web_app_v2(
        "/api/v2/workspace/theme-radar",
        {"date": date, "session": session, "limit": limit},
    )


@app.get("/api/v2/workspace/intel-context")
async def proxy_workspace_intel_context(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await _proxy_web_app_v2(
        "/api/v2/workspace/intel-context",
        {
            "date": date,
            "session": session,
            "subject_key": subject_key,
            "stock_id": stock_id,
            "limit": limit,
        },
    )


@app.get("/api/v2/workspace/market-validation")
async def proxy_workspace_market_validation(
    trade_date: str = Query(...),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
):
    return await _proxy_web_app_v2(
        "/api/v2/workspace/market-validation",
        {"trade_date": trade_date, "subject_key": subject_key, "stock_id": stock_id},
    )


@app.get("/api/theme-workspace/{subject_key}")
@app.get("/api/v2/theme-workspace/{subject_key}")
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
    # 新链：代理到 SPS /api/v1/theme_workspace/{subject_key}
    url = f"{_sps_base_url()}/api/v1/theme_workspace/{subject_key}"
    params = {
        "trade_date": trade_date,
        "include_history": str(include_history).lower(),
        "include_children": str(include_children).lower(),
        "include_stocks": str(include_stocks).lower(),
        "include_leaders": str(include_leaders).lower(),
        "stock_mapping_scope": stock_mapping_scope,
        "history_limit": history_limit,
        "children_limit": children_limit,
        "stocks_limit": stocks_limit,
    }
    q = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=q)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail=f"SPS unreachable: {exc}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")
        raise HTTPException(status_code=502, detail=f"SPS error: {exc.response.status_code}")
        raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")
    return payload


@app.get("/api/stock-workspace/{stock_id}")
@app.get("/api/v2/stock-workspace/{stock_id}")
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
@app.get("/api/v2/recap")
async def get_recap(
    date: str = Query(...),
    report_type: str = Query(default="post_market", pattern="^(pre_market|post_market)$"),
):
    if report_type == "pre_market":
        _require_gate_for_flag(PRE_MARKET_FLAG)
    else:
        _require_gate_for_flag(POST_MARKET_FLAG)
    return await bff_repo.fetch_recap_view(
        trade_date=date,
        report_type=report_type,
    )


@app.get("/api/recap/defaults")
@app.get("/api/v2/recap/defaults")
async def get_recap_defaults():
    return await bff_repo.fetch_recap_defaults()


@app.post("/api/v2/recap/publish-notion")
async def publish_recap_to_notion_proxy(payload: PublishNotionProxyPayload):
    _require_gate_for_flag(POST_MARKET_FLAG)

    url = f"{_sps_base_url()}/api/v1/recap/publish-notion"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=_model_to_dict(payload))
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SPS_NOTION_PUBLISH_UNAVAILABLE",
                "message": str(exc),
                "upstream": url,
            },
        )


@app.get("/api/v2/daily-review-v2")
async def get_daily_review_v2_proxy(date: str = Query(...)):
    _require_gate_for_flag(POST_MARKET_FLAG)
    url = f"{_sps_base_url()}/api/v2/daily-review-v2"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params={"date": date})
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SPS_DAILY_REVIEW_V2_UNAVAILABLE",
                "message": str(exc),
                "upstream": url,
            },
        )


@app.post("/api/v2/post-market/daily-review-v2/generate")
async def generate_daily_review_v2_proxy(payload: dict[str, Any] | None = None):
    _require_gate_for_flag(POST_MARKET_FLAG)
    url = f"{_sps_base_url()}/api/v2/post-market/daily-review-v2/generate"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload or {})
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SPS_DAILY_REVIEW_V2_GENERATE_UNAVAILABLE",
                "message": str(exc),
                "upstream": url,
            },
        )


@app.get("/api/collection/availability")
@app.get("/api/v2/collection/availability")
async def get_collection_availability(trade_date: Optional[str] = Query(default=None)):
    url = f"{_sps_base_url()}/api/v1/collection/availability"
    params = {"trade_date": trade_date} if trade_date else None
    return await _proxy_sps_collection("GET", url, params=params)


@app.post("/api/collection/start")
@app.post("/api/v2/collection/start")
async def start_collection(payload: CollectionStartRequest):
    url = f"{_sps_base_url()}/api/v1/collection/start"
    return await _proxy_sps_collection("POST", url, json_payload=_model_to_dict(payload))


@app.get("/api/collection/status")
@app.get("/api/v2/collection/status")
async def get_collection_status(job_id: str = Query(...)):
    url = f"{_sps_base_url()}/api/v1/collection/status"
    return await _proxy_sps_collection("GET", url, params={"job_id": job_id})


@app.post("/api/collection/cancel")
@app.post("/api/v2/collection/cancel")
async def cancel_collection(payload: CollectionJobActionRequest):
    url = f"{_sps_base_url()}/api/v1/collection/cancel"
    return await _proxy_sps_collection("POST", url, json_payload=_model_to_dict(payload))


@app.post("/api/collection/continue")
@app.post("/api/v2/collection/continue")
async def continue_collection(payload: CollectionJobActionRequest):
    url = f"{_sps_base_url()}/api/v1/collection/continue"
    return await _proxy_sps_collection("POST", url, json_payload=_model_to_dict(payload))


async def _proxy_sps_collection(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.request(method, url, params=params, json=json_payload)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SPS_COLLECTION_UNAVAILABLE",
                "message": str(exc),
                "upstream": url,
            },
        )


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


async def _proxy_jyhf_cdp(method: str, path: str, *, params: dict | None = None, payload: dict | None = None, timeout: float = 15.0) -> dict:
    """Proxy request to jyhf_cdp_service."""
    url = f"{JYHF_CDP_SERVICE_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            resp = await http.request(method.upper(), url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "JYHF_CDP_SERVICE_UNAVAILABLE", "message": str(exc), "upstream": url},
        ) from exc


@app.get("/api/v2/realtime/jyhf-cdp/status")
@app.get("/api/realtime/jyhf-cdp/status")
async def jyhf_cdp_status():
    return await _proxy_jyhf_cdp("GET", "/status")


@app.post("/api/v2/realtime/jyhf-cdp/start")
@app.post("/api/realtime/jyhf-cdp/start")
async def jyhf_cdp_start(payload: dict | None = None):
    return await _proxy_jyhf_cdp("POST", "/collector/start", payload=payload or {}, timeout=30.0)


@app.post("/api/v2/realtime/jyhf-cdp/stop")
@app.post("/api/realtime/jyhf-cdp/stop")
async def jyhf_cdp_stop(payload: dict | None = None):
    return await _proxy_jyhf_cdp("POST", "/collector/stop", payload=payload or {}, timeout=30.0)


@app.post("/api/v2/realtime/jyhf-cdp/restart")
@app.post("/api/realtime/jyhf-cdp/restart")
async def jyhf_cdp_restart(payload: dict | None = None):
    await _proxy_jyhf_cdp("POST", "/collector/stop", payload=payload or {}, timeout=15.0)
    return await _proxy_jyhf_cdp("POST", "/collector/start", payload=payload or {}, timeout=30.0)


@app.get("/api/v2/realtime/jyhf-cdp/logs")
@app.get("/api/realtime/jyhf-cdp/logs")
async def jyhf_cdp_logs(lines: int = Query(default=300, ge=20, le=2000)):
    return await _proxy_jyhf_cdp("GET", "/collector/logs", params={"lines": lines})


@app.get("/api/realtime/collector/status")
@app.get("/api/v2/realtime/collector/status")
async def get_realtime_collector_status():
    result = await _run_cmd(
        ["bash", str(_project_root() / "scripts" / "status_realtime_stack.sh")],
        timeout_sec=30,
    )
    return result


@app.post("/api/realtime/collector/start")
@app.post("/api/v2/realtime/collector/start")
async def start_realtime_collector(payload: RealtimeCollectorActionRequest):
    result = await _run_cmd(
        _build_start_cmd(with_frontend=payload.with_frontend, restart=payload.restart),
        timeout_sec=150,
    )
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/api/realtime/collector/stop")
@app.post("/api/v2/realtime/collector/stop")
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
@app.get("/api/v2/realtime/collector/logs")
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
