from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import logging
import os
import fcntl
import re
import sys
import time
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic import Field
from datetime import datetime, timezone as _tz
import httpx

# Startup watermark — any "running" job status with updated_at before this
# timestamp belongs to a previous process and is automatically stale.
_STARTUP_TS = datetime.now(_tz.utc)
import uuid

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
from stock_processing_service.application.orchestrators.bootstrap import build_container
from theme_service.repositories.phase1_read_repository import Phase1ReadRepository
from stock_processing_service.application.services.intel_new_chain_adapter import NewChainIntelFeedAdapter
from stock_processing_service.application.services.realtime_stack_manager import RealtimeStackManager
from stock_processing_service.application.services.event_driven_opportunity_builder import (
    EventDrivenOpportunityBuilder,
)
from stock_processing_service.application.services.pre_market_brief_builder import PreMarketBriefBuilder
from stock_processing_service.application.services.trade_plan_review_service import TradePlanReviewService
from stock_processing_service.application.jobs.collection_job_manager import CollectionJobManager
from stock_processing_service.publishers.notion_post_market_recap_publisher import NotionPostMarketRecapPublisher
from stock_processing_service.integrations.notion.notion_trade_plan_repository import NotionTradePlanRepository
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate
from stock_processing_service.domain.services.w2s_confirm_service import W2SConfirmService
from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.models import PreMarketAuctionSnapshot
from stock_service.services.auction_signal_service import AuctionCandidateInput
from stock_service.services.auction_snapshot_builder_service import AuctionSnapshotBuilderService

try:
    from redis.asyncio import Redis as AsyncRedis
except Exception:  # pragma: no cover - import fallback only
    AsyncRedis = None


logger = logging.getLogger(__name__)

PRE_MARKET_CONFIRM_NOT_READY_MESSAGE = "9:25分之后才能进行盘前确认！"
REALTIME_AUCTION_CACHE_PREFIX = "sps:w2s:pre_market_auction"
SPS_SINGLETON_LOCK_PATH = Path(os.getenv("SPS_SINGLETON_LOCK_PATH", "/tmp/ai_theme_app_sps.lock"))


def _db_name() -> str:
    # Phase 5: production uses single read/write database.
    return str(os.getenv("PG_DATABASE") or os.getenv("DB_NAME") or "stock_data_test")


def _redis_url() -> str:
    v = (os.getenv("REDIS_URL") or "").strip().strip("'\"")
    if not v:
        return "redis://127.0.0.1:6379/0"
    if not v.startswith(("redis://", "rediss://", "unix://")):
        raise RuntimeError(f"Invalid REDIS_URL: {v!r}")
    return v


def _acquire_sps_singleton_lock() -> int:
    """Enforce one live SPS instance across all ports."""
    SPS_SINGLETON_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(SPS_SINGLETON_LOCK_PATH), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise RuntimeError(
            f"SPS singleton lock already held: {SPS_SINGLETON_LOCK_PATH}. "
            "Only one stock_processing_service.api_app instance may run at a time."
        ) from exc
    os.ftruncate(fd, 0)
    os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
    os.fsync(fd)
    return fd


def _release_sps_singleton_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        os.close(fd)
    except Exception:
        pass


async def _init_stock_match_engine_background(app: FastAPI) -> None:
    """后台懒加载 StockMatchEngine，不阻塞 SPS 端口监听。"""
    status = app.state.match_engine_status
    status["loading"] = True
    try:
        from theme_service.services.stock_match_engine import StockMatchEngine
        import aiohttp

        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not deepseek_key:
            status["error"] = "DEEPSEEK_API_KEY not set"
            logger.warning("StockMatchEngine background init skipped: DEEPSEEK_API_KEY not set")
            return

        # 使用短超时 + TCPConnector 避免 SSL 层卡死阻塞事件循环
        _connector = aiohttp.TCPConnector(
            force_close=True,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

        class DeepSeekLLM:
            async def chat_completion(self, messages, temperature=0.1, max_tokens=512):
                headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
                payload = {"model": "deepseek-chat", "messages": messages,
                           "temperature": temperature, "max_tokens": max_tokens, "stream": False}
                timeout = aiohttp.ClientTimeout(
                    total=30, connect=10, sock_connect=10, sock_read=25,
                )
                async with aiohttp.ClientSession(connector=_connector, timeout=timeout) as s:
                    async with s.post("https://api.deepseek.com/v1/chat/completions",
                                      headers=headers, json=payload) as r:
                        data = await r.json()
                        return {"content": data["choices"][0]["message"]["content"]}

        engine = StockMatchEngine(llm_client=DeepSeekLLM())
        await engine.initialize()
        app.state.match_engine = engine
        status["ready"] = True
        status["loading"] = False
        logger.info("StockMatchEngine initialized (DeepSeek LLM) for mobile news-recommend")
    except Exception as exc:
        status["error"] = str(exc)
        status["loading"] = False
        logger.warning("StockMatchEngine background init failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.singleton_lock_fd = _acquire_sps_singleton_lock()
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=_db_name())
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    # P1-C: DB readiness hard guard — enforce single-DB stock_data_test
    write_db = _db_name()
    read_db = os.getenv("READ_PG_DATABASE", os.getenv("PG_DATABASE", ""))
    if not read_db:
        read_db = write_db
    force_single = os.getenv("FORCE_SINGLE_DB", "true").lower()
    same_db = (write_db == read_db)
    db_info = {
        "db_mode": "single_test" if (same_db and write_db == "stock_data_test") else "unknown",
        "write_db": write_db,
        "read_db": read_db,
        "same_db": same_db,
    }
    if force_single in ("1", "true", "yes", "on"):
        if write_db != "stock_data_test" or read_db != "stock_data_test":
            raise RuntimeError(
                f"DB guard: FORCE_SINGLE_DB=true but write_db={write_db}, read_db={read_db}. "
                f"Both must be stock_data_test. Set FORCE_SINGLE_DB=false to bypass."
            )
    logger.warning(
        "[DB_GUARD] db_mode=%s write_db=%s read_db=%s same_db=%s",
        db_info["db_mode"], write_db, read_db, same_db,
    )
    app.state.db_info = db_info

    facade = _ReplayDatabaseStockFacade(gw)
    app.state.read_port = StockReadGatewayAdapter(facade)
    app.state.gateway = gw
    app.state.container = build_container(facade)
    app.state.phase1_repo = Phase1ReadRepository()
    app.state.intel_adapter = NewChainIntelFeedAdapter(gw)
    # StockMatchEngine — 已有完整管线：LLM提取 → Gate匹配 → Rerank → Judge
    # 默认不阻塞 SPS 启动；设置 SPS_ENABLE_STOCK_MATCH_ENGINE=true 启用（后台懒加载）
    app.state.match_engine = None
    app.state.match_engine_status = {"enabled": False, "ready": False, "loading": False, "error": None}
    if os.environ.get("SPS_ENABLE_STOCK_MATCH_ENGINE", "false").lower() in ("1", "true", "yes", "on"):
        app.state.match_engine_status["enabled"] = True
        # 在独立线程中运行避免 SSL 阻塞事件循环（同 jyhf_market 问题）
        def _init_match_engine_sync():
            import asyncio as _asyncio
            _asyncio.run(_init_stock_match_engine_background(app))
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _init_match_engine_sync)
    else:
        logger.info("StockMatchEngine disabled (set SPS_ENABLE_STOCK_MATCH_ENGINE=true to enable)")
    from stock_processing_service.application.services.collection_task_registry import get_default_registry
    app.state.collection_job_manager = CollectionJobManager(
        container=app.state.container,
        registry=get_default_registry(),
    )
    # Phase 5: new-chain realtime stack manager
    app.state.realtime_manager = RealtimeStackManager(
        redis_url=_redis_url(),
        write_db=_db_name(),
    )
    app.state.w2s_alert_status = {
        "enabled": False,
        "running": False,
        "phase": "idle",
        "trade_date": None,
        "candidate_trade_date": None,
        "last_run_at": None,
        "last_success_at": None,
        "last_error": None,
        "last_built": 0,
        "last_pushed": 0,
        "total_built": 0,
        "total_pushed": 0,
    }
    # P1-C: SPS 启动时清理上一次 run 遗留的僵尸 consumer（进程已死但 Redis 仍记录）
    async def _cleanup_zombie_consumers_once():
        await asyncio.sleep(3)  # 等 Redis 连接就绪
        try:
            import redis.asyncio as aioredis
            from database_service.streams.utils.consumer_group_manager import ConsumerGroupManager
            r = aioredis.from_url(_redis_url(), decode_responses=True)
            mgr = ConsumerGroupManager(r)
            result = await mgr.cleanup_stale_consumers(idle_minutes=10, execute=True)
            await r.aclose()
            if result["stale_consumers_deleted"]:
                logger.warning(
                    "ZOMBIE_CONSUMER_CLEANUP: deleted=%d reclaimed=%d pending",
                    result["stale_consumers_deleted"], result["pending_reclaimed"],
                )
            else:
                logger.info("Consumer cleanup: no zombies found")
        except Exception as exc:
            logger.warning("Consumer cleanup skipped: %s", exc)
    asyncio.create_task(_cleanup_zombie_consumers_once())

    # 默认不在 SPS 初始化时自动拉起实时管线。
    # 实时采集应由页面按钮或显式运维命令启动，避免服务重启时产生隐藏副作用。
    if os.environ.get("SPS_AUTO_START_REALTIME_STACK", "false").lower() in ("1", "true", "yes", "on"):
        asyncio.create_task(_auto_start_realtime_stack(app))
    else:
        logger.info("Realtime stack auto-start disabled (set SPS_AUTO_START_REALTIME_STACK=true to enable)")
    # P1-G: 支撑位突破检测后台任务（盘中自动运行）
    _kline_alert_task = asyncio.create_task(_run_kline_break_detector_loop(app))
    _w2s_alert_task = None
    if os.environ.get("SPS_ENABLE_W2S_ALERT_LOOP", "true").lower() in ("1", "true", "yes", "on"):
        app.state.w2s_alert_status["enabled"] = True
        _w2s_alert_task = asyncio.create_task(_run_w2s_alert_loop(app))
    else:
        logger.info("W2S alert loop disabled (set SPS_ENABLE_W2S_ALERT_LOOP=true to enable)")

    # P2: jyhf_market 行情采集器自动启动（默认关闭—web_app orchestrator 管理生命周期）
    def _start_jyhf_sync(collector) -> None:
        """在独立线程中运行 jyhf_market collector.start()，避免 SSL 阻塞主线程事件循环。"""
        import asyncio as _asyncio
        _asyncio.run(collector.start())

    if os.environ.get("SPS_ENABLE_JYHF_MARKET_AUTO_START", "false").lower() in ("1", "true", "yes", "on"):
        async def _auto_start_jyhf_market():
            await asyncio.sleep(5)
            from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
            try:
                c = get_jyhf_market_collector()
                # 在 executor 中运行避免 SSL 阻塞事件循环（JYHF API 47.99.190.68 不可达时 PySSL_select→poll 卡死主线程）
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _start_jyhf_sync, c)
                logger.info("jyhf_market collector auto-started")
            except Exception as exc:
                logger.warning("jyhf_market auto-start failed: %s", exc)
        _jyhf_market_task = asyncio.create_task(_auto_start_jyhf_market())
    else:
        _jyhf_market_task = None
        logger.info("JYHF market auto-start DISABLED (web_app orchestrator owns lifecycle)")

    await app.state.phase1_repo.initialize()
    try:
        yield
    finally:
        for task in (_kline_alert_task, _w2s_alert_task, _jyhf_market_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        close = getattr(gw, "close", None)
        if callable(close):
            await close()
        phase1_close = getattr(app.state.phase1_repo, "close", None)
        if callable(phase1_close):
            await phase1_close()
        _release_sps_singleton_lock(getattr(app.state, "singleton_lock_fd", None))
        app.state.singleton_lock_fd = None


app = FastAPI(title="stock_processing_service_read_api", version="0.1.0", lifespan=lifespan)

# P0-D: CORS for direct SSE connections from frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


class CollectionStartRequest(BaseModel):
    trade_date: str
    options: dict[str, Any] = {}
    tushare_pause_seconds: float = 0.1
    abnormal_filters: dict[str, Any] = {}
    min_turnover_rate: float = 3.0
    min_composite_score: float = 40.0


class CollectionJobActionRequest(BaseModel):
    job_id: str


class NotionPublishPayload(BaseModel):
    trade_date: str
    force: bool = False
    dry_run: bool = False
    allow_preview_publish: bool = False  # Phase 4.5.3.1: opt-in to bypass workbench gate


class TradePlanReviewPayload(BaseModel):
    trade_date: str
    plan_date: str
    dry_run: bool = True
    force: bool = False


class PreMarketBriefRebuildPayload(BaseModel):
    trade_date: str
    source: str = "db_first"
    limit: int = Field(default=200, ge=1, le=500)
    dry_run: bool = False
    force: bool = False


class PreMarketBriefFinalizePayload(BaseModel):
    trade_date: str
    force: bool = False


class ScreenerExecutePayload(BaseModel):
    strategy_id: str
    trade_date: str | None = None
    candidate_trade_date: str | None = None
    confirm_trade_date: str | None = None
    limit: int = 100
    min_score: float = 60.0
    auto_tune_min_score: bool = True
    target_min_count: int = 30
    target_max_count: int = 120
    enable_llm_review: bool = False
    llm_top_k: int = 20
    run_stage1: bool = True
    run_stage2: bool = False


class ScreenerFavoritePayload(BaseModel):
    result_id: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ScreenerFavoriteUpdatePayload(BaseModel):
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ScreenerExportPayload(BaseModel):
    result_ids: list[str] = Field(default_factory=list)
    format: str = "json"


# ── W2S Backtest Request Models ──

class W2SDataQualityRequest(BaseModel):
    start_date: str
    end_date: str
    strategy_version: str = "w2s_v0.1"


class W2SBuildFeatureSnapshotRequest(BaseModel):
    run_id: str
    strategy_version: str = "w2s_v0.1"
    start_date: str
    end_date: str
    force_rebuild: bool = False


class W2SValidateSignalsRequest(BaseModel):
    run_id: str
    look_forward_days: list[int] = Field(default=[1, 2, 3, 5])


def _parse_trade_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stock_id_aliases(value: Any) -> set[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return set()
    aliases = {raw}
    if "." in raw:
        aliases.add(raw.split(".", 1)[0])
    elif len(raw) == 6 and raw.isdigit():
        if raw.startswith(("6", "9")):
            aliases.add(f"{raw}.SH")
        elif raw.startswith(("4", "8")):
            aliases.add(f"{raw}.BJ")
        else:
            aliases.add(f"{raw}.SZ")
    return {item for item in aliases if item}


def _candidate_role_label(candidate_type: str) -> str:
    mapping = {
        "dragon_repair": "龙头",
        "subdragon_repair": "龙二",
        "strong_trend_repair": "强趋势",
        "trend_repair": "强趋势",
        "bad_limit_repair": "强趋势",
        "upper_shadow_repair": "强趋势",
        "generic_repair": "强趋势",
    }
    return mapping.get(str(candidate_type or "").strip().lower(), "强趋势")


def _is_same_day_realtime_window(confirm_trade_date: date, now_cn: datetime) -> bool:
    if confirm_trade_date != now_cn.date():
        return False
    if now_cn.hour < 9:
        return False
    if now_cn.hour == 9 and now_cn.minute < 25:
        return False
    return now_cn.hour == 9 and now_cn.minute < 30


def _is_same_day_post_open_window(confirm_trade_date: date, now_cn: datetime) -> bool:
    return confirm_trade_date == now_cn.date() and (
        now_cn.hour > 9 or (now_cn.hour == 9 and now_cn.minute >= 30)
    )


def _realtime_auction_cache_key(trade_date: date) -> str:
    return f"{REALTIME_AUCTION_CACHE_PREFIX}:{trade_date.isoformat()}"


def _redis_url() -> str:
    return str(os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()


async def _get_async_redis() -> AsyncRedis:
    if AsyncRedis is None:
        raise HTTPException(status_code=503, detail="Redis客户端不可用，无法执行实时盘前确认")
    return AsyncRedis.from_url(_redis_url(), decode_responses=True)


def _auction_dto_to_cache_dict(dto: StockAuctionDTO) -> Dict[str, Any]:
    return {
        "trade_date": dto.trade_date.isoformat(),
        "stock_id": dto.stock_id,
        "auction_open_price": float(dto.auction_open_price) if dto.auction_open_price is not None else None,
        "auction_open_pct": float(dto.auction_open_pct) if dto.auction_open_pct is not None else None,
        "auction_volume": float(dto.auction_volume) if dto.auction_volume is not None else None,
        "auction_amount": float(dto.auction_amount) if dto.auction_amount is not None else None,
        "tail_auction_close_price": float(dto.tail_auction_close_price) if dto.tail_auction_close_price is not None else None,
        "tail_auction_volume": float(dto.tail_auction_volume) if dto.tail_auction_volume is not None else None,
        "tail_auction_amount": float(dto.tail_auction_amount) if dto.tail_auction_amount is not None else None,
        "tail_auction_vwap": float(dto.tail_auction_vwap) if dto.tail_auction_vwap is not None else None,
        # P2-B-0: rich auction features
        "last_minute_ratio": float(dto.last_minute_ratio) if dto.last_minute_ratio is not None else None,
        "carry_ratio": float(dto.carry_ratio) if dto.carry_ratio is not None else None,
        "price_path_stability_score": float(dto.price_path_stability_score) if dto.price_path_stability_score is not None else None,
        "has_end_spike": dto.has_end_spike,
        "has_end_drop": dto.has_end_drop,
        "shape_features": list(dto.shape_features),
        "source_snapshot_rule_version": dto.source_snapshot_rule_version,
    }


def _auction_dto_from_cache_dict(payload: Dict[str, Any]) -> StockAuctionDTO:
    return StockAuctionDTO(
        trade_date=_parse_trade_date(str(payload.get("trade_date") or "")) or date.today(),
        stock_id=str(payload.get("stock_id") or ""),
        auction_open_price=Decimal(str(payload["auction_open_price"])) if payload.get("auction_open_price") is not None else None,
        auction_open_pct=Decimal(str(payload["auction_open_pct"])) if payload.get("auction_open_pct") is not None else None,
        auction_volume=Decimal(str(payload["auction_volume"])) if payload.get("auction_volume") is not None else None,
        auction_amount=Decimal(str(payload["auction_amount"])) if payload.get("auction_amount") is not None else None,
        tail_auction_close_price=Decimal(str(payload["tail_auction_close_price"])) if payload.get("tail_auction_close_price") is not None else None,
        tail_auction_volume=Decimal(str(payload["tail_auction_volume"])) if payload.get("tail_auction_volume") is not None else None,
        tail_auction_amount=Decimal(str(payload["tail_auction_amount"])) if payload.get("tail_auction_amount") is not None else None,
        tail_auction_vwap=Decimal(str(payload["tail_auction_vwap"])) if payload.get("tail_auction_vwap") is not None else None,
        # P2-B-0: rich auction features
        last_minute_ratio=Decimal(str(payload["last_minute_ratio"])) if payload.get("last_minute_ratio") is not None else None,
        carry_ratio=Decimal(str(payload["carry_ratio"])) if payload.get("carry_ratio") is not None else None,
        price_path_stability_score=Decimal(str(payload["price_path_stability_score"])) if payload.get("price_path_stability_score") is not None else None,
        has_end_spike=bool(payload.get("has_end_spike", False)),
        has_end_drop=bool(payload.get("has_end_drop", False)),
        shape_features=tuple(payload.get("shape_features") or []),
        source_snapshot_rule_version=str(payload.get("source_snapshot_rule_version") or ""),
    )


def _snapshot_to_row(snapshot: PreMarketAuctionSnapshot) -> Dict[str, Any]:
    return {
        "trade_date": _parse_trade_date(snapshot.trade_date),
        "stock_id": snapshot.stock_id,
        "stock_name": snapshot.stock_name,
        "subject_key": snapshot.subject_key,
        "theme_name": snapshot.theme_name,
        "role_label": snapshot.role_label,
        "window_start_time": snapshot.window_start_time,
        "window_end_time": snapshot.window_end_time,
        "last_minute_start_time": snapshot.last_minute_start_time,
        "last_30s_start_time": snapshot.last_30s_start_time,
        "auction_open_price": snapshot.auction_open_price,
        "pre_close": snapshot.pre_close,
        "auction_open_pct": snapshot.auction_open_pct,
        "auction_volume": snapshot.auction_volume,
        "auction_amount": snapshot.auction_amount,
        "last_minute_amount": snapshot.last_minute_amount,
        "last_minute_ratio": snapshot.last_minute_ratio,
        "prev_day_max_intraday_amount": snapshot.prev_day_max_intraday_amount,
        "carry_ratio": snapshot.carry_ratio,
        "price_path_stability_score": snapshot.price_path_stability_score,
        "is_red_zone": snapshot.is_red_zone,
        "has_end_spike": snapshot.has_end_spike,
        "has_end_drop": snapshot.has_end_drop,
        "shape_features": list(snapshot.shape_features),
        "source_type": snapshot.source_type,
        "source_trace_id": snapshot.source_trace_id,
        "source_trace": dict(snapshot.source_trace),
        "source_version": snapshot.source_version,
        "rule_version": snapshot.rule_version,
    }


async def _write_realtime_auction_cache(
    trade_date: date,
    auctions: List[StockAuctionDTO],
    snapshots: List[Dict[str, Any]],
) -> None:
    redis = await _get_async_redis()
    try:
        ttl_seconds = max(int(os.getenv("W2S_REALTIME_AUCTION_CACHE_TTL", "1800") or 1800), 60)
        payload = {
            "trade_date": trade_date.isoformat(),
            "auctions": [_auction_dto_to_cache_dict(item) for item in auctions],
            "snapshots": snapshots,
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        await redis.setex(_realtime_auction_cache_key(trade_date), ttl_seconds, json.dumps(payload, ensure_ascii=False))
    finally:
        await redis.aclose()


async def _read_realtime_auction_cache(
    trade_date: date,
    stock_ids: List[str],
) -> tuple[List[StockAuctionDTO], List[Dict[str, Any]]]:
    redis = await _get_async_redis()
    try:
        raw = await redis.get(_realtime_auction_cache_key(trade_date))
    finally:
        await redis.aclose()
    if not raw:
        return [], []
    payload = json.loads(raw)
    allowed_aliases = set()
    for stock_id in stock_ids:
        allowed_aliases.update(_stock_id_aliases(stock_id))
    auctions: List[StockAuctionDTO] = []
    for row in list(payload.get("auctions") or []):
        if _stock_id_aliases(row.get("stock_id")) & allowed_aliases:
            auctions.append(_auction_dto_from_cache_dict(dict(row)))
    snapshots: List[Dict[str, Any]] = []
    for row in list(payload.get("snapshots") or []):
        aliases = _stock_id_aliases(row.get("stock_id"))
        if aliases & allowed_aliases:
            item = dict(row)
            item["trade_date"] = _parse_trade_date(str(item.get("trade_date") or trade_date.isoformat()))
            snapshots.append(item)
    return auctions, snapshots


async def _persist_pre_market_auction_snapshots(snapshots: List[Dict[str, Any]]) -> int:
    if not snapshots:
        return 0
    try:
        return await app.state.gateway.upsert_pre_market_auction_snapshots(snapshots)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"竞价快照落库失败: {exc}") from exc


async def _build_live_w2s_auction_material(
    confirm_trade_date: date,
    candidate_trade_date: date,
    formal_candidates: List[Dict[str, Any]],
) -> tuple[List[StockAuctionDTO], List[Dict[str, Any]]]:
    token = _resolve_tushare_token()
    if not token:
        raise HTTPException(status_code=400, detail="缺少 TUSHARE_TOKEN，无法执行实时盘前确认")
    stock_ids = [str(row.get("stock_id") or "") for row in formal_candidates if str(row.get("stock_id") or "").strip()]
    adapter = TushareAdapter(token, timeout=30, retry_count=1, pause_seconds=0.2)
    frame = await asyncio.to_thread(adapter.fetch_stk_auction, confirm_trade_date.isoformat(), stock_ids)
    records = TushareAdapter.to_records(frame)
    builder = AuctionSnapshotBuilderService()
    parsed_map: Dict[str, Any] = {}
    for record in records:
        parsed = builder.parse_tushare_auction_record(record)
        for alias in _stock_id_aliases(parsed.stock_id):
            parsed_map[alias] = parsed

    prev_bars = await app.state.read_port.get_stock_daily_bars(candidate_trade_date, stock_ids=stock_ids)
    prev_bar_map: Dict[str, Any] = {}
    for bar in prev_bars:
        for alias in _stock_id_aliases(bar.stock_id):
            prev_bar_map[alias] = bar

    auctions: List[StockAuctionDTO] = []
    snapshots: List[Dict[str, Any]] = []
    proxy_ratio = float(os.getenv("W2S_AUCTION_PROXY_RATIO", "0.08") or 0.08)
    for row in formal_candidates:
        stock_id = str(row.get("stock_id") or "").strip().upper()
        parsed = next((parsed_map.get(alias) for alias in _stock_id_aliases(stock_id) if parsed_map.get(alias) is not None), None)
        if parsed is None:
            continue
        prev_bar = next((prev_bar_map.get(alias) for alias in _stock_id_aliases(stock_id) if prev_bar_map.get(alias) is not None), None)
        prev_close = float(getattr(prev_bar, "close_price", None) or getattr(prev_bar, "pre_close", None) or 0.0)
        prev_amount = float(getattr(prev_bar, "amount", None) or 0.0)
        candidate = AuctionCandidateInput(
            trade_date=confirm_trade_date.isoformat(),
            stock_id=stock_id,
            stock_name=str(row.get("stock_name") or ""),
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
            role_label=_candidate_role_label(str(row.get("candidate_type") or "")),
            mainline_alive=True,
            action_bias="watch_open",
            is_reversal_watch=True,
        )
        snapshot = builder.build_single_point_snapshot(
            candidate,
            parsed,
            prev_day_close=prev_close,
            prev_day_max_intraday_amount_proxy=round(prev_amount * proxy_ratio, 2),
        )
        snapshot_row = _snapshot_to_row(snapshot)
        snapshot_row["source_type"] = "stock_processing_service.realtime.pre_market_auction"
        snapshot_row["source_trace"] = {
            **dict(snapshot_row.get("source_trace") or {}),
            "channel": "realtime_online_fetch",
            "candidate_trade_date": candidate_trade_date.isoformat(),
            "confirm_trade_date": confirm_trade_date.isoformat(),
        }
        snapshots.append(snapshot_row)
        auctions.append(
            StockAuctionDTO(
                trade_date=confirm_trade_date,
                stock_id=stock_id,
                auction_open_price=Decimal(str(snapshot.auction_open_price)),
                auction_open_pct=Decimal(str(snapshot.auction_open_pct)),
                auction_volume=Decimal(str(snapshot.auction_volume)),
                auction_amount=Decimal(str(snapshot.auction_amount)),
                tail_auction_vwap=Decimal(str(snapshot.auction_open_price)),
                # P2-B-0: rich auction features from PreMarketAuctionSnapshot
                last_minute_ratio=Decimal(str(snapshot.last_minute_ratio)) if snapshot.last_minute_ratio is not None else None,
                carry_ratio=Decimal(str(snapshot.carry_ratio)) if snapshot.carry_ratio is not None else None,
                price_path_stability_score=Decimal(str(snapshot.price_path_stability_score)) if snapshot.price_path_stability_score is not None else None,
                has_end_spike=snapshot.has_end_spike,
                has_end_drop=snapshot.has_end_drop,
                shape_features=tuple(snapshot.shape_features),
                source_snapshot_rule_version=str(snapshot.rule_version or ""),
            )
        )
    return auctions, snapshots


async def _load_w2s_auctions_for_confirm(
    confirm_trade_date: date,
    candidate_trade_date: date,
    formal_candidates: List[Dict[str, Any]],
) -> tuple[List[StockAuctionDTO], Dict[str, Any]]:
    stock_ids = [str(row.get("stock_id") or "") for row in formal_candidates if str(row.get("stock_id") or "").strip()]
    if not stock_ids:
        return [], {"channel": "empty", "cache_writes": 0, "persisted_rows": 0}

    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    if _is_same_day_realtime_window(confirm_trade_date, now_cn):
        auctions, cached_snapshots = await _read_realtime_auction_cache(confirm_trade_date, stock_ids)
        if auctions:
            return auctions, {"channel": "redis_realtime", "cache_writes": 0, "persisted_rows": 0}
        auctions, snapshots = await _build_live_w2s_auction_material(confirm_trade_date, candidate_trade_date, formal_candidates)
        await _write_realtime_auction_cache(confirm_trade_date, auctions, snapshots)
        persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
        return auctions, {"channel": "realtime_online_fetch", "cache_writes": len(auctions), "persisted_rows": persisted_rows}

    db_auctions = await app.state.read_port.get_stock_auction_snapshot(confirm_trade_date, stock_ids=stock_ids)
    if db_auctions:
        return db_auctions, {"channel": "db", "cache_writes": 0, "persisted_rows": 0}

    if _is_same_day_post_open_window(confirm_trade_date, now_cn):
        auctions, snapshots = await _read_realtime_auction_cache(confirm_trade_date, stock_ids)
        if auctions:
            persisted_rows = 0
            if snapshots:
                persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
            return auctions, {"channel": "redis_compensation", "cache_writes": 0, "persisted_rows": persisted_rows}
        auctions, snapshots = await _build_live_w2s_auction_material(confirm_trade_date, candidate_trade_date, formal_candidates)
        await _write_realtime_auction_cache(confirm_trade_date, auctions, snapshots)
        persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
        return auctions, {"channel": "online_compensation", "cache_writes": len(auctions), "persisted_rows": persisted_rows}

    return [], {"channel": "db_miss", "cache_writes": 0, "persisted_rows": 0}


def _looks_like_numeric_theme_name(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.isdigit()


async def _resolve_theme_name_map(subject_keys: List[str], trade_date: Optional[date] = None) -> Dict[str, str]:
    return await app.state.gateway.resolve_theme_name_map(subject_keys, trade_date)


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


def _is_weak_to_strong_strategy(strategy: Optional[Dict[str, Any]], strategy_id: str) -> bool:
    sid = (strategy_id or "").lower()
    if sid == "weak_to_strong" or "weak_to_strong" in sid:
        return True
    if not strategy:
        return False
    stype = str(strategy.get("strategy_type") or "").lower()
    sname = str(strategy.get("strategy_name") or "")
    return stype == "weak_to_strong" or "weak_to_strong" in stype or ("弱转强" in sname)


async def _resolve_prev_trade_date(trade_date: date) -> date:
    cal = await app.state.gateway.get_trade_calendar(trade_date)
    prev_day = (cal or {}).get("prev_trade_date") if isinstance(cal, dict) else None
    if not prev_day or prev_day >= trade_date:
        raise HTTPException(
            status_code=400,
            detail=f"未找到 {trade_date.isoformat()} 之前的上一个交易日，无法执行盘前确认",
        )
    return prev_day


async def _fetch_w2s_candidates(candidate_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    return await app.state.gateway.get_w2s_candidates_by_trade_date(candidate_trade_date, limit=limit)


async def _count_w2s_formal_candidates_by_trade_date(candidate_trade_date: date) -> int:
    rows = await _fetch_w2s_candidates(candidate_trade_date, limit=2000)
    return sum(1 for row in rows if str(row.get("pool_entry_type") or "").lower() == "formal")


async def _fetch_w2s_candidates_by_ids(candidate_ids: List[int]) -> List[Dict[str, Any]]:
    return await app.state.gateway.get_w2s_candidates_by_ids(candidate_ids)


async def _fetch_w2s_signals(trade_date: date) -> Dict[int, Dict[str, Any]]:
    rows = await app.state.gateway.get_w2s_signals_by_trade_date(trade_date)
    payload: Dict[int, Dict[str, Any]] = {}
    for row in rows or []:
        candidate_id = int(row.get("candidate_id") or 0)
        if candidate_id > 0:
            payload[candidate_id] = dict(row)
    return payload


async def _get_w2s_snapshot_coverage(trade_date: date) -> Dict[str, int]:
    return await app.state.gateway.get_w2s_snapshot_coverage(trade_date)


async def _has_w2s_snapshot_cache(trade_date: date) -> bool:
    coverage = await _get_w2s_snapshot_coverage(trade_date)
    candidate_cnt = int(coverage.get("candidate_cnt") or 0)
    snapshot_hit_cnt = int(coverage.get("snapshot_hit_cnt") or 0)
    if candidate_cnt <= 0:
        return True
    return snapshot_hit_cnt >= candidate_cnt


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _candidate_row_to_domain(candidate: Dict[str, Any]) -> W2SCandidate:
    evidence_json = _obj(candidate.get("evidence_json"))
    evidence_rules = evidence_json.get("evidence_rules") or evidence_json.get("trigger_flags") or []
    return W2SCandidate(
        trade_date=str(candidate.get("trade_date") or ""),
        stock_id=str(candidate.get("stock_id") or ""),
        stock_name=str(candidate.get("stock_name") or ""),
        subject_key=str(candidate.get("subject_key") or ""),
        subject_name=str(candidate.get("theme_name") or candidate.get("subject_key") or ""),
        support_score=_d(candidate.get("support_strength")),
        momentum_score=_d(candidate.get("candidate_score")),
        candidate_score=_d(candidate.get("candidate_score")),
        candidate_level=str(candidate.get("pool_entry_type") or "formal"),
        candidate_source=str(candidate.get("candidate_source") or "weak_to_strong_candidate_pool"),
        evidence_rules=list(evidence_rules) if isinstance(evidence_rules, list) else [],
    )


def _confirmed_pick_to_signal(pick: Any) -> Dict[str, Any]:
    decision = "confirmed" if bool(getattr(pick, "approved", False)) else "reject"
    return {
        "signal_level": str(getattr(pick, "confirm_level", "") or ""),
        "decision": decision,
        "confirmation_score": str(getattr(pick, "confirm_score", "0")),
        "auction_open_pct": None,
        "auction_close_pct": None,
        "auction_pattern": "",
        "last_minute_grab_score": 0,
        "plate_follow_score": 0,
        "risk_penalty": 0,
        "data_status": "ready" if getattr(pick, "reject_reason_code", None) is None else "rejected",
        "evidence_json": {
            "reject_reason_code": getattr(pick, "reject_reason_code", None),
            "evidence_rules": list(getattr(pick, "evidence_rules", []) or []),
        },
    }


async def _run_w2s_candidate_selection_for_screener(trade_date: date, stage1_limit: int) -> Dict[str, Any]:
    result = await app.state.container.build_weak_to_strong_candidate.execute(trade_date=trade_date)
    candidates = await _fetch_w2s_candidates(trade_date, limit=stage1_limit)
    metrics = dict(getattr(result, "metrics", None) or {})
    return {
        "status": str(result.status),
        "source_trade_date": trade_date.isoformat(),
        "candidate_count": len(candidates),
        "candidate_limit": stage1_limit,
        "selection_job": "build_weak_to_strong_candidate",
        "d1_total_in": int(metrics.get("d1_total_in") or 0),
        "d1_pass": int(metrics.get("d1_pass") or 0),
        "d1_written": int(metrics.get("d1_written") or 0),
    }


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


async def _refresh_w2s_auction_snapshot(trade_date: date, min_required_stocks: int = 0) -> None:
    """盘前竞价快照采集 — 通过 AuctionSnapshotRunner in-process 执行（不再 fork 子进程）。"""
    token = _resolve_tushare_token()
    base_max_stocks = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS", "80") or 80), 1)
    hard_cap = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS_HARD_CAP", "2000") or 2000), 1)
    dynamic_required = max(int(min_required_stocks or 0), 0)
    max_stocks = min(max(base_max_stocks, dynamic_required), hard_cap)
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    has_token = bool(token)
    if not has_token and trade_date == now_cn.date():
        raise HTTPException(status_code=400, detail="缺少 TUSHARE_TOKEN，无法执行盘前竞价采集")
    if not has_token and trade_date < now_cn.date():
        if await _has_w2s_snapshot_cache(trade_date):
            return
        raise HTTPException(
            status_code=400,
            detail="缺少 TUSHARE_TOKEN 且未找到该交易日缓存竞价快照，请先完成日采集或在 .env.theme/.env.local 配置 TUSHARE_TOKEN",
        )
    # 新链：AuctionSnapshotRunner in-process 调用（不 fork 子进程）
    from stock_processing_service.application.services.collection_task_runners import AuctionSnapshotRunner
    env = {}
    if has_token:
        env["TUSHARE_TOKEN"] = token
    context_kwargs = {
        "trade_date": trade_date.isoformat(),
        "payload": {
            "auction_top_k": 40,
            "auction_proxy_ratio": 0.08,
        },
        "env": env,
        "project_root": _project_root(),
        "python_bin": sys.executable,
    }
    runner = AuctionSnapshotRunner(universe_source="weak_to_strong_candidates", max_stocks=max_stocks)
    result = await runner.run(CollectionTaskContext(**context_kwargs))
    if result.status != "success":
        if await _has_w2s_snapshot_cache(trade_date):
            logger.warning("盘前竞价采集失败，已回退缓存继续执行: trade_date=%s status=%s", trade_date, result.status)
            return
        raise HTTPException(status_code=500, detail=f"盘前竞价采集失败: {result.error_message or result.current_label}")


def _build_w2s_result_row(candidate: Dict[str, Any], signal: Optional[Dict[str, Any]], rank: int) -> Dict[str, Any]:
    candidate_id = int(candidate.get("id") or 0)
    candidate_trade_date = str(candidate.get("trade_date") or "")
    confirm_trade_date = str(candidate.get("confirm_trade_date") or "")
    stock_id = str(candidate.get("stock_id") or "")
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
    result_id = f"w2s_{candidate_trade_date}__{confirm_trade_date or 'candidate'}__{stock_id}"
    return {
        "result_id": result_id,
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


def _parse_w2s_result_id(result_id: str) -> tuple[Optional[date], Optional[date], str]:
    text = str(result_id or "").strip()
    if not text.startswith("w2s_"):
        return None, None, ""
    raw = text.split("_", 1)[1]
    parts = raw.split("__")
    if len(parts) != 3:
        return None, None, ""
    candidate_trade_date_text, confirm_trade_date_text, stock_id = [part.strip() for part in parts]
    try:
        candidate_trade_date = date.fromisoformat(candidate_trade_date_text)
    except ValueError:
        return None, None, ""
    confirm_trade_date: Optional[date] = None
    if confirm_trade_date_text and confirm_trade_date_text != "candidate":
        try:
            confirm_trade_date = date.fromisoformat(confirm_trade_date_text)
        except ValueError:
            return None, None, ""
    return candidate_trade_date, confirm_trade_date, stock_id


async def _build_w2s_result_detail_from_snapshot(
    candidate_trade_date: date,
    stock_id: str,
    *,
    confirm_trade_date: Optional[date] = None,
    view: str | None = None,
) -> Dict[str, Any]:
    candidates = await _fetch_w2s_candidates(candidate_trade_date, limit=200)
    candidate = next((row for row in candidates if str(row.get("stock_id") or "") == stock_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="result not found")
    candidate = dict(candidate)
    if confirm_trade_date is not None:
        candidate["confirm_trade_date"] = confirm_trade_date.isoformat()
    signal: Optional[Dict[str, Any]] = None
    if confirm_trade_date is not None and (view == "confirm" or view is None):
        auctions, _meta = await _load_w2s_auctions_for_confirm(confirm_trade_date, candidate_trade_date, [candidate])
        if auctions:
            confirmed = W2SConfirmService().confirm(
                candidates=[_candidate_row_to_domain(candidate)],
                auctions=auctions,
            )
            if confirmed:
                signal = _confirmed_pick_to_signal(confirmed[0])
    row = _build_w2s_result_row(candidate, signal, rank=1)
    weak = dict(row.get("weak_to_strong") or {})
    weak["detail_view"] = "confirm" if confirm_trade_date is not None and (view == "confirm" or weak.get("signal_level")) else "candidate"
    weak["candidate_trade_date"] = candidate_trade_date.isoformat()
    weak["confirm_trade_date"] = confirm_trade_date.isoformat() if confirm_trade_date is not None else ""
    row["weak_to_strong"] = weak
    row["weak_to_strong_replay"] = {
        "candidate_evidence": _obj(candidate.get("evidence_json")),
        "signal_evidence": (signal or {}).get("evidence_json") or {},
    }
    row["dimension_details"] = None
    row["created_at"] = None
    return row
def _build_w2s_result_detail_from_replay(
    replay: Dict[str, Any],
    *,
    view: str | None = None,
) -> Dict[str, Any]:
    signal = {
        "signal_level": str(replay.get("signal_level") or ""),
        "decision": str(replay.get("decision") or ""),
        "confirmation_score": float(replay.get("confirmation_score") or 0.0),
        "auction_open_pct": float(replay.get("auction_open_pct") or 0.0),
        "auction_close_pct": float(replay.get("auction_close_pct") or 0.0),
        "auction_pattern": str(replay.get("auction_pattern") or ""),
        "last_minute_grab_score": float(replay.get("last_minute_grab_score") or 0.0),
        "plate_follow_score": float(replay.get("plate_follow_score") or 0.0),
        "risk_penalty": float(replay.get("risk_penalty") or 0.0),
        "data_status": str(replay.get("data_status") or "missing"),
        "evidence_json": replay.get("signal_evidence") or {},
    }
    candidate = {
        "id": int(replay.get("candidate_id") or 0),
        "stock_id": str(replay.get("stock_id") or ""),
        "stock_name": str(replay.get("stock_name") or ""),
        "subject_key": str(replay.get("subject_key") or ""),
        "theme_name": str(replay.get("theme_name") or replay.get("subject_key") or ""),
        "candidate_score": float(replay.get("candidate_score") or 0.0),
        "candidate_type": str(replay.get("candidate_type") or ""),
        "weak_type": str(replay.get("weak_type") or ""),
        "support_type": str(replay.get("support_type") or ""),
        "support_strength": float(replay.get("support_strength") or 0.0),
        "expected_open_low": float(replay.get("expected_open_low") or 0.0),
        "expected_open_high": float(replay.get("expected_open_high") or 0.0),
        "evidence_json": replay.get("candidate_evidence") or {},
    }
    row = _build_w2s_result_row(candidate, signal if signal.get("signal_level") else None, rank=1)
    weak = dict(row.get("weak_to_strong") or {})
    weak["detail_view"] = "confirm" if view == "confirm" or weak.get("signal_level") else "candidate"
    weak["candidate_trade_date"] = str(replay.get("candidate_trade_date") or "")
    weak["confirm_trade_date"] = str(replay.get("confirm_trade_date") or "")
    row["weak_to_strong"] = weak
    row["weak_to_strong_replay"] = {
        "candidate_evidence": replay.get("candidate_evidence") or {},
        "signal_evidence": replay.get("signal_evidence") or {},
    }
    row["dimension_details"] = None
    row["created_at"] = None
    return row


async def _execute_weak_to_strong_two_stage(payload: ScreenerExecutePayload, trade_date: date) -> Dict[str, Any]:
    started = time.perf_counter()
    strategy = await app.state.gateway.get_stock_screening_strategy(payload.strategy_id)
    strategy_name = str((strategy or {}).get("strategy_name") or "弱转强策略")

    run_stage1 = bool(payload.run_stage1)
    run_stage2 = bool(payload.run_stage2)
    if not run_stage1 and not run_stage2:
        run_stage1 = True
    hard_stage1_limit = 10
    default_stage1_limit = min(max(int(os.getenv("W2S_STAGE1_MAX_CANDIDATES", "10") or 10), 1), hard_stage1_limit)
    requested_stage1_limit = int(payload.limit or 0)
    if requested_stage1_limit > 0:
        stage1_limit = min(max(requested_stage1_limit, 1), hard_stage1_limit)
    else:
        stage1_limit = default_stage1_limit

    candidate_trade_date = _parse_trade_date(payload.candidate_trade_date or payload.trade_date)
    requested_confirm_trade_date = _parse_trade_date(payload.confirm_trade_date) if payload.confirm_trade_date else None
    confirm_trade_date: Optional[date] = None

    if run_stage2:
        confirm_trade_date = requested_confirm_trade_date or trade_date
        candidate_trade_date = await _resolve_prev_trade_date(confirm_trade_date)

    if run_stage2:
        assert confirm_trade_date is not None
        now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
        if confirm_trade_date == now_cn.date():
            if now_cn.hour < 9 or (now_cn.hour == 9 and now_cn.minute < 25):
                raise HTTPException(status_code=400, detail=PRE_MARKET_CONFIRM_NOT_READY_MESSAGE)

    stage1_summary: Dict[str, Any] = {"status": "skipped", "candidate_count": 0}
    stage2_summary: Dict[str, Any] = {"status": "skipped", "level_count": {"A": 0, "B": 0, "C": 0, "X": 0}}
    candidate_limit = 2000 if run_stage2 else stage1_limit
    if run_stage1:
        stage1_summary = await _run_w2s_candidate_selection_for_screener(
            candidate_trade_date,
            stage1_limit,
        )
    candidates = await _fetch_w2s_candidates(candidate_trade_date, limit=candidate_limit)
    if run_stage1:
        stage1_summary = {
            **stage1_summary,
            "candidate_count": len(candidates),
            "candidate_limit": stage1_limit,
        }
    signals: Dict[str, Dict[str, Any]] = {}
    if run_stage2:
        assert confirm_trade_date is not None
        formal_candidates = [
            row
            for row in candidates
            if str(row.get("pool_entry_type") or "").lower() in {"formal", "s", "a", "b"}
        ]
        auctions, auction_meta = await _load_w2s_auctions_for_confirm(
            confirm_trade_date,
            candidate_trade_date,
            formal_candidates,
        )
        if formal_candidates and not auctions:
            raise HTTPException(
                status_code=424,
                detail=f"{confirm_trade_date.isoformat()} 缺少盘前竞价快照，无法执行盘前确认",
            )
        domain_candidates = [_candidate_row_to_domain(row) for row in formal_candidates]
        confirmed = W2SConfirmService().confirm(candidates=domain_candidates, auctions=auctions)
        level_count = {"A": 0, "B": 0, "C": 0, "X": 0}
        for pick in confirmed:
            level = str(getattr(pick, "confirm_level", "") or "X")
            level_count[level] = int(level_count.get(level, 0)) + 1
            stock_id = str(getattr(pick, "stock_id", "") or "")
            if stock_id:
                signals[stock_id] = _confirmed_pick_to_signal(pick)
        stage2_summary = {
            "status": "success",
            "confirm_trade_date": confirm_trade_date.isoformat(),
            "snapshot_channel": str(auction_meta.get("channel") or "unknown"),
            "snapshot_refresh_skipped": str(auction_meta.get("channel") or "") == "db",
            "snapshot_candidate_cnt": len(formal_candidates),
            "snapshot_hit_cnt": len(auctions),
            "total_candidates": len(formal_candidates),
            "persisted_count": int(auction_meta.get("persisted_rows") or 0),
            "cache_writes": int(auction_meta.get("cache_writes") or 0),
            "level_count": level_count,
        }
    results: List[Dict[str, Any]] = []
    if run_stage2:
        for candidate in candidates:
            candidate["confirm_trade_date"] = confirm_trade_date.isoformat() if confirm_trade_date is not None else ""
        candidate_map: Dict[str, Dict[str, Any]] = {str(c.get("stock_id") or ""): c for c in candidates if str(c.get("stock_id") or "")}
        sorted_signals = sorted(
            signals.items(),
            key=lambda kv: float((kv[1] or {}).get("confirmation_score") or 0.0),
            reverse=True,
        )
        included_stock_ids: set[str] = set()
        for stock_id, signal in sorted_signals:
            candidate = candidate_map.get(stock_id)
            if candidate is None:
                continue
            results.append(_build_w2s_result_row(candidate, signal, len(results) + 1))
            included_stock_ids.add(stock_id)

        for candidate in sorted(candidates, key=lambda c: float(c.get("candidate_score") or 0.0), reverse=True):
            stock_id = str(candidate.get("stock_id") or "")
            if not stock_id or stock_id in included_stock_ids:
                continue
            if str(candidate.get("pool_entry_type") or "").lower() != "observe_only":
                continue
            results.append(_build_w2s_result_row(candidate, None, len(results) + 1))
    else:
        for idx, candidate in enumerate(candidates, start=1):
            signal = signals.get(str(candidate.get("stock_id") or ""))
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
            "confirm_trade_date": confirm_trade_date.isoformat() if confirm_trade_date else None,
            "snapshot_trade_date": confirm_trade_date.isoformat() if run_stage2 and confirm_trade_date else None,
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


def _normalize_recap_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    if isinstance(payload, dict) and payload:
        return payload
    recap_doc = row.get("recap_doc")
    if isinstance(recap_doc, str) and recap_doc.strip():
        try:
            parsed = json.loads(recap_doc)
            if isinstance(parsed, dict) and parsed:
                return {"recap_doc": parsed}
        except Exception:
            pass
    if isinstance(recap_doc, dict) and recap_doc:
        return {"recap_doc": recap_doc}
    doc = row.get("doc")
    if isinstance(doc, str) and doc.strip():
        try:
            parsed = json.loads(doc)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    if isinstance(doc, dict) and doc:
        return doc
    return {}


def _json_or_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _optional_import_status(module_name: str) -> dict[str, Any]:
    if importlib.util.find_spec(module_name) is None:
        return {"available": False, "version": None, "error": "module_not_found"}
    try:
        version = importlib.metadata.version(module_name)
    except Exception:
        version = ""
    return {
        "available": True,
        "version": str(version or ""),
        "error": None,
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    torch_status = _optional_import_status("torch")
    text2vec_status = _optional_import_status("text2vec")
    return {
        "status": "ok",
        "db": _db_name(),
        "runtime_profile": os.getenv("SPS_RUNTIME_PROFILE", "sps-unknown"),
        "python": sys.executable,
        "cwd": str(Path.cwd()),
        "torch_available": bool(torch_status["available"]),
        "torch_version": torch_status["version"],
        "torch_error": torch_status["error"],
        "text2vec_available": bool(text2vec_status["available"]),
        "text2vec_version": text2vec_status["version"],
        "text2vec_error": text2vec_status["error"],
    }


@app.get("/api/v1/debug/runtime_guard_smoke")
async def runtime_guard_smoke() -> dict[str, Any]:
    """Internal smoke for the v1 fallback weak direct-hit guard in the live SPS process."""
    from theme_service.services.theme_match_engine import (
        ThemeMatchEngine,
        _build_gate_evidence,
        _calc_feature_recall_score,
    )
    from theme_service.services.theme_match_types import ThemeMatchRequest, ThemeProfile

    class _StaticRepo:
        async def load_active_profiles(self):
            return [
                ThemeProfile(
                    subject_key="runtime-smoke-v1-fallback",
                    subject_name="福建题材",
                    theme_master_id=None,
                    concept="福建题材",
                    semantic_type="smoke",
                    strategy_type="event_driven",
                    ontology_json={},
                    gate_json={},
                    must_terms=["福建"],
                    should_terms=[],
                    not_terms=[],
                    strong_terms=[],
                    weak_terms=[],
                    negative_terms=[],
                    search_text="福建",
                    quality="smoke",
                    rerank_text="福建",
                    aliases=["福建"],
                    entity_hints=[],
                    core_objects=[],
                )
            ]

    class _SmokeEngine(ThemeMatchEngine):
        async def _dense_recall(self, request, event_profile=None):
            return []

        async def _sparse_recall(self, request, event_profile=None):
            return []

        def _rerank(self, request, candidate_rows, profile_map, event_profile=None, counters=None, evidence_cache=None):
            rows = []
            event_text = request.event_text()
            for row in candidate_rows or []:
                item = dict(row)
                profile = profile_map[item["subject_key"]]
                evidence = _build_gate_evidence(event_text, profile, event_profile)
                item["evidence"] = evidence
                item["rerank_score"] = _calc_feature_recall_score({}, evidence)
                rows.append(item)
            rows.sort(key=lambda item: (-float(item.get("rerank_score") or 0.0), str(item.get("subject_key"))))
            return rows

    engine = _SmokeEngine(_StaticRepo())
    if getattr(engine, "_judge", None) is not None:
        engine._judge.api_key = ""
    if getattr(engine, "_event_profile_extractor", None) is not None:
        engine._event_profile_extractor.api_key = ""
    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=0,
            news_id=0,
            title="福建发布天气预警",
            content="福建普通地方新闻触发旧 v1 fallback direct hit。",
            summary="福建天气预警",
            event_type="runtime_guard_smoke",
        )
    )
    guard = result.audit.get("v1_direct_hit_guard") if isinstance(result.audit, dict) else {}
    return {
        "ok": result.decision == "HUMAN_REVIEW" and result.reason_code == "weak_v1_direct_hit_review",
        "decision": result.decision,
        "reason_code": result.reason_code,
        "runtime_source": "v1_fallback",
        "match_reason": guard.get("previous_reason_code") or "direct_theme_name_hit",
        "guard_applied": bool(guard.get("blocked")),
        "guard": guard,
    }


class LiveDirectHitReplayRequest(BaseModel):
    cases_path: str = "theme_service/eval/product_runtime_phase2/live_direct_hit_replay_cases.jsonl"
    trade_date: str = "2026-05-22"
    run_id: str | None = None
    persist: bool = True
    out_dir: str = "tmp/product_runtime_phase2c"


LOW_VALUE_EVENT_TERMS = (
    "减持",
    "回购",
    "澄清公告",
    "交易监管",
    "天气预警",
    "山洪",
    "地震救灾",
    "列车停运",
    "普通人事任命",
    "普通财报",
    "季度财报",
)
LLM_ACCEPT_SAFETY_REVIEW_CODES = {
    "weak_v1_llm_accept_review",
    "llm_accept_without_hard_evidence",
    "llm_accept_generic_only_review",
    "low_conf_llm_accept_review",
    "low_value_event_match_blocked",
}


def _debug_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_rel_path(path_raw: str) -> Path:
    root = _debug_repo_root()
    path = Path(path_raw)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail=f"path outside repo is not allowed: {path_raw}")
    return path


def _load_jsonl_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"cases file not found: {path}")
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid jsonl at {path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail=f"jsonl row must be object at {path}:{lineno}")
        rows.append(row)
    return rows


async def _upsert_phase2c_replay_event(
    conn: Any,
    *,
    case: dict[str, Any],
    run_id: str,
    trade_date: str,
) -> int:
    case_id = str(case.get("case_id") or uuid.uuid4().hex)
    trace_id = f"{run_id}:{case_id}"[:128]
    event_time = datetime.fromisoformat(f"{trade_date}T07:30:00")
    raw_event_json = {
        "phase": "product_runtime_phase2c",
        "run_id": run_id,
        "case_id": case_id,
        "title": case.get("title") or "",
        "summary": case.get("summary") or "",
        "content": case.get("content") or case.get("event_text") or "",
        "expected_decision": case.get("expected_decision"),
        "expected_subject_key": case.get("expected_subject_key"),
        "must_not_subject_keys": case.get("must_not_subject_keys") or [],
        "tags": case.get("tags") or [],
    }
    row = await conn.fetchrow(
        """
        INSERT INTO news_event (
            news_id,
            event_type,
            direction,
            confidence,
            summary,
            event_time,
            entities,
            causal_claim,
            evidence_set,
            raw_event_json,
            source_category,
            source_trace_id
        )
        VALUES (
            NULL,
            $1,
            $2,
            $3,
            $4,
            $5,
            $6::jsonb,
            $7::jsonb,
            $8::jsonb,
            $9::jsonb,
            $10,
            $11
        )
        ON CONFLICT (source_trace_id) WHERE source_trace_id IS NOT NULL DO UPDATE SET
            event_type = EXCLUDED.event_type,
            summary = EXCLUDED.summary,
            event_time = EXCLUDED.event_time,
            entities = EXCLUDED.entities,
            causal_claim = EXCLUDED.causal_claim,
            evidence_set = EXCLUDED.evidence_set,
            raw_event_json = EXCLUDED.raw_event_json
        RETURNING id
        """,
        str(case.get("event_type") or "product_runtime_phase2c_live_replay"),
        str(case.get("direction") or "neutral"),
        float(case.get("confidence") or 0.8),
        str(case.get("summary") or case.get("title") or case.get("event_text") or ""),
        event_time,
        json.dumps(case.get("entities") or [], ensure_ascii=False),
        json.dumps(case.get("causal_claim") or [], ensure_ascii=False),
        json.dumps(case.get("evidence_set") or {}, ensure_ascii=False),
        json.dumps(raw_event_json, ensure_ascii=False),
        "product_runtime_phase2c",
        trace_id,
    )
    return int(row["id"])


def _replay_case_to_event_row(case: dict[str, Any], *, event_id: int, run_id: str) -> dict[str, Any]:
    event_text = str(case.get("event_text") or "")
    title = str(case.get("title") or event_text[:120])
    summary = str(case.get("summary") or event_text or title)
    content = str(case.get("content") or event_text or summary)
    return {
        "event_id": event_id,
        "id": event_id,
        "news_id": event_id,
        "title": title,
        "summary": summary,
        "content": content,
        "event_type": str(case.get("event_type") or "product_runtime_phase2c_live_replay"),
        "entities": case.get("entities") or [],
        "causal_claim": case.get("causal_claim") or [],
        "evidence_set": case.get("evidence_set") or {},
        "raw_event_json": {
            "phase": "product_runtime_phase2c",
            "run_id": run_id,
            "case_id": case.get("case_id"),
            "tags": case.get("tags") or [],
        },
        "trace_id": f"{run_id}:{case.get('case_id') or event_id}",
    }


def _extract_hits(evidence: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = evidence.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item not in (None, ""))
        elif isinstance(raw, str) and raw:
            values.append(raw)
    return list(dict.fromkeys(values))


def _write_phase2c_reports(out_dir: Path, *, run_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "live_replay_results.jsonl"
    result_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )

    new_rows_after_guard = len(rows)
    new_match_count = sum(row.get("decision") == "MATCH" for row in rows)
    new_human_review_count = sum(row.get("decision") == "HUMAN_REVIEW" for row in rows)
    new_weak_review_count = sum(row.get("reason_code") == "weak_v1_direct_hit_review" for row in rows)
    new_direct_hit_match_count = sum(
        row.get("decision") == "MATCH" and row.get("match_reason") == "direct_theme_name_hit"
        for row in rows
    )
    new_direct_hit_review_count = sum(
        row.get("decision") == "HUMAN_REVIEW"
        and (row.get("match_reason") == "direct_theme_name_hit" or row.get("reason_code") == "weak_v1_direct_hit_review")
        for row in rows
    )
    llm_accept_match_count = sum(row.get("match_reason") == "llm_accept_match" for row in rows)
    llm_accept_blocked_count = sum(row.get("reason_code") in LLM_ACCEPT_SAFETY_REVIEW_CODES for row in rows)
    weak_v1_llm_accept_review_count = sum(row.get("reason_code") == "weak_v1_llm_accept_review" for row in rows)
    llm_accept_without_hard_evidence_count = sum(row.get("reason_code") == "llm_accept_without_hard_evidence" for row in rows)
    llm_accept_generic_only_review_count = sum(row.get("reason_code") == "llm_accept_generic_only_review" for row in rows)
    low_conf_llm_accept_review_count = sum(row.get("reason_code") == "low_conf_llm_accept_review" for row in rows)
    low_value_event_match_blocked_count = sum(row.get("reason_code") == "low_value_event_match_blocked" for row in rows)
    new_obvious_wrong_match_count = sum(row.get("auto_label") in {"obvious_wrong", "guard_miss"} for row in rows)
    new_positive_fail_count = sum(row.get("auto_label") == "positive_fail" for row in rows)
    low_value_major = sum(row.get("is_low_value_event") and row.get("decision") == "MATCH" for row in rows)
    duplicate_primary = 0
    titles_seen: set[str] = set()
    for row in rows:
        if row.get("decision") != "MATCH":
            continue
        title_key = str(row.get("title") or "").strip()
        if title_key and title_key in titles_seen:
            duplicate_primary += 1
        titles_seen.add(title_key)

    attribution_rows: list[dict[str, Any]] = []
    for row in rows:
        evidence = row.get("best_evidence") if isinstance(row.get("best_evidence"), dict) else {}
        attribution_rows.append(
            {
                "event_id": row.get("event_id"),
                "case_id": row.get("case_id"),
                "title": row.get("title") or "",
                "matched_subject_key": row.get("matched_subject_key") or "",
                "matched_theme_name": row.get("matched_theme_name") or "",
                "confidence": row.get("confidence"),
                "decision": row.get("decision"),
                "match_reason": row.get("match_reason") or row.get("reason_code") or "",
                "runtime_source": row.get("runtime_source") or "",
                "best_evidence": evidence,
                "direct_hit_terms": _extract_hits(evidence, "direct_hit_terms", "direct_hits", "direct_theme_name_hits", "theme_name_hit_terms", "subject_name_hit_terms"),
                "accepted_anchor_hits": _extract_hits(evidence, "accepted_anchor_hits", "anchor_hits", "must_hits", "strong_hits"),
                "no_anchor_hits": _extract_hits(evidence, "no_anchor_hits", "weak_hits"),
                "negative_hits": _extract_hits(evidence, "negative_hits", "not_hits", "reject_hits"),
                "is_low_value_event": bool(row.get("is_low_value_event")),
                "is_duplicate_primary": False,
                "auto_label": row.get("auto_label") or "",
                "root_cause": row.get("root_cause") or "",
                "suggested_fix": row.get("suggested_fix") or "",
            }
        )

    (out_dir / "product_match_quality_attribution.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in attribution_rows) + "\n",
        encoding="utf-8",
    )

    metrics = {
        "run_id": run_id,
        "new_rows_after_guard": new_rows_after_guard,
        "new_match_count": new_match_count,
        "new_human_review_count": new_human_review_count,
        "new_weak_v1_direct_hit_review_count": new_weak_review_count,
        "new_direct_hit_match_count": new_direct_hit_match_count,
        "new_direct_hit_review_count": new_direct_hit_review_count,
        "llm_accept_match_count": llm_accept_match_count,
        "llm_accept_blocked_count": llm_accept_blocked_count,
        "weak_v1_llm_accept_review_count": weak_v1_llm_accept_review_count,
        "llm_accept_without_hard_evidence_count": llm_accept_without_hard_evidence_count,
        "llm_accept_generic_only_review_count": llm_accept_generic_only_review_count,
        "low_conf_llm_accept_review_count": low_conf_llm_accept_review_count,
        "low_value_event_match_blocked_count": low_value_event_match_blocked_count,
        "new_obvious_wrong_match_count": new_obvious_wrong_match_count,
        "new_positive_fail_count": new_positive_fail_count,
        "low_value_major": low_value_major,
        "duplicate_primary": duplicate_primary,
    }
    lines = [
        "# Product Runtime Phase 2C Live Replay Attribution",
        "",
        f"- run_id: {run_id}",
    ]
    lines.extend(f"- {key}: {value}" for key, value in metrics.items() if key != "run_id")
    lines.extend(
        [
            "",
            "| case_id | decision | reason | runtime_source | subject | title |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(
            f"| {row.get('case_id')} | {row.get('decision')} | {row.get('reason_code')} | "
            f"{row.get('runtime_source') or ''} | {row.get('matched_subject_key') or ''} {row.get('matched_theme_name') or ''} | {title} |"
        )
    (out_dir / "product_match_quality_attribution.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    direct_counter: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("match_reason") != "direct_theme_name_hit" and row.get("reason_code") != "weak_v1_direct_hit_review":
            continue
        key = (
            str(row.get("matched_subject_key") or ""),
            str(row.get("matched_theme_name") or ""),
            str(row.get("runtime_source") or ""),
        )
        item = direct_counter.setdefault(
            key,
            {"subject_key": key[0], "subject_name": key[1], "runtime_source": key[2], "n": 0, "review_n": 0, "match_n": 0},
        )
        item["n"] += 1
        item["review_n"] += int(row.get("decision") == "HUMAN_REVIEW")
        item["match_n"] += int(row.get("decision") == "MATCH")

    direct_rows = sorted(direct_counter.values(), key=lambda item: (-int(item["n"]), item["subject_key"]))
    direct_lines = [
        "# Product Runtime Phase 2C Direct Theme Name Hit Audit",
        "",
        f"- run_id: {run_id}",
        f"- direct_hit_rows: {sum(int(row['n']) for row in direct_rows)}",
        f"- v1_fallback_direct_hit_rows: {sum(int(row['n']) for row in direct_rows if row['runtime_source'] == 'v1_fallback')}",
        f"- weak_v1_direct_hit_review_count: {new_weak_review_count}",
        "",
        "| subject_key | subject_name | runtime_source | n | match_n | review_n |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in direct_rows:
        direct_lines.append(
            f"| {row['subject_key']} | {row['subject_name']} | {row['runtime_source']} | "
            f"{row['n']} | {row['match_n']} | {row['review_n']} |"
        )
    (out_dir / "direct_theme_name_hit_audit.md").write_text("\n".join(direct_lines) + "\n", encoding="utf-8")
    return metrics


@app.post("/api/v1/debug/product_runtime_phase2c/live_direct_hit_replay")
async def live_direct_hit_replay(payload: LiveDirectHitReplayRequest) -> dict[str, Any]:
    """Replay high-risk direct-hit samples through the live SPS process and active DB profiles."""
    from theme_service.services.theme_service import ThemeService

    cases_path = _safe_rel_path(payload.cases_path)
    out_dir = _safe_rel_path(payload.out_dir)
    cases = _load_jsonl_cases(cases_path)
    if not cases:
        raise HTTPException(status_code=400, detail="no replay cases loaded")

    run_id = payload.run_id or f"product_runtime_phase2c_live_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')}"
    svc = getattr(app.state, "phase2c_theme_service", None)
    if svc is None:
        svc = ThemeService(enable_clustering=False)
        svc.set_database_gateway(app.state.gateway)
        app.state.phase2c_theme_service = svc

    rows: list[dict[str, Any]] = []
    async with app.state.gateway._client.pool.acquire() as conn:
        for case in cases:
            case_id = str(case.get("case_id") or uuid.uuid4().hex)
            case["case_id"] = case_id
            event_id = await _upsert_phase2c_replay_event(conn, case=case, run_id=run_id, trade_date=payload.trade_date)
            event_row = _replay_case_to_event_row(case, event_id=event_id, run_id=run_id)
            decision = await svc.match_event(event_row, database_gateway=app.state.gateway)
            audit = decision.get("audit") if isinstance(decision.get("audit"), dict) else {}
            best_evidence = audit.get("best_evidence") if isinstance(audit.get("best_evidence"), dict) else {}
            guard = audit.get("v1_direct_hit_guard") if isinstance(audit.get("v1_direct_hit_guard"), dict) else {}
            high_noise_guard = audit.get("high_noise_fallback_guard") if isinstance(audit.get("high_noise_fallback_guard"), dict) else {}
            runtime_source = (
                guard.get("runtime_profile_source")
                or high_noise_guard.get("runtime_profile_source")
                or best_evidence.get("runtime_profile_source")
                or ("v1_fallback" if guard or high_noise_guard else "")
            )
            matched_subject_key = str(decision.get("matched_subject_key") or "")
            if matched_subject_key and not runtime_source:
                has_v2 = await conn.fetchval(
                    "SELECT 1 FROM theme_profile_v2 WHERE subject_key=$1 AND status='accepted_candidate' LIMIT 1",
                    matched_subject_key,
                )
                runtime_source = "v2_accepted" if has_v2 else "v1_fallback"
            match_reason = guard.get("previous_reason_code") or high_noise_guard.get("previous_reason_code") or decision.get("reason_code")
            text = f"{event_row['title']} {event_row['summary']} {event_row['content']}"
            is_low_value = bool(case.get("is_low_value_event")) or any(term in text for term in LOW_VALUE_EVENT_TERMS)

            if payload.persist and decision.get("decision") == "MATCH" and decision.get("matched_subject_key"):
                await app.state.gateway.upsert_event_subject_relation(
                    event_id,
                    str(decision.get("matched_subject_key")),
                    news_id=event_id,
                    subject_name=decision.get("matched_theme_name"),
                    confidence=float(decision.get("confidence") or 0.0),
                    relation_type="primary",
                    match_reason=str(decision.get("reason_code") or ""),
                    evidence_json={
                        **best_evidence,
                        "audit": audit,
                        "phase": "product_runtime_phase2c",
                        "case_id": case_id,
                    },
                    source="product_runtime_phase2c_live_replay",
                    source_trace_id=f"{run_id}:{case_id}"[:128],
                    run_id=run_id,
                )
            elif payload.persist and decision.get("decision") == "HUMAN_REVIEW":
                await app.state.gateway.enqueue_event_review(
                    event_id=event_id,
                    reason=str(decision.get("reason_code") or "product_runtime_phase2c_review"),
                    source_channel="product_runtime_phase2c",
                    proposed_theme_name=decision.get("matched_theme_name"),
                    proposed_theme_confidence=float(decision.get("confidence") or 0.0),
                )

            auto_label = "ok"
            root_cause = ""
            suggested_fix = "no_action"
            must_not = {str(item) for item in (case.get("must_not_subject_keys") or [])}
            expected_subject = str(case.get("expected_subject_key") or "")
            expected_decision = str(case.get("expected_decision") or "").upper()
            if decision.get("matched_subject_key") and str(decision.get("matched_subject_key")) in must_not:
                auto_label = "obvious_wrong"
                root_cause = "live_replay_must_not_violation"
                suggested_fix = "phase2c_delta_repair_required"
            elif expected_decision in {"UNKNOWN", "HUMAN_REVIEW"} and decision.get("decision") == "MATCH":
                auto_label = "guard_miss" if expected_decision == "HUMAN_REVIEW" else "obvious_wrong"
                root_cause = "weak_runtime_guard_gap" if expected_decision == "HUMAN_REVIEW" else "unexpected_match"
                suggested_fix = "inspect_runtime_guard_or_llm_veto"
            elif expected_subject and decision.get("decision") == "MATCH" and str(decision.get("matched_subject_key")) != expected_subject:
                auto_label = "wrong_subject"
                root_cause = "positive_rank_or_gate_issue"
                suggested_fix = "inspect_positive_rank"
            elif expected_decision == "MATCH" and decision.get("decision") != "MATCH":
                auto_label = "positive_fail"
                root_cause = "expected_match_missing"
                suggested_fix = "inspect_positive_recall"
            elif decision.get("reason_code") in LLM_ACCEPT_SAFETY_REVIEW_CODES:
                auto_label = "guarded_review"
                root_cause = "llm_accept_safety_gate"
                suggested_fix = "no_action_unless_repeated"
            elif is_low_value and decision.get("decision") == "MATCH":
                auto_label = "low_value"
                root_cause = "display_layer"
                suggested_fix = "keep_out_of_major_events"
            elif decision.get("reason_code") == "weak_v1_direct_hit_review":
                auto_label = "guarded_review"
                root_cause = "weak_v1_direct_hit_guard"
                suggested_fix = "no_action_unless_repeated"

            rows.append(
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "event_id": event_id,
                    "title": event_row["title"],
                    "summary": event_row["summary"],
                    "decision": decision.get("decision"),
                    "reason_code": decision.get("reason_code"),
                    "match_reason": match_reason,
                    "runtime_source": runtime_source,
                    "matched_subject_key": decision.get("matched_subject_key") or "",
                    "matched_theme_name": decision.get("matched_theme_name") or "",
                    "confidence": decision.get("confidence"),
                    "review_required": decision.get("review_required"),
                    "best_evidence": best_evidence,
                    "top_candidates": audit.get("top_candidates") or [],
                    "guard_applied": bool(guard.get("blocked") or high_noise_guard.get("blocked")),
                    "is_low_value_event": is_low_value,
                    "auto_label": auto_label,
                    "root_cause": root_cause,
                    "suggested_fix": suggested_fix,
                    "expected_subject_key": expected_subject,
                    "must_not_subject_keys": list(must_not),
                    "tags": case.get("tags") or [],
                }
            )

    metrics = _write_phase2c_reports(out_dir, run_id=run_id, rows=rows)
    return {
        "ok": True,
        "run_id": run_id,
        "cases": len(rows),
        "metrics": metrics,
        "out_dir": str(out_dir.relative_to(_debug_repo_root())),
        "reports": [
            str((out_dir / "live_replay_results.jsonl").relative_to(_debug_repo_root())),
            str((out_dir / "product_match_quality_attribution.md").relative_to(_debug_repo_root())),
            str((out_dir / "direct_theme_name_hit_audit.md").relative_to(_debug_repo_root())),
        ],
    }


@app.get("/api/v1/recap/defaults")
async def get_recap_defaults() -> dict[str, Any]:
    """返回最近的盘后复盘和盘前简报日期。"""
    latest_post: str | None = None
    latest_pre: str | None = None
    try:
        d = await app.state.gateway.get_latest_post_market_recap_trade_date()
        if d:
            latest_post = d.isoformat() if hasattr(d, "isoformat") else str(d)
    except Exception:
        pass
    try:
        d = await app.state.gateway.get_latest_pre_market_brief_trade_date()
        if d:
            latest_pre = d.isoformat() if hasattr(d, "isoformat") else str(d)
    except Exception:
        pass
    return {
        "latest_post_market_date": latest_post,
        "latest_pre_market_date": latest_pre,
    }


@app.get("/api/v1/post_market_snapshot")
async def get_post_market_snapshot(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {"trade_date": trade_date, "snapshot_version": "missing", "payload": {}}
    payload = _normalize_recap_payload(row)
    return {
        "trade_date": str(row.get("trade_date") or trade_date),
        "snapshot_version": str(row.get("snapshot_version") or "unknown"),
        "payload": payload,
    }


@app.post("/api/v1/recap/publish-notion")
async def publish_post_market_recap_to_notion(payload: NotionPublishPayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc

    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        raise HTTPException(status_code=404, detail="post_market_recap_snapshot not found")

    normalized_payload = _normalize_recap_payload(row)

    # ── Phase 4.5.3.1: require formal workbench approval to publish ──
    try:
        gate = _get_approval_gate()
        approval = gate.check(d)
        if not approval.can_generate_report and not payload.allow_preview_publish:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot publish to Notion: workbench session is {approval.session_status}. "
                    f"Approve the workbench snapshot first, or set allow_preview_publish=true "
                    f"to bypass this gate. Reason: {approval.reason}"
                ),
            )
        wb_approval = {
            "mode": approval.mode,
            "can_generate_formal_report": approval.can_generate_report,
            "snapshot_version": approval.snapshot_version,
            "approved_at": approval.approved_at,
            "approved_by": approval.approved_by,
            "based_on_draft_version": (
                approval.snapshot.based_on_draft_version if approval.snapshot else 0
            ),
            "session_status": approval.session_status,
            "preview_publish": not approval.can_generate_report,
            "reason": approval.reason,
        }
    except HTTPException:
        raise
    except Exception:
        wb_approval = {"error": "approval check failed"}

    publisher = NotionPostMarketRecapPublisher.from_env()
    result = publisher.publish_snapshot(
        row=row,
        payload=normalized_payload,
        force=payload.force,
        dry_run=payload.dry_run,
    )
    return {
        "ok": True,
        "page_id": result.page_id,
        "page_url": result.page_url,
        "action": result.action,
        "report_id": result.report_id,
        "report_type": result.report_type,
        "trade_date": result.trade_date,
        "workbench_approval": wb_approval,
    }


@app.post("/api/v1/trade-plan/review")
async def review_trade_plan(payload: TradePlanReviewPayload) -> dict[str, Any]:
    try:
        trade_dt = date.fromisoformat(payload.trade_date)
        plan_dt = date.fromisoformat(payload.plan_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid trade_date or plan_date") from exc

    try:
        repository = NotionTradePlanRepository.from_env()
        service = TradePlanReviewService(
            repository=repository,
            gateway=app.state.gateway,
        )
        result = await service.review(
            trade_date=trade_dt,
            plan_date=plan_dt,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result.get("ok"):
        code = str(result.get("error_code") or "")
        if code == "TRADE_PLAN_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result)
        if code == "POST_MARKET_RECAP_SNAPSHOT_MISSING":
            raise HTTPException(status_code=424, detail=result)
        raise HTTPException(status_code=500, detail=result)

    return result


async def _build_one_to_two_watchlists(trade_date: date) -> dict[str, Any]:
    """Read DailyReviewV2.watchlists.one_to_two from persisted setup plan rows.

    This helper never recomputes the setup plan. Missing persisted plan is a
    precondition failure, not an empty result.
    """
    read_port = getattr(app.state, "read_port", None)
    if read_port is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "READ_PORT_MISSING",
                "message": "OneToTwo watchlists require read_port",
                "trade_date": trade_date.isoformat(),
            },
        )
    fn = getattr(read_port, "get_post_market_setup_plan_rows", None)
    if not callable(fn):
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "SETUP_PLAN_READ_METHOD_MISSING",
                "message": "OneToTwo watchlists require get_post_market_setup_plan_rows",
                "trade_date": trade_date.isoformat(),
            },
        )
    rows = await fn(trade_date, "one_to_two")
    if not rows:
        raise HTTPException(
            status_code=424,
            detail={
                "error_code": "ONE_TO_TWO_SETUP_PLAN_MISSING",
                "message": "Persisted one_to_two setup plan missing",
                "trade_date": trade_date.isoformat(),
            },
        )

    summary_row = next((dict(r) for r in rows if str((r or {}).get("stock_id") or "") == "__SUMMARY__"), None)
    if summary_row is None:
        raise HTTPException(
            status_code=424,
            detail={
                "error_code": "SETUP_PLAN_SUMMARY_MISSING",
                "message": "Persisted one_to_two setup plan summary row missing",
                "trade_date": trade_date.isoformat(),
            },
        )
    items = [dict(r) for r in rows if str((r or {}).get("stock_id") or "") != "__SUMMARY__"]
    import json as _json
    summary_raw = summary_row.get("summary") if "summary" in summary_row else {}
    diagnostics_raw = summary_row.get("diagnostics") if "diagnostics" in summary_row else {}
    summary = _json.loads(summary_raw) if isinstance(summary_raw, str) else summary_raw
    diagnostics = _json.loads(diagnostics_raw) if isinstance(diagnostics_raw, str) else diagnostics_raw
    if not isinstance(summary, dict) or not summary:
        raise HTTPException(
            status_code=424,
            detail={
                "error_code": "SETUP_PLAN_PAYLOAD_INVALID",
                "message": "Persisted one_to_two setup plan summary payload invalid",
                "trade_date": trade_date.isoformat(),
            },
        )
    if not isinstance(diagnostics, dict):
        raise HTTPException(
            status_code=424,
            detail={
                "error_code": "SETUP_PLAN_PAYLOAD_INVALID",
                "message": "Persisted one_to_two setup plan diagnostics payload invalid",
                "trade_date": trade_date.isoformat(),
            },
        )
    return {"one_to_two": {"summary": summary, "items": items, "diagnostics": diagnostics}}


def _trim_daily_review_v2_response(v2: dict[str, Any]) -> dict[str, Any]:
    """裁剪 daily-review-v2 响应中的冗余数据，减少传输体积。

    主要优化：
    1. 剔除 f10_capital 大字段（每只股票 ~14KB）
    2. 去除 limit_up_theme_matrix 中与 columns 完全重复的 visible_columns
    3. 去除 non_mainline_columns（前端不需要）
    """
    # 1. money_flow_reviews: 剔除每项的 f10_capital
    for item in v2.get("money_flow_reviews") or []:
        if isinstance(item, dict):
            item.pop("f10_capital", None)

    # 2. stock_capital_reviews: 同上
    for item in v2.get("stock_capital_reviews") or []:
        if isinstance(item, dict):
            item.pop("f10_capital", None)

    # 3. limit_up_theme_matrix: 去重
    mtx = v2.get("limit_up_theme_matrix")
    if isinstance(mtx, dict):
        mtx.pop("visible_columns", None)
        mtx.pop("non_mainline_columns", None)

    # 4. strong_stock_pool_reviews 可能也很大，但先保留
    pdv2 = v2.get("post_market_decision_v2")
    if isinstance(pdv2, dict) and isinstance(pdv2.get("strong_stock_pool_reviews"), list):
        # 保留必要字段，剔除冗余 JSON
        for item in pdv2["strong_stock_pool_reviews"]:
            if isinstance(item, dict):
                item.pop("raw_source", None)
                item.pop("debug_context", None)

    return v2


@app.get("/api/v1/daily_review")
async def get_daily_review(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """结构化每日复盘 — 从 post_market_recap_snapshot 派生。

    返回 DailyReview = { review_date, market_summary, theme_reviews, capital_reviews, trading_principle, diagnostics }。
    """
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc

    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {
            "trade_date": trade_date,
            "market_summary": {},
            "theme_reviews": [],
            "capital_reviews": [],
            "trading_principle": {},
            "diagnostics": {
                "partial": True,
                "snapshot_status": "missing",
                "missing_sections": ["post_market_recap_snapshot"],
            },
        }

    payload = _normalize_recap_payload(row)
    recap_doc = payload.get("recap_doc") or payload

    return {
        "trade_date": trade_date,
        "market_summary": recap_doc.get("market_summary") or {},
        "theme_reviews": recap_doc.get("theme_reviews") or [],
        "capital_reviews": recap_doc.get("capital_reviews") or [],
        "strong_stock_reviews": recap_doc.get("strong_stock_reviews") or [],
        "trading_principle": recap_doc.get("trading_principle") or {},
        "diagnostics": recap_doc.get("diagnostics") or {},
    }


@app.get("/api/v2/daily-review/{trade_date}/watchlists")
async def get_daily_review_watchlists(
    trade_date: str,
    setup_type: str = Query("one_to_two", description="setup type, currently only one_to_two"),
) -> dict[str, Any]:
    """Return setup-plan watchlists from DailyReview V2."""
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc

    if setup_type != "one_to_two":
        raise HTTPException(status_code=400, detail="unsupported setup_type")

    watchlists = await _build_one_to_two_watchlists(d)
    block = watchlists.get("one_to_two")
    if not isinstance(block, dict):
        raise HTTPException(
            status_code=424,
            detail={
                "error_code": "ONE_TO_TWO_SETUP_PLAN_MISSING",
                "message": "Persisted one_to_two setup plan missing from watchlists",
                "trade_date": trade_date,
            },
        )
    return {
        "trade_date": trade_date,
        "setup_type": "one_to_two",
        **block,
    }


@app.get("/api/v2/daily-review-v2")
async def get_daily_review_v2(date_param: str = Query(..., alias="date", description="YYYY-MM-DD")) -> dict[str, Any]:
    """DailyReview V2 skeleton contract.

    V2-P1 exposes a complete page-level ViewModel shape and diagnostics without
    changing RecapPage's default sections_first rendering path.
    """
    try:
        d = date.fromisoformat(date_param)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date: {date_param}") from exc

    from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
        PostMarketDailyReviewV2Builder,
    )

    builder = PostMarketDailyReviewV2Builder()
    row = await _fetch_latest_post_market_recap_snapshot_row(d)
    if not row:
        return builder.build(trade_date=d, recap_doc=None)

    payload = _normalize_recap_payload(row)
    recap_doc = payload.get("recap_doc") or payload
    if not isinstance(recap_doc, dict):
        recap_doc = {}

    recap_doc = await _enrich_recap_doc_with_limit_up_board_counts(d, recap_doc)
    recap_doc = await _enrich_recap_doc_with_new_high_summary(d, recap_doc)
    recap_doc = await _enrich_recap_doc_with_seat_money_context(d, recap_doc)
    structured_v2 = builder.build(
        trade_date=d,
        recap_doc=recap_doc,
        recap_snapshot_version=str(row.get("snapshot_version") or ""),
    )
    v2 = structured_v2

    # ── PR-14A: enrich with engine report on every read ──
    try:
        from stock_processing_service.application.services.post_market_engine_report_composer import (
            PostMarketEngineReportComposer,
        )
        composer = PostMarketEngineReportComposer()
        composer_input = {**recap_doc, **v2}
        engine_report = composer.compose(composer_input)
        v2 = {**v2, **engine_report}
        for key in ("daily_recap_essentials", "limit_up_ladder", "limit_up_theme_events", "new_high_summary", "seat_money_summary"):
            if key in structured_v2:
                v2[key] = structured_v2[key]
    except Exception:
        pass

    v2 = await _enrich_v2_theme_names(v2, d)

    v2["watchlists"] = await _build_one_to_two_watchlists(d)

    # ── 响应瘦身：裁剪前端不需要的冗余数据 ──
    v2 = _trim_daily_review_v2_response(v2)

    # ── Phase 4.5.3: enrich with workbench approval metadata (non-blocking) ──
    try:
        v2["workbench_approval"] = await _check_workbench_approval(d)
    except Exception:
        v2["workbench_approval"] = {"error": "approval check failed"}

    # ── Phase 4.5.5: enrich with workbench section content from draft or snapshot ──
    try:
        v2 = _enrich_v2_with_workbench_sections(v2, d)
    except Exception:
        pass

    return v2


@app.post("/api/v2/post-market/daily-review-v2/generate")
async def generate_daily_review_v2(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate and store DailyReview V2 under recap_doc.daily_review_v2."""
    p = payload or {}
    trade_date_str = str(p.get("trade_date") or p.get("date") or "")
    force = bool(p.get("force", False))
    try:
        d = date.fromisoformat(trade_date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date: {trade_date_str}") from exc

    from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
        PostMarketDailyReviewV2Builder,
    )

    row = await _fetch_latest_post_market_recap_snapshot_row(d)
    builder = PostMarketDailyReviewV2Builder()
    if not row:
        v2 = builder.build(trade_date=d, recap_doc=None)
        return {
            "ok": False,
            "status": "failed_precondition",
            "trade_date": trade_date_str,
            "schema_version": v2["schema_version"],
            "snapshot_version": v2["snapshot_version"],
            "module_coverage": v2["diagnostics"]["module_coverage"],
            "error_code": "POST_MARKET_RECAP_SNAPSHOT_NOT_FOUND",
        }

    normalized = _normalize_recap_payload(row)
    recap_doc = normalized.get("recap_doc") or normalized
    if not isinstance(recap_doc, dict):
        recap_doc = {}

    recap_doc = await _enrich_recap_doc_with_limit_up_board_counts(d, recap_doc)
    recap_doc = await _enrich_recap_doc_with_new_high_summary(d, recap_doc)
    recap_doc = await _enrich_recap_doc_with_seat_money_context(d, recap_doc)

    # ── Self-healing: inject abnormal_reviews from DB if recap_doc has none ──
    if not recap_doc.get("abnormal_reviews"):
        context = recap_doc.get("report_context") or {}
        if not isinstance(context, dict):
            context = {}
        if not context.get("stock_abnormal_signal") and not context.get("abnormal_signals"):
            try:
                pool = getattr(app.state.gateway, "_client", None)
                pool = getattr(pool, "pool", None) if pool else None
                if pool is not None:
                    async with pool.acquire() as conn:
                        ar_rows = await conn.fetch(
                            "SELECT stock_id, stock_name, subject_key, turnover_rate,"
                            " abnormal_composite_score, abnormal_labels, conclusion,"
                            " volume_ratio_to_ma50, main_net_inflow"
                            " FROM stock_abnormal_signal"
                            " WHERE trade_date = $1::date"
                            " ORDER BY abnormal_composite_score DESC",
                            d,
                        )
                        if ar_rows:
                            recap_doc["abnormal_reviews"] = [dict(r) for r in ar_rows]
            except Exception:
                pass

    structured_v2 = builder.build(
        trade_date=d,
        recap_doc=recap_doc,
        recap_snapshot_version=str(row.get("snapshot_version") or ""),
    )
    v2 = structured_v2

    # ── P0: 事件→题材因果链 ──
    theme_driver_events = None
    try:
        from stock_processing_service.application.services.event_driver_tracer import (
            EventDriverTracer,
        )
        pool = getattr(app.state.gateway, "_client", None)
        pool = getattr(pool, "pool", None) if pool else None
        if pool is not None:
            tracer = EventDriverTracer(pool)
            limit_up_matrix = v2.get("limit_up_theme_matrix") or {}
            matrix_columns = limit_up_matrix.get("columns") or []
            if matrix_columns:
                theme_driver_events = await tracer.trace_theme_rows(
                    matrix_columns, d, per_theme_limit=2,
                )
            # 重新 build 并注入 driver_events
            structured_v2 = builder.build(
                trade_date=d,
                recap_doc=recap_doc,
                recap_snapshot_version=str(row.get("snapshot_version") or ""),
                theme_driver_events=theme_driver_events,
            )
            v2 = structured_v2
    except Exception as exc:
        logger.warning("EventDriverTracer enrichment skipped: %s", exc)

    # ── PR-14A: compose engine report into DailyReviewV2 ──
    try:
        from stock_processing_service.application.services.post_market_engine_report_composer import (
            PostMarketEngineReportComposer,
        )
        composer = PostMarketEngineReportComposer()
        composer_input = {**recap_doc, **v2}
        engine_report = composer.compose(composer_input)
        v2 = {**v2, **engine_report}
        for key in ("daily_recap_essentials", "limit_up_ladder", "limit_up_theme_events", "new_high_summary", "seat_money_summary"):
            if key in structured_v2:
                v2[key] = structured_v2[key]
    except Exception:
        pass  # best-effort, don't block

    v2 = await _enrich_v2_theme_names(v2, d)

    v2["watchlists"] = await _build_one_to_two_watchlists(d)

    updated_recap_doc = dict(recap_doc)
    if isinstance(v2.get("limit_up_theme_matrix"), dict):
        updated_recap_doc["limit_up_theme_matrix"] = v2["limit_up_theme_matrix"]
    updated_recap_doc["daily_review_v2"] = v2
    updated_payload = dict(normalized)
    updated_payload["recap_doc"] = updated_recap_doc

    affected = await app.state.gateway.upsert_post_market_recap_snapshot(
        {
            "trade_date": d,
            "snapshot_version": str(row.get("snapshot_version") or ""),
            "batch_id": str(row.get("batch_id") or ""),
            "trace_id": str(row.get("trace_id") or ""),
            "payload": updated_payload,
            "source_name": "stock_processing_service",
        }
    )
    return {
        "ok": True,
        "status": "success" if affected else "skipped_idempotent",
        "trade_date": trade_date_str,
        "schema_version": v2["schema_version"],
        "snapshot_version": v2["snapshot_version"],
        "affected_rows": affected,
        "module_coverage": v2["diagnostics"]["module_coverage"],
    }


def _daily_review_v2_has_limit_up_ladder(v2: dict[str, Any]) -> bool:
    ladder = v2.get("limit_up_ladder")
    if not isinstance(ladder, dict):
        return False
    board_rows = ladder.get("board_rows")
    if not isinstance(board_rows, list):
        return False
    return any(isinstance(row, dict) and int(row.get("stock_count") or 0) > 0 for row in board_rows)


async def _enrich_recap_doc_with_limit_up_board_counts(trade_date: date, recap_doc: dict[str, Any]) -> dict[str, Any]:
    """Materialize board counts from `stock_daily_snapshot` for DailyReview V2."""
    try:
        from stock_processing_service.application.services.limit_up_board_recalculator import (
            LimitUpBoardRecalculator,
        )

        recalculator = LimitUpBoardRecalculator()
        client = getattr(app.state.gateway, "_client", None)
        pool = getattr(client, "pool", None) if client else None
        logger.warning(
            "limit_up board recompute: client=%s pool=%s dsn_builder=%s",
            bool(client),
            bool(pool),
            bool(callable(getattr(client, "_build_dsn", None))),
        )
        if pool is not None:
            async with pool.acquire() as conn:
                enriched = await recalculator.enrich_recap_doc(recap_doc, trade_date, conn)
                logger.warning("limit_up board recompute: via_pool done")
                return enriched

        dsn_builder = getattr(client, "_build_dsn", None)
        if callable(dsn_builder):
            import asyncpg

            conn = await asyncpg.connect(dsn=dsn_builder())
            try:
                enriched = await recalculator.enrich_recap_doc(recap_doc, trade_date, conn)
                logger.warning("limit_up board recompute: via_dsn done")
                return enriched
            finally:
                await conn.close()
        return recap_doc
    except Exception:
        logger.exception("limit_up board recomputation skipped")
        return recap_doc


async def _enrich_recap_doc_with_new_high_summary(trade_date: date, recap_doc: dict[str, Any]) -> dict[str, Any]:
    """Materialize innovation-high summary from `stock_daily_snapshot` for DailyReview V2."""
    try:
        existing = recap_doc.get("new_high_summary")
        if isinstance(existing, dict) and existing.get("representative_stocks"):
            return recap_doc

        client = getattr(app.state.gateway, "_client", None)
        pool = getattr(client, "pool", None) if client else None
        if pool is None:
            dsn_builder = getattr(client, "_build_dsn", None)
            if not callable(dsn_builder):
                return recap_doc
            import asyncpg
            conn = await asyncpg.connect(dsn=dsn_builder())
            try:
                enriched = await _build_new_high_summary_from_conn(trade_date, recap_doc, conn)
                return enriched
            finally:
                await conn.close()
        async with pool.acquire() as conn:
            return await _build_new_high_summary_from_conn(trade_date, recap_doc, conn)
    except Exception:
        logger.exception("new_high summary recomputation skipped")
        return recap_doc


async def _build_new_high_summary_from_conn(trade_date: date, recap_doc: dict[str, Any], conn) -> dict[str, Any]:
    from datetime import timedelta

    rows = await conn.fetch(
        """
        WITH hist AS (
            SELECT
                split_part(stock_id, '.', 1) AS stock_key,
                trade_date,
                high_price,
                MAX(high_price) OVER (
                    PARTITION BY split_part(stock_id, '.', 1)
                    ORDER BY trade_date
                    ROWS BETWEEN 250 PRECEDING AND 1 PRECEDING
                ) AS prev_250_high
            FROM stock_daily_snapshot
            WHERE trade_date >= $1::date - INTERVAL '260 days'
              AND trade_date <= $1::date
              AND source_name LIKE 'tushare%'
        )
        SELECT
            h.trade_date,
            h.stock_key,
            h.high_price,
            COALESCE(s.name, h.stock_key) AS stock_name,
            COALESCE(gp.concept, '') AS industry_name
        FROM hist h
        LEFT JOIN stocks s ON s.stock_id = h.stock_key
        LEFT JOIN stock_gate_profile gp ON gp.stock_id = h.stock_key
        WHERE h.trade_date = ANY($2::date[])
          AND h.prev_250_high IS NOT NULL
          AND h.high_price >= h.prev_250_high
        ORDER BY h.trade_date DESC, h.high_price DESC, h.stock_key
        """,
        trade_date,
        [trade_date, trade_date - timedelta(days=1), trade_date - timedelta(days=2)],
    )
    if not rows:
        return recap_doc

    by_date: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        trade_day = row.get("trade_date")
        by_date.setdefault(trade_day, []).append(dict(row))

    today_rows = by_date.get(trade_date, [])
    yesterday_rows = by_date.get(trade_date - timedelta(days=1), [])
    day_before_rows = by_date.get(trade_date - timedelta(days=2), [])

    classified_rows = [
        row for row in today_rows if str(row.get("industry_name") or "").strip()
    ]
    unclassified_count = len(today_rows) - len(classified_rows)
    classification_rate = (
        len(classified_rows) / len(today_rows) if today_rows else 0.0
    )
    industry_rows: dict[str, list[dict[str, Any]]] = {}
    for row in today_rows:
        key = str(row.get("industry_name") or "未分类").strip() or "未分类"
        industry_rows.setdefault(key, []).append(row)
    industry_summary = [
        {
            "industry_name": name,
            "count": len(items),
            "representative_stocks": items[:3],
        }
        for name, items in sorted(industry_rows.items(), key=lambda item: (-len(item[1]), item[0]))[:5]
    ]
    summary = "暂无结构化创新高数据"
    if today_rows:
        industries = "、".join(
            item["industry_name"]
            for item in industry_summary
            if item.get("industry_name") not in {"未分类", "未知"}
        ) or "暂无明确行业聚焦"
        reps = "、".join([item["stock_name"] for item in today_rows[:4] if item.get("stock_name")]) or "暂无代表股"
        summary = (
            f"今日创新高 {len(today_rows)} 家；行业已识别 {len(classified_rows)} 家"
            f"（{classification_rate:.0%}），已分类方向为 {industries}；代表股 {reps}。"
        )

    enriched = dict(recap_doc)
    enriched["new_high_summary"] = {
        "summary": summary,
        "today_count": len(today_rows),
        "yesterday_count": len(yesterday_rows),
        "day_before_count": len(day_before_rows),
        "industry_summary": industry_summary,
        "representative_stocks": today_rows[:10],
        "diagnostics": {
            "source": "recomputed_from_stock_daily_snapshot",
            "row_count": len(today_rows),
            "classified_count": len(classified_rows),
            "unclassified_count": unclassified_count,
            "classification_rate": classification_rate,
        },
    }
    return enriched


async def _enrich_v2_theme_names(v2: dict[str, Any], trade_date: date) -> dict[str, Any]:
    """Translate numeric subject keys in V2 payload to readable theme names."""
    if not isinstance(v2, dict):
        return v2

    subject_keys: list[str] = []

    def collect_keys(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("subject_key", "theme_name"):
                value = str(row.get(key) or "").strip()
                if value and value.isdigit():
                    subject_keys.append(value)

    collect_keys(v2.get("stock_capital_reviews"))
    collect_keys(v2.get("theme_capital_reviews"))
    seat_money = v2.get("seat_money_summary")
    if isinstance(seat_money, dict):
        for key in ("institution_top_buys", "institution_top_sells", "hot_money_top_buys", "hot_money_top_sells", "theme_rows"):
            collect_keys(seat_money.get(key))

    subject_keys = sorted(set(subject_keys))
    if not subject_keys:
        return v2

    theme_map = await _resolve_theme_name_map(subject_keys, trade_date)
    if not theme_map:
        return v2

    def normalize_rows(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("subject_key") or row.get("theme_name") or "").strip()
            if key and key in theme_map:
                row["theme_name"] = theme_map.get(key, key)

    normalize_rows(v2.get("stock_capital_reviews"))
    normalize_rows(v2.get("theme_capital_reviews"))
    if isinstance(seat_money, dict):
        for key in ("institution_top_buys", "institution_top_sells", "hot_money_top_buys", "hot_money_top_sells", "theme_rows"):
            normalize_rows(seat_money.get(key))

        institution_names = [
            str(row.get("stock_name") or "").strip()
            for row in (seat_money.get("institution_top_buys") or [])[:3]
            if isinstance(row, dict) and str(row.get("stock_name") or "").strip()
        ]
        hot_money_names = [
            str(row.get("stock_name") or "").strip()
            for row in (seat_money.get("hot_money_top_buys") or [])[:3]
            if isinstance(row, dict) and str(row.get("stock_name") or "").strip()
        ]
        theme_names = [
            str(row.get("theme_name") or "").strip()
            for row in (seat_money.get("theme_rows") or [])[:3]
            if isinstance(row, dict) and str(row.get("theme_name") or "").strip()
        ]
        if institution_names or hot_money_names or theme_names:
            parts: list[str] = []
            if institution_names:
                parts.append(f"机构关注 {'、'.join(institution_names)}")
            if hot_money_names:
                parts.append(f"游资关注 {'、'.join(hot_money_names)}")
            cohesion = str(seat_money.get("cohesion") or "").strip()
            if cohesion and cohesion != "--":
                parts.append(f"资金{cohesion}")
            if theme_names:
                parts.append(f"主题聚焦 {'、'.join(theme_names)}")
            seat_money["summary"] = "，".join(parts)

    return v2


async def _enrich_recap_doc_with_seat_money_context(trade_date: date, recap_doc: dict[str, Any]) -> dict[str, Any]:
    """Inject structured dragon_tiger_object / hot_money_trading_activity facts when snapshot is missing them."""
    try:
        context = recap_doc.get("report_context") if isinstance(recap_doc.get("report_context"), dict) else {}
        dragon_missing = not (isinstance(context.get("dragon_tiger"), list) and context.get("dragon_tiger"))
        hot_money_missing = not (isinstance(context.get("hot_money_activities"), list) and context.get("hot_money_activities"))
        if not dragon_missing and not hot_money_missing:
            return recap_doc

        client = getattr(app.state.gateway, "_client", None)
        fetch_context = getattr(client, "get_post_market_report_context", None)
        if not callable(fetch_context):
            return recap_doc

        report_context = await fetch_context(trade_date)
        if not isinstance(report_context, dict):
            return recap_doc

        enriched = dict(recap_doc)
        merged_context = dict(context)
        if dragon_missing and isinstance(report_context.get("dragon_tiger"), list) and report_context.get("dragon_tiger"):
            merged_context["dragon_tiger"] = report_context["dragon_tiger"]
        if hot_money_missing and isinstance(report_context.get("hot_money_activities"), list) and report_context.get("hot_money_activities"):
            merged_context["hot_money_activities"] = report_context["hot_money_activities"]
        if isinstance(report_context.get("theme_name_map"), dict) and report_context.get("theme_name_map") and not merged_context.get("theme_name_map"):
            merged_context["theme_name_map"] = report_context["theme_name_map"]
        if merged_context:
            enriched["report_context"] = merged_context
        if dragon_missing and isinstance(report_context.get("dragon_tiger"), list) and report_context.get("dragon_tiger"):
            enriched["dragon_tiger_reviews"] = report_context["dragon_tiger"]
        if hot_money_missing and isinstance(report_context.get("hot_money_activities"), list) and report_context.get("hot_money_activities"):
            enriched["hot_money_activities"] = report_context["hot_money_activities"]
        return enriched
    except Exception:
        logger.exception("seat money context recomputation skipped")
        return recap_doc


async def _fetch_latest_post_market_recap_snapshot_row(trade_date: date) -> dict[str, Any] | None:
    """Bypass gateway caching and read the latest recap snapshot directly."""
    try:
        client = getattr(app.state.gateway, "_client", None)
        pool = getattr(client, "pool", None) if client else None
        if pool is not None:
            row = await pool.fetchrow(
                """
                SELECT trade_date, snapshot_version, batch_id, trace_id, payload
                FROM post_market_recap_snapshot
                WHERE trade_date = $1::date
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                trade_date,
            )
            return dict(row) if row else None

        dsn_builder = getattr(client, "_build_dsn", None)
        if callable(dsn_builder):
            import asyncpg
            conn = await asyncpg.connect(dsn=dsn_builder())
            try:
                row = await conn.fetchrow(
                    """
                    SELECT trade_date, snapshot_version, batch_id, trace_id, payload
                    FROM post_market_recap_snapshot
                    WHERE trade_date = $1::date
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    trade_date,
                )
                return dict(row) if row else None
            finally:
                await conn.close()
    except Exception:
        logger.exception("failed to fetch recap snapshot directly")
    return None


# ── P1: PostMarket Readiness API ──

@app.get("/api/v1/post-market/derived-data/readiness")
async def get_post_market_readiness(date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """查询盘后复盘派生数据 readiness 状态。"""
    from datetime import date as _date
    from stock_processing_service.application.services.post_market_readiness_service import (
        PostMarketReadinessService,
    )
    try:
        d = _date.fromisoformat(date)
    except ValueError:
        return {"status": "error", "error_code": "INVALID_DATE", "message": f"invalid date: {date}"}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None
    service = PostMarketReadinessService(pool=pool)
    result = await service.check(d)

    # P1-3: 写入 post_market_derived_readiness 状态
    try:
        from stock_processing_service.application.services.post_market_job_status_service import (
            PostMarketJobStatusService,
        )
        jss = PostMarketJobStatusService(pool=pool)
        await jss.mark_finished(
            trade_date_val=d,
            job_key="post_market_derived_readiness",
            status="success" if result.status == "ready" else "failed_precondition",
            error_code=result.error_code or None,
            diagnostics={"readiness": result.to_dict()},
        )
    except Exception as exc:
        logger.warning("failed to write job status: %s", exc)

    return result.to_dict()


@app.get("/api/v1/post-market/jobs/status")
async def get_post_market_jobs_status(date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """查询盘后复盘各阶段任务状态。"""
    from datetime import date as _date
    from stock_processing_service.application.services.post_market_job_status_service import (
        PostMarketJobStatusService,
    )
    try:
        d = _date.fromisoformat(date)
    except ValueError:
        return {"status": "error", "error_code": "INVALID_DATE", "message": f"invalid date: {date}"}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None
    jss = PostMarketJobStatusService(pool=pool)
    return await jss.summary_by_date(d)


# ── P1-4: PostMarket derived-data generate ──

@app.post("/api/v1/post-market/derived-data/generate")
async def generate_post_market_derived_data(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成每日动态复盘派生数据。P1阶段只做任务壳+状态流转，派生算法在P2实现。"""
    p = payload or {}
    trade_date_str = str(p.get("trade_date") or p.get("date") or "")
    from datetime import date as _date
    try:
        d = _date.fromisoformat(trade_date_str)
    except ValueError:
        return {"ok": False, "status": "error", "error_code": "INVALID_DATE", "message": f"invalid date: {trade_date_str}"}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None

    from stock_processing_service.application.use_cases.generate_post_market_derived_data import (
        PostMarketDerivedDataGenerateUseCase,
    )
    db_manager = getattr(getattr(app.state, "gateway", None), "_client", None)
    uc = PostMarketDerivedDataGenerateUseCase(pool=pool, db_manager=db_manager)
    uc.register_theme_cycle_truth()
    uc.register_dragon_tiger_object_build()
    uc.register_hot_money_activity_build(project_root=str(_project_root()))
    uc.register_theme_leader_candidate_build(project_root=str(_project_root()))
    uc.register_money_flow_enhanced_build(project_root=str(_project_root()))
    uc.register_stock_abnormal_signal_build(project_root=str(_project_root()))
    uc.register_strong_stock_watch_build()
    result = await uc.execute(d, force=bool(p.get("force", False)))
    return {
        "ok": result.status == "success",
        "trade_date": result.trade_date,
        "job_key": "post_market_derived_data",
        "status": result.status,
        "before_readiness": result.before_readiness,
        "after_readiness": result.after_readiness,
        "job_results": result.job_results,
        "missing_tables": result.missing_tables,
    }


# ── P1-5: PostMarket recap generate ──

@app.post("/api/v1/post-market/recap/generate")
async def generate_post_market_recap(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成盘后复盘报告快照。readiness 门禁 + 调用 DailyReview 生成。

    支持 async_mode=true：立即返回 202 accepted，后台执行完整 job.execute()。
    """
    p = payload or {}
    trade_date_str = str(p.get("trade_date") or p.get("date") or "")
    from datetime import date as _date
    try:
        d = _date.fromisoformat(trade_date_str)
    except ValueError:
        return {"ok": False, "status": "error", "error_code": "INVALID_DATE"}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None

    from stock_processing_service.application.services.post_market_job_status_service import (
        PostMarketJobStatusService,
    )
    from stock_processing_service.application.services.post_market_readiness_service import (
        PostMarketReadinessService,
    )
    jss = PostMarketJobStatusService(pool=pool)
    rs = PostMarketReadinessService(pool=pool)

    force = bool(p.get("force", False))
    async_mode = bool(p.get("async_mode", False))
    mode = str(p.get("mode") or "").strip()
    if not mode:
        mode = "full_truth_rebuild" if force else "read_model_only"

    # Readiness gate: for force rebuilds, readiness is advisory only —
    # the user explicitly triggered a rebuild to generate missing data.
    # For non-force (scheduled/programmatic) calls, it remains a hard gate.
    if not force:
        readiness = await rs.check(d)
        if readiness.status != "ready":
            await jss.mark_finished(d, "post_market_recap_generate", "failed_precondition",
                error_code="POST_MARKET_DERIVED_DATA_NOT_READY",
                diagnostics={"readiness": readiness.to_dict()})
            return {
                "ok": False, "trade_date": trade_date_str,
                "status": "failed_precondition",
                "error_code": "POST_MARKET_DERIVED_DATA_NOT_READY",
                "missing_tables": readiness.missing_tables,
            }

    if async_mode and force:
        from datetime import timedelta as _td
        from uuid import uuid4
        version_tag = uuid4().hex[:8]
        snapshot_version = f"daily_review_generate.{mode}.{version_tag}"
        batch_id = uuid4().hex[:12]
        trace_id = uuid4().hex[:12]

        # Check for existing running job — but allow stale running to be replaced.
        existing_status = await _read_job_status(pool, d, "post_market_recap_generate")
        if existing_status and existing_status.get("status") == "running":
            try:
                existing_diag = existing_status.get("diagnostics") or {}
                existing_snapshot_version = existing_diag.get("snapshot_version") or ""
                updated_at = existing_status.get("updated_at")
                stale_timeout_sec = 10 * 60  # 10 minutes
                is_stale = False

                if not updated_at:
                    # No timestamp — can't verify freshness, treat as stale.
                    is_stale = True
                else:
                    import datetime as _dt
                    parsed = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            parsed = _dt.datetime.strptime(str(updated_at)[:19], fmt)
                            break
                        except ValueError:
                            continue
                    if parsed is None:
                        is_stale = True
                    else:
                        parsed_utc = parsed.replace(tzinfo=_dt.timezone.utc)
                        # Running job from BEFORE this process started → always stale.
                        if parsed_utc < _STARTUP_TS:
                            is_stale = True
                        else:
                            age = (_dt.datetime.now(_dt.timezone.utc) - parsed_utc).total_seconds()
                            is_stale = age > stale_timeout_sec

                if not is_stale:
                    return {
                        "ok": True, "trade_date": trade_date_str,
                        "status": "running",
                        "message": "已有重新复盘任务正在执行",
                        "snapshot_version": existing_snapshot_version,
                        "job_name": "post_market_recap_generate",
                    }
                # stale: mark the old job as failed and continue
                await jss.mark_finished(d, "post_market_recap_generate", "failed",
                    error_code="STALE_RUNNING_JOB_REPLACED",
                    diagnostics={
                        "replaced_snapshot_version": existing_snapshot_version,
                        "new_snapshot_version": snapshot_version,
                        "reason": f"stale running replaced by new force rebuild (timeout={stale_timeout_sec}s, startup_ts={_STARTUP_TS.isoformat()})",
                    })
            except Exception:
                pass  # if stale detection fails, proceed with new rebuild

        # Mark queued before launching background task
        await jss.mark_finished(d, "post_market_recap_generate", "pending",
            diagnostics={"snapshot_version": snapshot_version, "batch_id": batch_id, "trace_id": trace_id, "mode": mode})

        job = app.state.container.build_post_market_recap

        skip_truth = mode == "read_model_only"

        import logging as _logging
        _recap_logger = _logging.getLogger("stock_processing_service.api.recap_rebuild")

        async def _run_background():
            try:
                await job.execute(
                    trade_date=d,
                    snapshot_version=snapshot_version,
                    batch_id=batch_id,
                    trace_id=trace_id,
                    lookback_days=7,
                    skip_prereqs=skip_truth,
                    skip_layer_c=skip_truth,
                )
            except Exception as exc:
                import traceback as _traceback
                _recap_logger.exception(
                    "post_market_recap async rebuild failed: trade_date=%s snapshot_version=%s",
                    trade_date_str, snapshot_version,
                )
                try:
                    # Check if job.execute already wrote detailed diagnostics
                    existing = await _read_job_status(pool, d, "post_market_recap_generate",
                                                       snapshot_version=snapshot_version)
                    existing_diag = (existing or {}).get("diagnostics") or {}
                    if (existing and existing.get("status") == "failed"
                            and (existing_diag.get("error_message")
                                 or existing_diag.get("error_type")
                                 or existing_diag.get("stage"))):
                        # Job already recorded the real error — don't overwrite
                        _recap_logger.info(
                            "preserved job diagnostics: trade_date=%s snapshot_version=%s error_type=%s",
                            trade_date_str, snapshot_version,
                            existing_diag.get("error_type", "unknown"),
                        )
                        return
                    await jss.mark_finished(d, "post_market_recap_generate", "failed",
                        error_code=type(exc).__name__ or "RECAP_BUILD_EXCEPTION",
                        diagnostics={
                            "snapshot_version": snapshot_version, "batch_id": batch_id,
                            "trace_id": trace_id, "mode": mode,
                            "stage": "api_background_exception",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc) or repr(exc),
                            "traceback": _traceback.format_exc()[-4000:],
                        })
                except Exception:
                    _recap_logger.exception("failed to mark job as failed after exception")

        import asyncio as _asyncio
        _asyncio.create_task(_run_background())

        return {
            "ok": True, "trade_date": trade_date_str,
            "status": "accepted",
            "snapshot_version": snapshot_version,
            "job_name": "post_market_recap_generate",
            "poll_interval_sec": 3,
            "mode": mode,
        }

    # Synchronous mode (original behavior)
    return await generate_daily_review({
        "date": trade_date_str,
        "mode": mode,
        "force": force,
    })


async def _read_job_status(
    pool, trade_date, job_key: str, *, snapshot_version: str = ""
) -> dict[str, Any] | None:
    """Read job status for trade_date + job_key.

    When snapshot_version is provided, ONLY match that version — no fallback.
    Fallback to latest row ONLY when snapshot_version is empty.
    """
    if pool is None:
        return None
    import json as _json
    async with pool.acquire() as conn:
        if snapshot_version:
            row = await conn.fetchrow("""
                SELECT status, error_code, diagnostics, updated_at
                FROM post_market_job_status
                WHERE trade_date = $1::date
                  AND job_key = $2
                  AND diagnostics->>'snapshot_version' = $3
                ORDER BY updated_at DESC LIMIT 1
            """, trade_date, job_key, snapshot_version)
            if not row:
                return None  # version-specific query: no fallback
        else:
            row = await conn.fetchrow("""
                SELECT status, error_code, diagnostics, updated_at
                FROM post_market_job_status
                WHERE trade_date = $1::date AND job_key = $2
                ORDER BY updated_at DESC LIMIT 1
            """, trade_date, job_key)
        if not row:
            return None
        diag = row.get("diagnostics")
        if isinstance(diag, str):
            diag = _json.loads(diag)
        updated_at = row.get("updated_at")
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        return {
            "status": row["status"],
            "error_code": row.get("error_code"),
            "diagnostics": diag or {},
            "updated_at": str(updated_at) if updated_at else "",
        }


@app.get("/api/v1/post-market/recap/generate/status")
async def get_post_market_recap_generate_status(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    snapshot_version: str = Query("", description="optional snapshot_version filter"),
) -> dict[str, Any]:
    """查询重新复盘任务状态。"""
    from datetime import date as _date
    try:
        d = _date.fromisoformat(trade_date)
    except ValueError:
        return {"ok": False, "status": "error", "error_code": "INVALID_DATE"}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None

    status_row = await _read_job_status(
        pool, d, "post_market_recap_generate",
        snapshot_version=snapshot_version or "",
    )

    if not status_row:
        return {
            "ok": True, "trade_date": trade_date,
            "status": "unknown",
            "message": "no job status record found",
            "snapshot_version": snapshot_version or "",
        }

    # Check if snapshot exists for this date
    snapshot_ready = False
    if status_row["status"] == "success" and pool is not None:
        try:
            async with pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT 1 FROM post_market_recap_snapshot WHERE trade_date = $1::date LIMIT 1",
                    d,
                )
                snapshot_ready = bool(exists)
        except Exception:
            pass

    diag = status_row.get("diagnostics") or {}
    updated_at = status_row.get("updated_at")
    elapsed_sec: float | None = None
    if updated_at:
        import datetime as _dt
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = _dt.datetime.strptime(str(updated_at)[:19], fmt)
                elapsed_sec = (_dt.datetime.now(_dt.timezone.utc) - parsed.replace(tzinfo=_dt.timezone.utc)).total_seconds()
                break
            except ValueError:
                continue

    return {
        "ok": True,
        "trade_date": trade_date,
        "snapshot_version": snapshot_version or diag.get("snapshot_version", ""),
        "job_name": "post_market_recap_generate",
        "status": status_row["status"],
        "error_code": status_row.get("error_code"),
        "diagnostics": diag,
        "updated_at": updated_at,
        "snapshot_ready": snapshot_ready,
        "mode": diag.get("mode", ""),
        "elapsed_sec": round(elapsed_sec, 1) if elapsed_sec is not None else None,
        "stage": diag.get("stage", ""),
    }


# ── P1: DailyReview fast generate (read_model_only) ──

@app.post("/api/v1/daily_review/generate")
async def generate_daily_review(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成 DailyReview 快照 — read_model_only 模式只读已有对象，不触发事实层生产。

    mode=read_model_only (默认): 只读已有对象，10-30 秒。
    mode=full_truth_rebuild: 重跑 evidence/cycle/identity/mainline/LayerC，5-10 分钟 (危险)。
    """
    p = payload or {}
    trade_date_str = str(p.get("date") or p.get("trade_date") or "")
    mode = str(p.get("mode") or "read_model_only")
    force = bool(p.get("force", False))

    if not trade_date_str:
        raise HTTPException(status_code=400, detail="date is required")

    td = date.fromisoformat(trade_date_str)
    skip_truth = mode == "read_model_only"

    try:
        from uuid import uuid4
        batch_id = uuid4().hex[:12]; trace_id = uuid4().hex[:12]
        version_tag = uuid4().hex[:8] if force else "v2"

        job = app.state.container.build_post_market_recap
        result = await job.execute(
            trade_date=td,
            snapshot_version=f"daily_review_generate.{mode}.{version_tag}",
            batch_id=batch_id,
            trace_id=trace_id,
            lookback_days=7,
            skip_prereqs=skip_truth,
            skip_layer_c=skip_truth,
        )

        return {
            "status": result.status,
            "trade_date": trade_date_str,
            "mode": mode,
            "affected_rows": result.affected_rows,
            "metrics": result.metrics,
        }
    except Exception as exc:
        import traceback as _traceback
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": type(exc).__name__,
                "message": str(exc) or repr(exc),
                "traceback": _traceback.format_exc()[-4000:],
            },
        ) from exc


@app.get("/api/v1/theme/workspace/{subject_key}")
async def get_theme_workspace(subject_key: str, trade_date: str = "") -> dict[str, Any]:
    """题材工作台：读取 stock_data_test 中的题材相关数据。"""
    try:
        from asyncpg import connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await connect(host="localhost", port=5432, database=db, user=os.environ.get("PG_USERNAME","postgres"), password=os.environ.get("PG_PASSWORD",""))
    except Exception as e:
        return {"subject_key": subject_key, "detail": {}, "diagnostics": {"partial": True, "missing_sections": [str(e)]}}

    td_raw = trade_date or str((await conn.fetchrow("SELECT max(trade_date) FROM subject_stock_daily_snapshot"))[0] or "")
    td_date = date.fromisoformat(td_raw) if td_raw else date.today()
    result: dict[str, Any] = {"subject_key": subject_key, "trade_date": td_raw, "detail": {}, "analytics": {}}

    try:
        # Theme name from theme_gate_profile
        name_row = await conn.fetchrow("SELECT concept FROM theme_gate_profile WHERE subject_key=$1", subject_key)
        theme_name = name_row["concept"] if name_row else subject_key

        # Build detail dict
        detail: dict[str, Any] = {"theme_name": theme_name}
        v2 = await conn.fetchrow("SELECT theme_name, summary, detail_html, reason_short FROM vw_theme_detail_joined WHERE subject_key=$1 LIMIT 1", subject_key)
        if v2:
            detail["theme_name"] = v2.get("theme_name") or theme_name
            detail["summary"] = v2.get("summary","")
            detail["detail_html"] = v2.get("detail_html","")
            detail["reason_short"] = v2.get("reason_short","")

        # History items from subject_history_staging
        hist = await conn.fetch("SELECT * FROM subject_history_staging WHERE subject_key=$1 ORDER BY rank_date DESC LIMIT 8", subject_key)
        result["history"] = [dict(r) for r in hist]
        detail["history_count"] = len(result["history"])

        # Child themes from subject_children_staging
        child = await conn.fetch("SELECT * FROM subject_children_staging WHERE parent_subject_key=$1 LIMIT 8", subject_key)
        result["children"] = [dict(r) for r in child]
        detail["children_count"] = len(result["children"])

        # Stock items from subject_stock_staging
        stocks = await conn.fetch("SELECT * FROM subject_stock_staging WHERE subject_key=$1 LIMIT 12", subject_key)
        result["stocks"] = [dict(r) for r in stocks]
        detail["stock_count"] = len(result["stocks"])

        # Graph: hierarchical children + stocks for 题材图谱 tab
        graph: dict[str, Any] = {
            "root": {
                "name": theme_name,
                "subject_key": subject_key,
                "pct_chg": None,
            },
            "children": [],
            "uncategorized_stocks": [],
        }
        # Root pct_chg from recent rank
        root_rank = await conn.fetchrow(
            "SELECT pct_chg FROM subject_history_staging WHERE subject_key=$1 ORDER BY rank_date DESC LIMIT 1",
            subject_key,
        )
        if root_rank and root_rank["pct_chg"] is not None:
            graph["root"]["pct_chg"] = float(root_rank["pct_chg"])

        # Children with per-child stocks
        graph_children = await conn.fetch(
            "SELECT * FROM subject_children_staging WHERE parent_subject_key=$1 ORDER BY sort LIMIT 20",
            subject_key,
        )
        for ch in graph_children:
            child_node: dict[str, Any] = {
                "name": ch["child_name"] or ch["child_subject_key"],
                "child_subject_key": ch["child_subject_key"],
                "pct_chg": float(ch["pct_chg"]) if ch["pct_chg"] is not None else None,
                "stocks": [],
            }
            # Stocks under this child
            child_stocks = await conn.fetch(
                "SELECT stock_id, stock_name, reason FROM subject_child_stock_reason "
                "WHERE subject_key=$1 AND child_name=$2 ORDER BY sort_order LIMIT 20",
                subject_key, ch["child_name"],
            )
            for cs in child_stocks:
                child_node["stocks"].append({
                    "stock_id": cs["stock_id"],
                    "stock_name": cs["stock_name"],
                    "reason": cs["reason"] or "",
                })
            graph["children"].append(child_node)

        # Uncategorized stocks (cdp_extracted or no child_name)
        uncat = await conn.fetch(
            "SELECT stock_id, stock_name, reason FROM subject_child_stock_reason "
            "WHERE subject_key=$1 AND (child_name='cdp_extracted' OR child_name IS NULL OR child_name='') "
            "ORDER BY sort_order LIMIT 50",
            subject_key,
        )
        for us in uncat:
            graph["uncategorized_stocks"].append({
                "stock_id": us["stock_id"],
                "stock_name": us["stock_name"],
                "reason": us["reason"] or "",
            })
        result["graph"] = graph

        result["detail"] = detail

        # Analytics: summary from theme_cycle_judgement_v2
        cycle = await conn.fetchrow("SELECT * FROM theme_cycle_judgement_v2 WHERE subject_key=$1 ORDER BY trade_date DESC LIMIT 1", subject_key)
        analytics_summary = dict(cycle) if cycle else None

        # Analytics: recent rank for trend (from subject_history_staging)
        ranks = await conn.fetch("SELECT * FROM subject_history_staging WHERE subject_key=$1 ORDER BY rank_date DESC LIMIT 5", subject_key)
        recent_rank = [dict(r) for r in ranks]

        # Analytics: leader stocks (enriched with daily snapshot + money_flow + position + pattern)
        ranked = await conn.fetch(
            """SELECT l.*,
               s.close_price, s.pct_chg, s.trade_date,
               s.is_leader, s.rank_order,
               CASE WHEN jsonb_typeof(s.raw_json)='array' AND jsonb_array_length(s.raw_json)>17
                    THEN NULLIF(s.raw_json->>17,'')::numeric END AS volume_ratio,
               CASE WHEN jsonb_typeof(s.raw_json)='array' AND jsonb_array_length(s.raw_json)>20
                    THEN NULLIF(s.raw_json->>20,'')::integer END AS current_flag,
               COALESCE(m.main_net_inflow,
                 CASE WHEN jsonb_typeof(s.raw_json)='array' AND jsonb_array_length(s.raw_json)>35
                      THEN NULLIF(s.raw_json->>35,'')::numeric END
               ) AS main_net_inflow,
               m.money_flow_tier, m.role_enhanced,
               p.position_label,
               x.pattern_labels
            FROM theme_stock_leaderboard l
            LEFT JOIN subject_stock_daily_snapshot s ON s.stock_id=l.stock_id AND s.subject_key=l.subject_key AND s.trade_date=$2
            LEFT JOIN money_flow_enhanced m ON m.trade_date=s.trade_date AND m.subject_key=s.subject_key AND split_part(m.stock_id,'.',1)=split_part(s.stock_id,'.',1)
            LEFT JOIN stock_position_judgement p ON p.trade_date=s.trade_date AND split_part(p.stock_id,'.',1)=split_part(s.stock_id,'.',1)
            LEFT JOIN stock_pattern_judgement x ON x.trade_date=s.trade_date AND split_part(x.stock_id,'.',1)=split_part(s.stock_id,'.',1)
            WHERE l.subject_key=$1 ORDER BY l.leader_score DESC LIMIT 20""",
            subject_key, td_date
        )
        leader_stocks = [dict(r) for r in ranked]

        result["analytics"] = {
            "trade_date": td_raw,
            "summary": analytics_summary,
            "recent_rank": recent_rank,
            "leader_stocks": leader_stocks,
        }
        result["diagnostics"] = {"partial": False, "missing_sections": [], "source": "sps"}
    except Exception as e:
        result["diagnostics"] = {"partial": True, "missing_sections": [str(e)]}
    finally:
        await conn.close()
    return result


@app.get("/api/v1/stock/workspace/{stock_id}")
async def get_stock_workspace(stock_id: str) -> dict[str, Any]:
    """个股工作台：读取 stock_data_test 中的个股相关数据。"""
    try:
        from asyncpg import connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
    except Exception as e:
        return {"stock_id": stock_id, "diagnostics": {"partial": True, "missing_sections": [str(e)]}}

    code = stock_id.split(".")[0] if "." in stock_id else stock_id
    result: dict[str, Any] = {"stock_id": stock_id}

    try:
        # stock_detail
        row = await conn.fetchrow(
            "SELECT stock_id, stock_name, close_price as price, close_price as pct_chg FROM subject_stock_daily_snapshot WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 1", code
        )
        result["stock_detail"] = dict(row) if row else {"name": stock_id}

        # themes
        themes = await conn.fetch(
            "SELECT DISTINCT subject_key, theme_name FROM strong_stock_watch_pool WHERE split_part(stock_id,'.',1)=$1 AND watch_status!='removed'", code
        )
        result["themes"] = [dict(r) for r in themes]

        # money_flow
        mf = await conn.fetch(
            "SELECT * FROM money_flow_enhanced WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 6", code
        )
        result["money_flow"] = [dict(r) for r in mf]

        # dragon_tiger
        dt = await conn.fetch(
            "SELECT * FROM dragon_tiger_object WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 5", code
        )
        result["dragon_tiger"] = [dict(r) for r in dt]

        # auction_validation
        av = await conn.fetch(
            "SELECT * FROM pre_market_auction_signal_validation WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 6", code
        )
        result["auction_validation"] = [dict(r) for r in av]

        # kline position
        pos = await conn.fetchrow(
            "SELECT * FROM stock_position_judgement WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 1", code
        )
        # kline pattern
        pat = await conn.fetchrow(
            "SELECT * FROM stock_pattern_judgement WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 1", code
        )
        result["kline"] = {"position": dict(pos) if pos else None, "pattern": dict(pat) if pat else None}

        # stock_lightspots
        spots = await conn.fetch(
            "SELECT content, biz_key, created_at FROM stock_lightspots WHERE split_part(stock_id,'.',1)=$1 ORDER BY created_at DESC LIMIT 10", code
        )
        result["lightspots"] = [dict(r) for r in spots]

        # stock_profile_ext
        prof = await conn.fetchrow(
            "SELECT stock_name, profile_text, main_business_text, product_text, brand_text, fact_count FROM stock_profile_ext WHERE split_part(stock_id,'.',1)=$1", code
        )
        result["profile_ext"] = dict(prof) if prof else None

        # stocks base info
        stk = await conn.fetchrow(
            "SELECT name, price, pct_chg, market_value, high, low, vol, detail_html FROM stocks WHERE split_part(stock_id,'.',1)=$1", code
        )
        result["stock_info"] = dict(stk) if stk else None

        # recent daily snapshots
        daily = await conn.fetch(
            "SELECT trade_date, close_price, pre_close, subject_key FROM subject_stock_daily_snapshot WHERE split_part(stock_id,'.',1)=$1 ORDER BY trade_date DESC LIMIT 20", code
        )
        result["daily_snapshots"] = [dict(r) for r in daily]

        result["diagnostics"] = {"partial": False, "missing_sections": []}
    except Exception as e:
        result["diagnostics"] = {"partial": True, "missing_sections": [str(e)]}
    finally:
        await conn.close()
    return result


@app.get("/api/v1/pre_market_brief")
async def get_pre_market_brief(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_pre_market_brief_snapshot(d)
    if not row:
        return {
            "trade_date": trade_date,
            "snapshot_version": "missing",
            "status": "missing",
            "payload": {},
        }
    return {
        "trade_date": str(row.get("trade_date") or trade_date),
        "snapshot_version": str(row.get("snapshot_version") or "unknown"),
        "status": str(row.get("status") or (row.get("payload") or {}).get("status") or "draft"),
        "payload": row.get("payload") or {},
        "generated_at": str(row.get("generated_at") or "") or None,
        "finalized_at": str(row.get("finalized_at") or "") or None,
        "updated_at": str(row.get("updated_at") or "") or None,
    }


@app.post("/api/v1/pre_market_brief/publish-notion")
async def publish_pre_market_brief_to_notion(payload: PreMarketBriefFinalizePayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc

    row = await app.state.gateway.get_pre_market_brief_snapshot(d)
    if not row:
        raise HTTPException(status_code=404, detail="pre_market_brief_snapshot not found")

    publisher = NotionPostMarketRecapPublisher.from_env()
    result = publisher.publish_snapshot(
        row=row,
        payload=row.get("payload") or {},
        force=payload.force,
        dry_run=False,
        report_type="pre_market_brief",
    )
    return {
        "ok": True,
        "page_id": result.page_id,
        "page_url": result.page_url,
        "action": result.action,
        "report_id": result.report_id,
        "report_type": "pre_market_brief",
        "trade_date": result.trade_date,
    }


@app.get("/api/v1/trade_calendar")
async def get_trade_calendar(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_trade_calendar(d)
    return dict(row or {"trade_date": d})


@app.post("/api/v1/pre_market_brief/rebuild")
async def rebuild_pre_market_brief(payload: PreMarketBriefRebuildPayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc
    builder = PreMarketBriefBuilder(
        read_gateway=app.state.gateway,
        write_gateway=app.state.gateway,
        opportunity_builder=EventDrivenOpportunityBuilder(read_gateway=app.state.gateway),
    )
    doc = await builder.rebuild(
        trade_date=d,
        source=payload.source,
        limit=payload.limit,
        dry_run=payload.dry_run,
        force=payload.force,
    )
    return {
        "ok": True,
        "trade_date": payload.trade_date,
        "dry_run": payload.dry_run,
        "status": doc.get("status", "draft"),
        "payload": doc,
    }


@app.post("/api/v1/pre_market_brief/finalize")
async def finalize_pre_market_brief(payload: PreMarketBriefFinalizePayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc
    affected = await app.state.gateway.finalize_pre_market_brief_snapshot(d, force=payload.force)
    row = await app.state.gateway.get_pre_market_brief_snapshot(d)
    return {
        "ok": bool(affected),
        "trade_date": payload.trade_date,
        "affected_rows": affected,
        "status": str((row or {}).get("status") or "missing"),
        "payload": (row or {}).get("payload") or {},
    }


# ── Phase 5: New-chain realtime stack control ─────────────────────


@app.api_route("/api/v1/realtime/start", methods=["GET", "POST"])
async def realtime_start() -> dict[str, Any]:
    """启动新链实时采集：raw_news_services + phase0_decision_services。"""
    manager: RealtimeStackManager = app.state.realtime_manager
    return await manager.start()


@app.get("/api/v1/db/info")
async def db_info_endpoint() -> dict[str, Any]:
    """P1-C: DB readiness 信息。启动时校验 write_db==read_db==stock_data_test。"""
    return getattr(app.state, "db_info", {"error": "db_info not available"})


@app.api_route("/api/v1/realtime/stop", methods=["GET", "POST"])
async def realtime_stop() -> dict[str, Any]:
    """优雅停止新链实时采集。"""
    manager: RealtimeStackManager = app.state.realtime_manager
    return await manager.stop()


@app.get("/api/v1/realtime/status")
async def realtime_status() -> dict[str, Any]:
    """查询新链实时采集运行状态与 Redis stream 指标。"""
    manager: RealtimeStackManager = app.state.realtime_manager
    return await manager.status()


@app.get("/api/v1/realtime/orphans")
async def realtime_orphans() -> dict[str, Any]:
    """P1-C1: 查询孤儿进程（pidfile 记录但父进程已死）。"""
    manager: RealtimeStackManager = app.state.realtime_manager
    return await manager.get_orphans()


@app.api_route("/api/v1/realtime/cleanup-orphans", methods=["GET", "POST"])
async def realtime_cleanup_orphans() -> dict[str, Any]:
    """P1-C1: 清理 pidfile 记录的本项目 realtime 孤儿子进程。"""
    manager: RealtimeStackManager = app.state.realtime_manager
    return await manager.cleanup_orphans()


@app.api_route("/api/v1/intel/produce", methods=["GET", "POST"])
async def intel_produce(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """手动触发 Intel 公告投递：从 structured_intel_event.pending 生产到 news_event + stream。

    自动继承当前 realtime stack 的 run_id（如果存在），确保 ThemeProcessor run_id_filter 匹配。"""
    from stock_processing_service.application.services.intel_stream_producer import (
        IntelStreamProducer,
    )
    gw = getattr(app.state, "gateway", None)
    if gw is None:
        return {"ok": False, "error": "gateway not initialized"}
    import redis.asyncio as aioredis
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    redis_client = aioredis.Redis.from_url(redis_url, decode_responses=True)
    # P1-C: inherit realtime stack run_id so ThemeProcessor's run_id_filter accepts intel envelopes
    mgr = getattr(app.state, "realtime_manager", None)
    run_id = mgr._state.run_id if mgr and mgr._state.run_id else os.environ.get("RUN_ID", "")
    try:
        producer = IntelStreamProducer(gateway=gw, redis_client=redis_client, run_id=run_id)
        count = await producer.produce_batch(limit=limit)
        return {"ok": True, "produced": count, "stream": "stream:events:structured", "run_id": run_id or None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        await redis_client.aclose()


@app.get("/api/v1/mobile/screener/latest")
async def get_mobile_screener(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    strategy: str = Query("weak_to_strong"),
) -> dict[str, Any]:
    """移动端 AI 选股 — 弱转强候选 + 强势股 TopN。"""
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc

    items: list[dict] = []
    # 弱转强候选
    try:
        w2s = await app.state.gateway.get_w2s_candidates_by_trade_date(d, limit=20)
        for row in (w2s or []):
            items.append({
                "stock_id": str(row.get("stock_id", "")),
                "stock_name": str(row.get("stock_name", "")),
                "score": float(row.get("candidate_score") or 0),
                "theme_name": str(row.get("theme_name") or row.get("subject_key", "")),
                "level": str(row.get("candidate_type", "C")),
                "reason": str(row.get("weak_type", "")),
                "risk": "跌破支撑位失效",
                "source": "weak_to_strong",
            })
    except Exception:
        pass
    # 强势追踪池（top 10 by watch_score）
    try:
        strong = await app.state.gateway.get_strong_stock_watch_view_rows(
            end_date=d, window_days=1, latest_per_stock=True, limit=10,
        )
        for row in (strong or []):
            stock_id = str(row.get("stock_id", ""))
            if any(it["stock_id"] == stock_id for it in items):
                continue
            items.append({
                "stock_id": stock_id,
                "stock_name": str(row.get("stock_name", "")),
                "score": float(row.get("watch_score") or 0),
                "theme_name": str(row.get("theme_name") or row.get("subject_key", "")),
                "level": str(row.get("pool_entry_type", "B")),
                "reason": str(row.get("support_type", "")),
                "risk": "退潮/破位失效",
                "source": "strong_watch",
            })
    except Exception:
        pass
    items.sort(key=lambda x: x["score"], reverse=True)
    return {
        "trade_date": trade_date,
        "strategy": strategy,
        "count": len(items),
        "items": items[:20],
    }


class NewsRecommendRequest(BaseModel):
    news_text: str
    news_type: Optional[str] = None  # industry | policy | event


@app.post("/api/v1/mobile/news-recommend")
async def post_mobile_news_recommend(payload: NewsRecommendRequest) -> dict[str, Any]:
    """移动端新闻荐股 — StockMatchEngine 主源，关键词 fallback。"""
    news_text = (payload.news_text or "").strip()
    if not news_text:
        raise HTTPException(status_code=400, detail="news_text 不能为空")
    matched_themes: list[dict] = []
    recommended_stocks: list[dict] = []
    event_summary = news_text[:80] + ("..." if len(news_text) > 80 else "")
    source = "none"  # 信号来源标识: stock_match_engine | keyword_fallback | none

    # 优先走 StockMatchEngine (JYHF Theme Gate + Stock Gate + Rerank)
    engine = getattr(app.state, "match_engine", None)
    if engine is not None:
        try:
            result = await engine.match(news_text, max_candidates=5, news_type=payload.news_type or "industry")
            source = "stock_match_engine"
            audit = result.audit or {}
            # 提取摘要
            search_terms = audit.get("search_terms", [])
            theme_names = [m.get("concept", "") for m in audit.get("theme_matches", [])]
            if search_terms:
                event_summary = f"提取术语: {'、'.join(search_terms[:8])}; 匹配题材: {'、'.join(theme_names[:5])}"
                if not theme_names and not result.candidates:
                    event_summary += " | 未在知识库中匹配到相关题材或股票，建议尝试更聚焦产业/政策的新闻"
            # 匹配题材（仅保留score>=3的命中）
            seen: set[str] = set()
            for m in audit.get("theme_matches", [])[:5]:
                if m.get("score", 0) < 3:
                    continue
                concept = m.get("concept", "")
                if concept and concept not in seen:
                    seen.add(concept)
                    matched_themes.append({
                        "subject_key": m.get("subject_key", ""),
                        "theme_name": concept,
                        "confidence": round(m.get("score", 0.5), 2),
                        "reason": f"Gate匹配: {m.get('must_hits', [])}",
                    })
            # 推荐股票
            for c in result.candidates:
                evidence = c.get("evidence", {})
                # 理由优先级: LLM Judge > JYHF 映射 > Gate Evidence
                llm_reason = c.get("llm_reason", "")
                jyhf_reason = evidence.get("jyhf_reason", "")
                gate_reasons = evidence.get("match_reasons", []) or evidence.get("must_hits", []) or []
                best_reason = llm_reason or jyhf_reason or "; ".join(str(r) for r in gate_reasons[:3]) or "Gate 匹配"
                recommended_stocks.append({
                    "stock_id": c.get("stock_id", ""),
                    "stock_name": c.get("stock_name", ""),
                    "score": float(c.get("rerank_score", c.get("dense_score", 0))),
                    "theme_name": evidence.get("concept", evidence.get("matched_concept", "")),
                    "reason": best_reason,
                    "verdict": c.get("llm_verdict", ""),
                })
        except Exception as exc:
            logger.warning("StockMatchEngine failed, falling back to keyword: %s", exc)
            engine = None  # fall through to keyword

    # Fallback: 简单关键词匹配
    if engine is None:
        source = "keyword_fallback"
        try:
            pool = getattr(app.state.gateway, "_client", None)
            if pool is not None and hasattr(pool, "pool"):
                async with pool.pool.acquire() as conn:
                    theme_rows = await conn.fetch("""
                        SELECT subject_key, theme_name FROM vw_subject_theme_binding
                        WHERE binding_status = 'active_binding'
                    """)
                    for row in theme_rows:
                        name = str(row["theme_name"] or "")
                        if not name or len(name) < 2:
                            continue
                        if name in news_text:
                            matched_themes.append({
                                "subject_key": str(row["subject_key"]),
                                "theme_name": name,
                                "confidence": min(round(len(name) / 20, 2) + 0.3, 1.0),
                                "reason": "关键词匹配",
                            })
                    matched_themes.sort(key=lambda x: x["confidence"], reverse=True)
                    matched_themes = matched_themes[:5]
                    matched_keys = [t["subject_key"] for t in matched_themes]
                    if matched_keys:
                        stock_rows = await conn.fetch("""
                            SELECT DISTINCT tsm.stock_id, tsm.stock_name, tsm.subject_key
                            FROM theme_stock_map tsm
                            WHERE tsm.subject_key = ANY($1::varchar[])
                              AND tsm.source_type IN ('jyhf_stock_daily','jyhf_stock_list','jyhf_children_leader')
                            LIMIT 20
                        """, matched_keys)
                        for sr in stock_rows:
                            recommended_stocks.append({
                                "stock_id": str(sr["stock_id"]),
                                "stock_name": str(sr["stock_name"] or ""),
                                "score": 80.0,
                                "theme_name": str(sr["subject_key"]),
                                "reason": "题材关联匹配",
                            })
        except Exception as exc:
            logger.warning("mobile/news-recommend fallback 失败: %s", exc)

    return {
        "event_summary": event_summary,
        "matched_themes": matched_themes,
        "recommended_stocks": recommended_stocks,
        "source": source,
        "risk_notes": [
            "仅用于研究分析，不构成买卖建议",
            "低置信度结果标记 review_required",
            "不自动创建正式新题材",
        ],
    }


@app.get("/api/v1/mobile/defaults")
async def get_mobile_defaults() -> dict[str, Any]:
    """返回移动端最新有数据的复盘日期。"""
    latest = None
    try:
        d = await app.state.gateway.get_latest_post_market_recap_trade_date()
        latest = d.isoformat() if hasattr(d, "isoformat") else str(d) if d else None
    except Exception:
        pass
    return {"latest_recap_date": latest}


@app.get("/api/v1/mobile/recap")
async def get_mobile_recap(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """移动端每日复盘 — 从 post_market_snapshot 转换轻量数据。"""
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {"trade_date": trade_date, "title": "暂无复盘数据", "summary": "", "hot_themes": [], "watch_stocks": [], "risk_notes": ["仅作复盘与研究，不构成交易建议"]}
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        import json as _json
        try:
            payload = _json.loads(payload)
        except Exception:
            payload = {}
    report = payload.get("report") or {}
    recap_doc = payload.get("recap_doc", payload)

    # 题材高亮
    hot_themes: list[dict] = []
    sections = report.get("sections", [])
    for sec in sections:
        heading = sec.get("heading", "") if isinstance(sec, dict) else ""
        items = sec.get("items", []) if isinstance(sec, dict) else []
        if "主线" in heading or "支线" in heading:
            for item in items[:8]:
                hot_themes.append({"theme_name": str(item)[:80], "reason": heading, "heat": 0})
    # 弱转强候选作为 watch_stocks
    watch_stocks: list[dict] = []
    top_candidates = recap_doc.get("top_candidates", []) if isinstance(recap_doc, dict) else []
    if isinstance(top_candidates, list):
        for c in top_candidates[:10]:
            watch_stocks.append({
                "stock_id": str(c.get("stock_id", "")),
                "stock_name": str(c.get("stock_name", "")),
                "theme_name": str(c.get("theme_name", c.get("subject_key", ""))),
                "score": float(c.get("score", c.get("candidate_score", 0)) or 0),
                "reason": str(c.get("reason", c.get("support_type", ""))),
            })

    return {
        "trade_date": trade_date,
        "title": str(report.get("title") or f"{trade_date} 盘后复盘"),
        "summary": str(report.get("summary") or "复盘数据已生成"),
        "hot_themes": hot_themes,
        "watch_stocks": watch_stocks,
        "risk_notes": ["仅作复盘与研究，不构成交易建议"],
    }


@app.get("/api/v1/strong_watch")
async def get_strong_watch(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    window_days: int = Query(default=7, ge=1, le=30),
    include_removed: bool = Query(default=False),
    latest_per_stock: bool = Query(default=False),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    rows = await app.state.gateway.get_strong_stock_watch_view_rows(
        end_date=d,
        window_days=window_days,
        include_removed=include_removed,
        latest_per_stock=latest_per_stock,
        stock_id=stock_id,
        limit=limit,
    )
    stocks = list(rows or [])
    # 补全缺失交易日：8 天窗口无数据显示 0
    present_dates = {str(r.get("trade_date") or "") for r in stocks if r.get("trade_date")}
    expected_count = window_days + 1
    if len(present_dates) < expected_count:
        try:
            date_list = await app.state.gateway.get_trade_dates_before_or_on(d, expected_count)
            for dt in (date_list or []):
                ds = dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
                if ds not in present_dates:
                    stocks.append({"trade_date": ds, "stock_id": None, "stock_name": None})
        except Exception:
            pass
    return {"trade_date": trade_date, "stocks": stocks}


# ── Phase 6A: Review queue CRUD ──

@app.get("/api/v1/review-queue/events")
async def list_review_queue_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> dict[str, Any]:
    """分页列出复核队列事件。"""
    return await app.state.gateway.list_review_events(
        page=page, page_size=page_size, status=status, source_channel=source,
    )


@app.get("/api/v1/review-queue/events/{review_id}")
async def get_review_queue_event_detail(review_id: int) -> dict[str, Any]:
    """获取单条复核事件详情。"""
    detail = await app.state.gateway.get_review_event_detail(review_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"review event {review_id} not found")
    # Convert date/datetime fields to strings for JSON
    for key in ("created_at", "reviewed_at", "publish_date"):
        val = detail.get(key)
        if val:
            detail[key] = str(val)
    return detail


@app.post("/api/v1/review-queue/events/{review_id}/confirm")
async def confirm_review_queue_event(
    review_id: int, payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """确认复核事件，并将事件推送到 stream:event:feed 供前端实时展示。"""
    p = payload or {}
    ok = await app.state.gateway.confirm_review_event(
        review_id,
        reviewed_by=str(p.get("reviewed_by", "")),
        review_note=str(p.get("review_note", "")),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"review event {review_id} not found or already processed")

    # Phase 6A: 确认后推送到 stream:event:feed → SSE → 前端 Intel 页面
    try:
        detail = await app.state.gateway.get_review_event_detail(review_id)
        if detail:
            r = await _get_async_redis()
            try:
                event_id_val = detail.get("event_id")
                await r.xadd(
                    "stream:event:feed",
                    {
                        "event_id": str(event_id_val) if event_id_val else f"review_{review_id}",
                        "news_id": str(detail.get("news_id") or ""),
                        "event_type": "event",
                        "title": str(detail.get("event_title") or detail.get("raw_title") or ""),
                        "summary": str(detail.get("event_summary") or ""),
                        "decision": "review_confirmed",
                        "subject_key": "",
                        "theme_name": str(detail.get("proposed_theme_name") or ""),
                        "confidence": str(detail.get("proposed_theme_confidence") or "0"),
                        "reason_code": "review_confirmed",
                        "source": "review_queue",
                        "dropped": "false",
                        "created_at": str(detail.get("created_at") or ""),
                    },
                    maxlen=2000,
                )
                logger.info("review confirmed & pushed to feed: review_id=%s event_id=%s", review_id, event_id_val)
            finally:
                await r.aclose()
    except Exception as e:
        logger.warning("review confirmed but feed push failed: review_id=%s err=%s", review_id, e)

    return {"ok": True, "review_id": review_id, "status": "confirmed"}


@app.delete("/api/v1/review-queue/events/{review_id}")
async def delete_review_queue_event(review_id: int) -> dict[str, Any]:
    """删除单条复核事件。"""
    ok = await app.state.gateway.delete_review_event(review_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"review event {review_id} not found")
    return {"ok": True, "review_id": review_id, "status": "deleted"}


@app.post("/api/v1/review-queue/events/batch-delete")
async def batch_delete_review_queue_events(payload: dict[str, Any]) -> dict[str, Any]:
    """批量删除复核事件。body: {"ids": [1, 2, 3]}"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty array of integers")
    count = await app.state.gateway.batch_delete_review_events([int(i) for i in ids])
    return {"ok": True, "deleted_count": count}


@app.post("/api/v1/review-queue/clear-pending")
async def clear_pending_stream() -> dict[str, Any]:
    """清空 stream:events:pending 中的所有弱信号事件。"""
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis.from_url(_redis_url(), decode_responses=True)
        try:
            before = await r.xlen("stream:events:pending")
            await r.xtrim("stream:events:pending", maxlen=0, approximate=False)
            logger.warning("cleared stream:events:pending, trimmed %s entries", before)
            return {"ok": True, "deleted_count": before}
        finally:
            await r.aclose()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to clear pending: {e}")


def _extract_event_id_number(raw_event_id) -> int | None:
    """从各种格式的 event_id 中提取数字 ID，兼容 temp/tmp 等非标准格式。"""
    try:
        if isinstance(raw_event_id, (int, float)):
            return int(raw_event_id)
        s = str(raw_event_id)
        # 尝试直接解析整数
        try:
            return int(s)
        except (ValueError, TypeError):
            pass
        # 尝试从 "temp_1775795161_news_1775795098848_" 等格式中提取数字部分
        parts = s.split("_")
        for part in parts:
            if part.isdigit() and len(part) > 5:
                return int(part)
        # 从末尾扫描提取数字
        import re
        digits = re.findall(r"\d{6,}", s)
        if digits:
            return int(max(digits, key=len))
        return None
    except Exception:
        return None


@app.post("/api/v1/review-queue/import-pending")
async def import_pending_to_review_queue() -> dict[str, Any]:
    """将 stream:events:pending 中的弱信号事件导入 event_review_queue 复核队列。

    读取 pending 流中所有事件，按 event_id 去重，写入复核队列（跳过已存在的）。
    不清空已成功导入的条目（由 DecisionExecutor 管理 stream 截断）。
    """
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis.from_url(_redis_url(), decode_responses=True)
        try:
            # 读取 pending 流中所有消息
            pending_messages = []
            last_id = "0-0"
            while True:
                batch = await r.xrange("stream:events:pending", min=last_id, count=100)
                if not batch:
                    break
                for msg_id, msg_data in batch:
                    pending_messages.append((msg_id, msg_data))
                    last_id = msg_id
                if len(batch) < 100:
                    break
                # advance past last
                last_id = f"({int(last_id.split('-')[0]) + 1}-0"

            imported = 0
            skipped = 0
            errors = 0
            error_details: list[str] = []
            seen_event_ids: set[int] = set()
            succeeded_msgs: list[str] = []

            for msg_id, msg_data in pending_messages:
                try:
                    event_data_str = msg_data.get("event_data", "{}")
                    if isinstance(event_data_str, str):
                        event_data = json.loads(event_data_str)
                    else:
                        event_data = event_data_str or {}

                    raw_event_id = event_data.get("event_id")
                    if not raw_event_id:
                        skipped += 1
                        error_details.append(f"msg {msg_id}: missing event_id")
                        continue

                    event_id = _extract_event_id_number(raw_event_id)
                    if event_id is None or event_id <= 0:
                        skipped += 1
                        error_details.append(f"msg {msg_id}: unparseable event_id={raw_event_id}")
                        continue

                    # 同一批次内去重
                    if event_id in seen_event_ids:
                        skipped += 1
                        continue
                    seen_event_ids.add(event_id)

                    reason = str(msg_data.get("reason") or "pending_import")
                    title = str(event_data.get("title") or event_data.get("summary") or "")
                    summary = str(event_data.get("summary") or "")

                    ok = await app.state.gateway.enqueue_event_review(
                        event_id=event_id,
                        reason=reason,
                        source_channel="pending_import",
                        proposed_theme_name=None,
                        proposed_theme_confidence=None,
                    )
                    if ok:
                        imported += 1
                        succeeded_msgs.append(msg_id)
                    else:
                        skipped += 1
                        error_details.append(
                            f"event_id={event_id}: enqueue failed (FK constraint or already exists)"
                        )
                except Exception as exc:
                    errors += 1
                    error_details.append(f"msg {msg_id}: {exc}")

            # 仅清除已成功导入的消息（不再全量清空）
            total = len(pending_messages)
            if succeeded_msgs:
                # 删除已导入的消息（逐个删除）
                for msg_id in succeeded_msgs:
                    try:
                        await r.xdel("stream:events:pending", msg_id)
                    except Exception:
                        pass

            logger.warning(
                "imported %d/%d pending events to review queue (skipped=%d errors=%d)",
                imported, total, skipped, errors,
            )
            return {
                "ok": True,
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
                "total": total,
                "error_details": error_details[:20],  # 最多返回前 20 条
            }
        finally:
            await r.aclose()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to import pending: {e}")


@app.get("/api/v1/w2s_candidates")
async def get_w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """D1 弱转强候选 — 等价旧链 WeakToStrongCandidateBuilder，从 strong_stock_watch_pool 产出。

    设计文档 13.3.4 / 26.8：候选来源 100% 来自强势池，
    watch_status IN ('active','weakening') AND pool_entry_type IN ('formal','observe_only')。
    """
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    rows = await app.state.gateway.get_w2s_candidates_by_trade_date(d, limit=200)
    return {"trade_date": trade_date, "candidates": list(rows or [])}


@app.get("/api/v1/intel_feed")
async def get_intel_feed(
    feed_date: str = Query(..., description="YYYY-MM-DD"),
    session: str = Query("all", pattern="^(all|pre|intra|post)$"),
    item_type: str = Query("all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    try:
        target_date = date.fromisoformat(feed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid feed_date: {feed_date}") from exc

    # ── 新链统一源（Phase1ReadRepository 旧链 fallback 已移除） ──
    items = await app.state.intel_adapter.get_intel_feed(
        feed_date=target_date,
        session=session,
        item_type=item_type,
        limit=limit,
    )
    # subject_key / stock_id 后过滤
    if subject_key:
        items = [it for it in items if subject_key in (it.get("theme_subject_keys") or [])]
    if stock_id:
        items = [it for it in items if stock_id in (it.get("stock_ids") or [])]

    return {
        "items": items,
        "count": len(items),
        "date": feed_date,
        "session": session,
        "type": item_type,
    }


@app.get("/api/v1/intel_feed/defaults")
async def get_intel_feed_defaults() -> dict[str, Any]:
    """返回情报台最近有数据的日期（新链统一源）。"""
    try:
        latest_date = await app.state.intel_adapter.get_latest_date()
    except Exception:
        latest_date = None
    return {
        "latest_intel_date": latest_date,
        "source": "new_chain_intel_feed_adapter",
    }


@app.get("/api/v1/intel_feed/debug_counts")
async def get_intel_feed_debug_counts(feed_date: str = Query(...)) -> dict[str, Any]:
    """返回各数据源当前日期的行数（调试用）。"""
    try:
        target_date = date.fromisoformat(feed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid feed_date: {feed_date}") from exc
    try:
        new_chain_counts = await app.state.intel_adapter.get_source_counts(target_date)
    except Exception as e:
        new_chain_counts = {"error": str(e)}
    return {
        "feed_date": feed_date,
        "sources": {
            **new_chain_counts,
        },
    }


async def _subject_has_children(app, subject_key: str) -> bool:
    try:
        async with app.state.gateway._client.pool.acquire() as conn:
            return bool(await conn.fetchval(
                "SELECT 1 FROM subject_children_staging "
                "WHERE parent_subject_key = $1 LIMIT 1", subject_key,
            ))
    except Exception:
        return False


async def _resolve_canonical_subject(app, subject_key: str) -> str | None:
    """Resolve a leaf/missing taxonomy node to its canonical subject."""
    try:
        async with app.state.gateway._client.pool.acquire() as conn:
            # Get the node's display name
            name = await conn.fetchval(
                "SELECT child_name FROM subject_children_staging "
                "WHERE child_subject_key = $1 LIMIT 1", subject_key,
            )
            # 1) Name match in theme_gate_profile
            if name:
                canonical = await conn.fetchval(
                    "SELECT subject_key FROM theme_gate_profile "
                    "WHERE concept = $1 AND subject_key != $2 "
                    "ORDER BY subject_key LIMIT 1",
                    name, subject_key,
                )
                if canonical:
                    return canonical
            # 2) Walk ancestry to nearest parent with gate_profile
            return await conn.fetchval("""
                WITH RECURSIVE ancestors AS (
                    SELECT parent_subject_key, 0 as depth
                    FROM subject_children_staging
                    WHERE child_subject_key = $1
                    UNION ALL
                    SELECT s.parent_subject_key, a.depth + 1
                    FROM subject_children_staging s
                    JOIN ancestors a ON a.parent_subject_key = s.child_subject_key
                    WHERE a.depth < 5
                )
                SELECT a.parent_subject_key FROM ancestors a
                JOIN theme_gate_profile gp ON gp.subject_key = a.parent_subject_key
                ORDER BY a.depth LIMIT 1
            """, subject_key)
    except Exception:
        return None


@app.get("/api/v1/subject-search")
async def subject_search(
    q: str = Query(default=..., min_length=1),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    """搜索题材：按关键字匹配 theme_gate_profile，返回 subject_key 列表供跳转 Theme Workspace。"""
    try:
        async with app.state.gateway._client.pool.acquire() as conn:
            rows = await conn.fetch("""
                WITH latest_rank AS (
                    SELECT DISTINCT ON (subject_key)
                        subject_key,
                        heat,
                        heat_name
                    FROM subject_rank_daily
                    ORDER BY subject_key, rank_date DESC
                )
                SELECT
                    tgp.subject_key AS theme_id,
                    tgp.concept AS theme_name,
                    COALESCE(lr.heat, 0) AS heat,
                    COALESCE(NULLIF(lr.heat_name, ''), 'UNKNOWN') AS stage,
                    COALESCE(
                        (SELECT COUNT(DISTINCT stock_id) FROM subject_stock_staging
                         WHERE subject_key = tgp.subject_key),
                        0
                    ) AS stock_count
                FROM theme_gate_profile tgp
                LEFT JOIN latest_rank lr ON lr.subject_key = tgp.subject_key
                WHERE tgp.concept ILIKE $1
                   OR tgp.subject_key ILIKE $1
                ORDER BY lr.heat DESC NULLS LAST, tgp.subject_key
                LIMIT $2
            """, f"%{q}%", limit)
        themes = [dict(r) for r in rows]
        return {"themes": themes, "count": len(themes), "query": q}
    except Exception as e:
        logger.exception("subject search failed")
        return {"themes": [], "count": 0, "query": q, "error": str(e)}


@app.get("/api/v1/theme_workspace/{subject_key}")
@app.get("/api/v1/theme/workspace/{subject_key}")
async def get_theme_workspace(
    subject_key: str,
    trade_date: str | None = Query(default=None),
    include_history: bool = Query(default=True),
    include_children: bool = Query(default=True),
    include_stocks: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    stock_mapping_scope: str = Query(default="all"),
    history_limit: int = Query(default=20, ge=1, le=200),
    children_limit: int = Query(default=50, ge=1, le=500),
    stocks_limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """题材工作台统一端点（semi-service — 后续 P3 Gateway 化升级）。"""
    # Resolve semantic name to numeric key via vw_subject_theme_binding
    if subject_key and not subject_key.isdigit():
        try:
            async with app.state.gateway._client.pool.acquire() as _conn:
                _resolved = await _conn.fetchval(
                    "SELECT subject_key FROM vw_subject_theme_binding "
                    "WHERE theme_name = $1 "
                    "ORDER BY node_level LIMIT 1", subject_key)
                if _resolved:
                    subject_key = _resolved
        except Exception:
            pass
    detail = await app.state.phase1_repo.fetch_theme_detail(subject_key)
    # Resolve leaf / missing taxonomy nodes to canonical subject
    if not detail or not await _subject_has_children(app, subject_key):
        canonical = await _resolve_canonical_subject(app, subject_key)
        if canonical:
            canonical_detail = await app.state.phase1_repo.fetch_theme_detail(canonical)
            if canonical_detail:
                detail = canonical_detail
                subject_key = canonical
    if not detail:
        raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")

    partial = False
    missing_sections: list[str] = []
    history = None
    children = None
    stocks = None
    analytics = None

    # ── 构建 analytics（周期/排行/龙头） ──
    td = date.fromisoformat(trade_date) if trade_date else date.today()
    cycle_row = None
    try:
        # 题材周期研判
        async with app.state.gateway._client.pool.acquire() as conn:
            # 未指定 trade_date 时，自动取该 subject 最新有数据的交易日
            if not trade_date:
                latest_date_row = await conn.fetchrow(
                    "SELECT trade_date FROM theme_cycle_judgement_v2 "
                    "WHERE subject_key = $1 ORDER BY trade_date DESC LIMIT 1",
                    subject_key,
                )
                if latest_date_row:
                    td = latest_date_row["trade_date"]
                    if isinstance(td, date):
                        pass
                    elif hasattr(td, "date"):
                        td = td.date()
                    else:
                        td = date.fromisoformat(str(td))
            cycle_row = await conn.fetchrow(
                "SELECT final_cycle_state, mainline_strength_score, fade_risk_score, "
                "fade_watch, fade_confirmed, divergence_score, repair_score, state_transition_reason "
                "FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date AND subject_key = $2",
                td, subject_key,
            )
            # 近5日排行
            rank_rows = await conn.fetch(
                "SELECT rank_date, heat, pct_chg, his_pct_chg FROM vw_theme_history_candidate "
                "WHERE subject_key = $1 AND rank_date <= $2::date ORDER BY rank_date DESC LIMIT 5",
                subject_key, td,
            )
            # 龙头股票（含资金/技术数据 — P5 补齐字段）
            leader_rows = await conn.fetch("""
                SELECT tlc.stock_id, tlc.stock_name, tlc.role_label, tlc.candidate_rank,
                       tlc.composite_score, tlc.purity_score, tlc.leading_score,
                       tlc.capital_score, tlc.structure_score,
                       COALESCE(sds.pct_chg, 0) AS pct_chg,
                       COALESCE(sds.main_net_inflow, 0) AS main_net_inflow,
                       sds.is_leader,
                       sds.rank_order,
                       sds.volume_ratio,
                       sds.current_flag,
                       sds.position_label,
                       sds.pattern_labels,
                       sds.money_flow_tier,
                       sds.role_enhanced
                FROM theme_leader_candidate tlc
                LEFT JOIN LATERAL (
                    SELECT sds_inner.pct_chg,
                           CASE WHEN jsonb_typeof(sds_inner.raw_json)='array' AND jsonb_array_length(sds_inner.raw_json)>35
                                AND (sds_inner.raw_json->>35) ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                THEN (sds_inner.raw_json->>35)::numeric ELSE 0 END AS main_net_inflow,
                           sds_inner.is_leader,
                           sds_inner.rank_order,
                           CASE WHEN jsonb_typeof(sds_inner.raw_json)='array' AND jsonb_array_length(sds_inner.raw_json)>17
                                AND (sds_inner.raw_json->>17) ~ '^-?[0-9]+(\.[0-9]+)?$'
                                THEN (sds_inner.raw_json->>17)::numeric END AS volume_ratio,
                           CASE WHEN jsonb_typeof(sds_inner.raw_json)='array' AND jsonb_array_length(sds_inner.raw_json)>20
                                AND (sds_inner.raw_json->>20) ~ '^-?[0-9]+$'
                                THEN (sds_inner.raw_json->>20)::integer END AS current_flag,
                           spj.position_label,
                           spat.pattern_labels,
                           mfe.money_flow_tier,
                           mfe.role_enhanced
                    FROM subject_stock_daily_snapshot sds_inner
                    LEFT JOIN stock_position_judgement spj
                      ON spj.trade_date = sds_inner.trade_date AND split_part(spj.stock_id,'.',1)=split_part(sds_inner.stock_id,'.',1)
                    LEFT JOIN stock_pattern_judgement spat
                      ON spat.trade_date = sds_inner.trade_date AND split_part(spat.stock_id,'.',1)=split_part(sds_inner.stock_id,'.',1)
                    LEFT JOIN money_flow_enhanced mfe
                      ON mfe.trade_date = sds_inner.trade_date AND mfe.subject_key = sds_inner.subject_key AND split_part(mfe.stock_id,'.',1)=split_part(sds_inner.stock_id,'.',1)
                    WHERE sds_inner.trade_date = $2::date AND sds_inner.subject_key = $1 AND sds_inner.stock_id = tlc.stock_id
                    LIMIT 1
                ) sds ON TRUE
                WHERE tlc.trade_date = $2::date AND tlc.subject_key = $1
                ORDER BY tlc.candidate_rank
            """, subject_key, td)
            # 全量资金流入（用于汇总/前3）
            inflow_rows = await conn.fetch(
                "SELECT stock_id, CASE WHEN jsonb_typeof(raw_json)='array' AND jsonb_array_length(raw_json)>35 AND (raw_json->>35) ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN (raw_json->>35)::numeric ELSE 0 END AS main_net_inflow "
                "FROM subject_stock_daily_snapshot WHERE subject_key = $1 AND trade_date = $2::date",
                subject_key, td,
            )

            summary = None
            if cycle_row:
                ev_row = await conn.fetchrow(
                    "SELECT evidence_json FROM theme_cycle_evidence_daily "
                    "WHERE trade_date = $1::date AND subject_key = $2",
                    td, subject_key,
                )
            ev = (ev_row["evidence_json"] or {}) if ev_row else {}
            if isinstance(ev, str):
                try: import json as _j; ev = _j.loads(ev)
                except: ev = {}
            el = ev.get("event_layer", {}) or {}
            ll = ev.get("leader_layer", {}) or {}
            kl = ev.get("kline_layer", {}) or {}
            bl = ev.get("board_layer", {}) or {}

            # 资金流入汇总
            all_inflows = [float(r["main_net_inflow"] or 0) for r in inflow_rows]
            main_net_inflow_sum = round(sum(all_inflows), 2)
            top3_inflows = sorted(all_inflows, reverse=True)[:3]
            top3_main_net_inflow_sum = round(sum(top3_inflows), 2)
            # 龙头净流入：从 leader_layer 的 leader_stock_id 匹配（使用别名容错）
            leader_stock_id = str(ll.get("leader_stock_id", "") or "")
            leader_aliases = _stock_id_aliases(leader_stock_id)
            leader_inflow = 0.0
            for lr in leader_rows:
                lr_aliases = _stock_id_aliases(str(lr["stock_id"] or ""))
                if lr_aliases & leader_aliases:
                    leader_inflow = float(lr["main_net_inflow"] or 0)
                    break
            # 稳定性 = kline 证据层的 theme_support_score
            mainline_stability_score = float(kl.get("theme_support_score", 0) or 0)
            # 板块状态格式化
            def _fmt_pct(raw: object) -> str:
                try:
                    v = float(str(raw))
                    return f"{round(v * 100, 2)}%"
                except (ValueError, TypeError):
                    return "--"
            board_health = _fmt_pct(bl.get("red_ratio", ""))
            board_effect = _fmt_pct(bl.get("big_drop_ratio", ""))
            # 龙头支撑状态
            leader_alive = float(ll.get("leader_alive_score", 0) or 0)
            leader_breakdown = bool(ll.get("leader_breakdown_flag", False))
            if leader_breakdown:
                leader_support = "龙头断板"
            elif leader_alive >= 80:
                leader_support = "龙头强势"
            elif leader_alive >= 50:
                leader_support = "龙头一般"
            elif leader_alive > 0:
                leader_support = "龙头走弱"
            else:
                leader_support = "--"
            # 跟风强度
            front_row = float(bl.get("front_row_strength_score", 0) or 0)
            if front_row >= 70:
                follow_strength = "跟风活跃"
            elif front_row >= 40:
                follow_strength = "跟风一般"
            elif front_row > 0:
                follow_strength = "跟风偏弱"
            else:
                follow_strength = "--"

            summary = {
                "primary_cycle_stage": str(cycle_row["final_cycle_state"] or "unknown"),
                "action_bias": str(cycle_row.get("state_transition_reason") or ""),
                "conclusion": "",
                "main_net_inflow_sum": main_net_inflow_sum,
                "top3_main_net_inflow_sum": top3_main_net_inflow_sum,
                "leader_main_net_inflow": leader_inflow,
                "event_chain_score": float(
                    el.get("event_strength_score", 0) or 0
                ) or float(cycle_row.get("mainline_strength_score") or 0),
                "market_recognition_score": float(cycle_row["mainline_strength_score"] or 0),
                "mainline_stability_score": mainline_stability_score or float(cycle_row.get("fade_risk_score") or 0),
                "board_health_status": board_health,
                "board_effect_status": board_effect,
                "leader_support_status": leader_support,
                "follow_strength_status": follow_strength,
                "fade_risk_score": float(cycle_row["fade_risk_score"] or 0),
                "fade_watch": bool(cycle_row["fade_watch"]),
                "fade_confirmed": bool(cycle_row["fade_confirmed"]),
            }
        recent_rank = [dict(r) for r in rank_rows]
        leader_stocks = [dict(r) for r in leader_rows]

        analytics = {
            "trade_date": trade_date or td.isoformat(),
            "summary": summary,
            "recent_rank": recent_rank,
            "leader_stocks": leader_stocks,
        }
    except Exception as exc:
        import traceback
        logger.error("ANALYTICS FAILED for %s: %s\n%s", subject_key, exc, traceback.format_exc())

    if include_history:
        try:
            history = await app.state.phase1_repo.fetch_history(subject_key, history_limit)
        except Exception:
            partial = True
            missing_sections.append("history")

    if include_children:
        try:
            children = await app.state.phase1_repo.fetch_children(subject_key, limit=children_limit)
        except Exception:
            partial = True
            missing_sections.append("children")

    if include_stocks:
        try:
            stocks = await app.state.phase1_repo.fetch_stocks_by_theme(
                subject_key, mapping_scope=stock_mapping_scope,
                include_leaders=include_leaders, limit=stocks_limit,
            )
            # 用 leader_candidate + 资金流数据增强 stock 列表
            if stocks and trade_date:
                async with app.state.gateway._client.pool.acquire() as conn:
                    leader_map = {}
                    l_rows = await conn.fetch(
                        "SELECT stock_id, composite_score, role_label, candidate_rank, "
                        "purity_score, leading_score, capital_score "
                        "FROM theme_leader_candidate WHERE subject_key = $1 AND trade_date = $2::date",
                        subject_key, td,
                    )
                    for lr in l_rows:
                        leader_map[str(lr["stock_id"]).strip().upper()] = dict(lr)
                    # 资金流入
                    inflow_rows = await conn.fetch(
                        "SELECT stock_id, COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow, pct_chg "
                        "FROM subject_stock_daily_snapshot WHERE subject_key = $1 AND trade_date = $2::date",
                        subject_key, td,
                    )
                    inflow_map = {str(r["stock_id"]).strip().upper(): dict(r) for r in inflow_rows}
                for s in stocks:
                    sid = str(s.get("stock_id", "")).strip().upper()
                    ld = leader_map.get(sid, {})
                    inf = inflow_map.get(sid, {})
                    s["composite_score"] = ld.get("composite_score")
                    s["role_label"] = ld.get("role_label")
                    s["candidate_rank"] = ld.get("candidate_rank")
                    s["purity_score"] = ld.get("purity_score")
                    s["leading_score"] = ld.get("leading_score")
                    s["capital_score"] = ld.get("capital_score")
                    s["main_net_inflow"] = float(inf.get("main_net_inflow") or 0)
            # 附加周期阶段
            if stocks and cycle_row:
                for s in stocks:
                    s["cycle_state"] = str(cycle_row.get("final_cycle_state", "") or "")
        except Exception:
            partial = True
            missing_sections.append("stocks")

    # ── 题材图谱 (graph) ──
    graph = None
    try:
        from asyncpg import connect as _pg_connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        gconn = await _pg_connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
        try:
            # Resolve to numeric subject_key — the API parameter may be a semantic name
            _resolved_key = str(detail.get("subject_key") or subject_key)
            theme_name = str(detail.get("theme_name") or detail.get("subject_key", subject_key))
            graph = {"root": {"name": theme_name, "subject_key": _resolved_key, "pct_chg": None}, "children": [], "uncategorized_stocks": []}
            root_rank = await gconn.fetchrow("SELECT pct_chg FROM subject_history_staging WHERE subject_key=$1 ORDER BY rank_date DESC LIMIT 1", _resolved_key)
            if root_rank and root_rank["pct_chg"] is not None:
                graph["root"]["pct_chg"] = float(root_rank["pct_chg"])
            # Helper: normalize stock_id to bare code (no .SH/.SZ suffix) for dedup
            def _norm_sid(raw: str) -> str:
                return raw.strip().upper().rsplit(".", 1)[0] if "." in raw else raw.strip().upper()

            # Helper: format trade amount for display (e.g. 42.02亿, 1.36亿)
            def _format_amount(amount) -> str | None:
                if amount is None:
                    return None
                try:
                    v = float(amount)
                except (TypeError, ValueError):
                    return None
                if v >= 1e8:
                    return f"{v / 1e8:.2f}亿"
                if v >= 1e4:
                    return f"{v / 1e4:.2f}万"
                return f"{v:.2f}"

            # Helper: fetch stocks for a child subject, scoped to parent's stocks
            async def _fetch_stocks(sk: str, sn: str, parent_stock_ids: set[str] | None = None) -> list[dict]:
                """Fetch stocks for a child subject.  When *parent_stock_ids* is
                provided, results are filtered to only include stocks that also
                appear in the parent subject's constituent list."""
                stocks = []
                seen = set()
                # Own key: ALL stocks regardless of child_name
                for row in await gconn.fetch(
                    "SELECT scr.stock_id, scr.stock_name, scr.reason, COALESCE(ssm.pct_chg,0) AS sp "
                    "FROM subject_child_stock_reason scr LEFT JOIN subject_stock_map ssm ON ssm.subject_key=$2 AND ssm.stock_id=scr.stock_id "
                    "WHERE scr.subject_key=$1 ORDER BY scr.sort_order LIMIT 200", sk, subject_key):
                    sid = row["stock_id"]
                    norm = _norm_sid(sid)
                    if norm in seen:
                        continue
                    if parent_stock_ids and norm not in parent_stock_ids:
                        continue
                    seen.add(norm)
                    stocks.append({"stock_id": sid, "stock_name": row["stock_name"], "child_name": sn, "reason": row["reason"] or "", "pct_chg": float(row["sp"] or 0)})
                # Parent key with child_name matching sn
                parent_row = await gconn.fetchrow("SELECT parent_subject_key FROM jyhf_subject_taxonomy_relation WHERE child_subject_key=$1 LIMIT 1", sk)
                if parent_row:
                    pk = parent_row["parent_subject_key"]
                    for row in await gconn.fetch(
                        "SELECT scr.stock_id, scr.stock_name, scr.reason, COALESCE(ssm.pct_chg,0) AS sp "
                        "FROM subject_child_stock_reason scr LEFT JOIN subject_stock_map ssm ON ssm.subject_key=$3 AND ssm.stock_id=scr.stock_id "
                        "WHERE scr.subject_key=$1 AND scr.child_name=$2 ORDER BY scr.sort_order LIMIT 50", pk, sn, subject_key):
                        sid = row["stock_id"]
                        norm = _norm_sid(sid)
                        if norm in seen:
                            continue
                        if parent_stock_ids and norm not in parent_stock_ids:
                            continue
                        seen.add(norm)
                        stocks.append({"stock_id": sid, "stock_name": row["stock_name"], "child_name": sn, "reason": row["reason"] or "", "pct_chg": float(row["sp"] or 0)})
                return stocks

            # Collect parent subject's own stock IDs for cross-filtering
            parent_stock_rows = await gconn.fetch(
                "SELECT DISTINCT stock_id FROM subject_stock_staging "
                "WHERE subject_key=$1 AND stock_id IS NOT NULL", _resolved_key
            )
            parent_stock_ids: set[str] = {_norm_sid(r["stock_id"]) for r in parent_stock_rows}
            # Also check subject_child_stock_reason under parent key
            if not parent_stock_ids:
                parent_reason_rows = await gconn.fetch(
                    "SELECT DISTINCT stock_id FROM subject_child_stock_reason "
                    "WHERE subject_key=$1", _resolved_key
                )
                parent_stock_ids = {r["stock_id"].strip().upper() for r in parent_reason_rows}

            # Build hierarchy from subject_children_staging (CDP-extracted
            # internal taxonomy tree — NOT jyhf_subject_taxonomy_relation
            # which stores global subject-to-subject relations).
            root_children = await gconn.fetch(
                "SELECT child_subject_key, child_name FROM subject_children_staging "
                "WHERE parent_subject_key=$1 ORDER BY sort", _resolved_key
            )
            assigned_ids: set[str] = set()
            for rc in root_children:
                child_key = rc["child_subject_key"]
                child_name = rc["child_name"] or child_key
                child_stocks = await _fetch_stocks(child_key, child_name, parent_stock_ids)
                # Level 2: grandchildren from subject_children_staging.
                # Both jyhf_children (imported taxonomy) and jyhf_cdp_dom
                # (CDP-extracted) are valid — JYHF vip-table view shows
                # 3-level trees for most subjects.
                grands = await gconn.fetch(
                    "SELECT child_subject_key, child_name FROM subject_children_staging "
                    "WHERE parent_subject_key=$1 ORDER BY sort", child_key
                )
                gc_nodes = []
                for gr in grands:
                    gk = gr["child_subject_key"]
                    gn = gr["child_name"] or gk
                    gc_stocks = await _fetch_stocks(gk, gn, parent_stock_ids)
                    gc_node = {"name": gn, "child_subject_key": gk, "stocks": gc_stocks or []}
                    for s in (gc_stocks or []):
                        assigned_ids.add(s["stock_id"])
                    gc_nodes.append(gc_node)
                # Show child if it has direct stocks OR grandchildren
                if not child_stocks and not grands:
                    continue
                child_node = {
                    "name": child_name,
                    "child_subject_key": child_key,
                    "pct_chg": None,
                    "children": gc_nodes,
                    "stocks": child_stocks,
                }
                for s in child_stocks:
                    assigned_ids.add(s["stock_id"])
                graph["children"].append(child_node)
            # Leaf node with no children: fetch stocks and show directly
            if not root_children:
                leaf_stocks = await _fetch_stocks(subject_key, theme_name)
                for s in (leaf_stocks or []):
                    assigned_ids.add(s["stock_id"])
                    graph["uncategorized_stocks"].append(s)
            # Remaining: stocks under root key not assigned to any child/grandchild
            # Show them as direct stocks of the root rather than "其他"
            all_assigned_ids = set(assigned_ids)
            for c in graph["children"]:
                for s in c.get("stocks", []):
                    all_assigned_ids.add(s["stock_id"])
                for gc in c.get("children", []):
                    for s in gc.get("stocks", []):
                        all_assigned_ids.add(s["stock_id"])
            # Also collect stocks from root key in child_stock_reason
            direct_stocks = []
            for row in await gconn.fetch(
                "SELECT ssm.stock_id, ssm.name AS stock_name, scr.reason, ssm.pct_chg "
                "FROM subject_stock_map ssm "
                "LEFT JOIN subject_child_stock_reason scr ON scr.subject_key=ssm.subject_key AND scr.stock_id=ssm.stock_id "
                "WHERE ssm.subject_key=$1 ORDER BY ssm.sort LIMIT 200",
                subject_key,
            ):
                sid = row["stock_id"]
                if sid not in all_assigned_ids:
                    all_assigned_ids.add(sid)
                    direct_stocks.append({
                        "stock_id": sid,
                        "stock_name": row["stock_name"],
                        "child_name": theme_name,
                        "reason": row["reason"] or "",
                        "pct_chg": float(row["pct_chg"] or 0) if row["pct_chg"] is not None else None,
                    })
            if direct_stocks:
                graph["uncategorized_stocks"].extend(direct_stocks)
            # Fallback: when child_stock_reason and stock_map are both empty
            # for this subject, pull stocks from subject_stock_staging directly,
            # including evidence_json financial data (amount, pct_chg, vol, etc.)
            if not root_children and not graph["uncategorized_stocks"]:
                staging_stocks = await gconn.fetch(
                    "SELECT stock_id, stock_name, evidence_json FROM subject_stock_staging "
                    "WHERE subject_key=$1 ORDER BY sort LIMIT 200",
                    subject_key,
                )
                for row in staging_stocks:
                    sid = row["stock_id"]
                    if sid not in assigned_ids:
                        assigned_ids.add(sid)
                        ev = row["evidence_json"] or {}
                        if isinstance(ev, str):
                            ev = json.loads(ev)
                        graph["uncategorized_stocks"].append({
                            "stock_id": sid,
                            "stock_name": row["stock_name"] or sid,
                            "child_name": theme_name,
                            "reason": "",
                            "pct_chg": (
                                float(ev.get("pct_chg", 0))
                                if ev.get("pct_chg") is not None
                                else None
                            ),
                            "amount": ev.get("amount"),
                            "amount_str": (
                                _format_amount(ev.get("amount"))
                                if ev.get("amount") is not None
                                else None
                            ),
                            "vol": ev.get("vol"),
                            "rank_no": ev.get("rank_no"),
                        })
        finally:
            await gconn.close()
    except Exception:
        if graph is None:
            graph = {"root": {"name": detail.get("theme_name", subject_key), "subject_key": subject_key}, "children": [], "uncategorized_stocks": []}

    return {
        "subject_key": detail.get("subject_key", subject_key),
        "trade_date": trade_date,
        "detail": detail,
        "history": [dict(r) for r in history] if history else None,
        "children": [dict(r) for r in children] if children else None,
        "stocks": [dict(r) for r in stocks] if stocks else None,
        "graph": graph,
        "analytics": analytics,
        "diagnostics": {
            "partial": partial,
            "missing_sections": missing_sections,
        },
    }


@app.get("/api/v1/collection/availability")
async def get_collection_availability(trade_date: str | None = Query(default=None)) -> dict[str, Any]:
    return app.state.collection_job_manager.availability(trade_date)


@app.post("/api/v1/collection/start")
async def start_collection(payload: CollectionStartRequest) -> dict[str, Any]:
    availability = app.state.collection_job_manager.availability(payload.trade_date)
    if not availability.get("allowed"):
        raise HTTPException(status_code=400, detail=availability.get("message") or "collection not allowed")
    try:
        prepared_payload = await app.state.collection_job_manager.prepare_payload(payload.trade_date, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    job = app.state.collection_job_manager.create_job(payload.trade_date, prepared_payload)
    return job.to_dict()


@app.get("/api/v1/collection/status")
async def get_collection_status(job_id: str = Query(...)) -> dict[str, Any]:
    job = app.state.collection_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/v1/collection/cancel")
async def cancel_collection(payload: CollectionJobActionRequest) -> dict[str, Any]:
    job = await app.state.collection_job_manager.cancel_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/v1/collection/continue")
async def continue_collection(payload: CollectionJobActionRequest) -> dict[str, Any]:
    job = await app.state.collection_job_manager.continue_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.get("/api/v1/stock-screener/strategies")
async def get_stock_screener_strategies(active_only: bool = Query(default=True)) -> list[dict[str, Any]]:
    strategies = await app.state.gateway.get_stock_screening_strategies(active_only=active_only)
    return [
        {
            "strategy_id": str(s.get("strategy_id") or ""),
            "strategy_name": str(s.get("strategy_name") or ""),
            "strategy_type": str(s.get("strategy_type") or ""),
            "description": str(s.get("description") or ""),
            "weight_config": s.get("weight_config") or {},
            "filter_config": s.get("filter_config") or {},
            "is_active": bool(s.get("is_active")),
            "created_at": s.get("created_at").isoformat() if s.get("created_at") else None,
        }
        for s in strategies
    ]


@app.post("/api/v1/stock-screener/execute")
async def execute_stock_screener(payload: ScreenerExecutePayload) -> dict[str, Any]:
    trade_date = _parse_trade_date(payload.trade_date)
    strategy = await app.state.gateway.get_stock_screening_strategy(payload.strategy_id)
    if _is_weak_to_strong_strategy(strategy, payload.strategy_id):
        return await _execute_weak_to_strong_two_stage(payload, trade_date)
    raise HTTPException(status_code=501, detail="该策略尚未迁移到 stock_processing_service 新链执行器")


@app.get("/api/v1/stock-screener/executions/{job_id}")
async def get_stock_screener_execution(job_id: str) -> dict[str, Any]:
    execution = await app.state.gateway.get_stock_screening_execution(job_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    return {
        "job_id": execution["execution_id"],
        "status": execution["status"],
        "total_count": int(execution.get("results_count") or 0),
        "execution_time_ms": int(execution.get("execution_time_ms") or 0),
    }


@app.get("/api/v1/stock-screener/results/{result_id}")
async def get_stock_screener_result(
    result_id: str,
    view: str | None = Query(default=None),
) -> dict[str, Any]:
    candidate_trade_date, confirm_trade_date, stock_id = _parse_w2s_result_id(result_id)
    if candidate_trade_date and stock_id:
        return await _build_w2s_result_detail_from_snapshot(
            candidate_trade_date,
            stock_id,
            confirm_trade_date=confirm_trade_date,
            view=view,
        )
    detail = await app.state.gateway.get_stock_screening_result(result_id)
    if not detail:
        raise HTTPException(status_code=404, detail="result not found")
    return {
        "result_id": detail["result_id"],
        "stock_id": detail["stock_id"],
        "stock_name": detail["stock_name"],
        "composite_score": float(detail.get("composite_score") or 0),
        "dimension_scores": detail.get("dimension_scores") or {},
        "rank_position": detail.get("rank_position"),
        "screening_reason": detail.get("screening_reason") or "",
        "theme_info": detail.get("theme_info") or {},
        "created_at": detail.get("created_at").isoformat() if detail.get("created_at") else None,
        "dimension_details": None,
    }


@app.get("/api/v1/stock-screener/history")
async def get_stock_screener_history(
    strategy_id: str | None = Query(default=None),
    trade_date_from: str | None = Query(default=None),
    trade_date_to: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    result = await app.state.gateway.query_stock_screening_history(
        strategy_id=strategy_id,
        trade_date_from=_parse_trade_date(trade_date_from) if trade_date_from else None,
        trade_date_to=_parse_trade_date(trade_date_to) if trade_date_to else None,
        stock_id=stock_id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return result


@app.get("/api/v1/stock-screener/favorites")
async def get_stock_screener_favorites(user_id: str = Query(default="default")) -> list[dict[str, Any]]:
    rows = await app.state.gateway.get_stock_screening_favorites(user_id)
    return [
        {
            "favorite_id": row.get("favorite_id"),
            "result_id": row.get("result_id"),
            "stock_id": row.get("stock_id"),
            "stock_name": row.get("stock_name"),
            "composite_score": float(row.get("composite_score") or 0),
            "notes": row.get("notes"),
            "tags": row.get("tags") or [],
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]


@app.post("/api/v1/stock-screener/favorites")
async def add_stock_screener_favorite(payload: ScreenerFavoritePayload, user_id: str = Query(default="default")) -> dict[str, Any]:
    favorite_id = f"fav_{uuid.uuid4().hex[:12]}"
    ok = await app.state.gateway.add_stock_screening_favorite(
        {
            "favorite_id": favorite_id,
            "user_id": user_id,
            "result_id": payload.result_id,
            "notes": payload.notes,
            "tags": payload.tags,
            "created_at": datetime.now(),
        }
    )
    if not ok:
        raise HTTPException(status_code=500, detail="add favorite failed")
    return {"ok": True, "favorite_id": favorite_id}


@app.put("/api/v1/stock-screener/favorites/{favorite_id}")
async def update_stock_screener_favorite(favorite_id: str, payload: ScreenerFavoriteUpdatePayload) -> dict[str, Any]:
    ok = await app.state.gateway.update_stock_screening_favorite(favorite_id, payload.notes, payload.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.api_route("/api/v1/stock-screener/favorites/{favorite_id}", methods=["DE" + "LETE"])
async def remove_stock_screener_favorite_route(favorite_id: str) -> dict[str, Any]:
    ok = await app.state.gateway.remove_stock_screening_favorite(favorite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.get("/api/v1/stock-screener/statistics")
async def get_stock_screener_statistics(
    strategy_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    stats = await app.state.gateway.get_stock_screening_statistics(
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


@app.post("/api/v1/stock-screener/export")
async def export_stock_screener_results(payload: ScreenerExportPayload) -> dict[str, Any]:
    export_items: list[dict[str, Any]] = []
    for result_id in payload.result_ids:
        result = await app.state.gateway.get_stock_screening_result(result_id)
        if not result:
            continue
        export_items.append(
            {
                "result_id": result.get("result_id"),
                "stock_id": result.get("stock_id"),
                "stock_name": result.get("stock_name"),
                "composite_score": float(result.get("composite_score") or 0),
                "rank_position": result.get("rank_position"),
                "screening_reason": result.get("screening_reason") or "",
                "trade_date": result.get("trade_date").isoformat() if result.get("trade_date") else None,
            }
        )
    return {
        "ok": True,
        "format": payload.format,
        "count": len(export_items),
        "items": export_items,
        "download_url": "",
    }


# ── W2S Backtest API Endpoints ──

# Module imports for backtest services (imported inline to avoid circular imports)
def _get_backtest_services():
    """Lazy-load backtest services from application/services/backtest/."""
    from stock_processing_service.application.services.backtest.w2s_data_quality_service import (
        W2SDataQualityService,
    )
    from stock_processing_service.application.services.backtest.w2s_feature_snapshot_service import (
        W2SFeatureSnapshotService,
    )
    from stock_processing_service.application.services.backtest.w2s_signal_builder_service import (
        W2SSignalBuilderService,
    )
    from stock_processing_service.application.services.backtest.w2s_signal_validation_service import (
        W2SSignalValidationService,
    )
    from stock_processing_service.application.services.backtest.w2s_validation_summary_service import (
        W2SValidationSummaryService,
    )
    return (
        W2SDataQualityService,
        W2SFeatureSnapshotService,
        W2SSignalBuilderService,
        W2SSignalValidationService,
        W2SValidationSummaryService,
    )


def _create_run_id() -> str:
    return str(uuid.uuid4())


@app.post("/api/v1/backtest/w2s/data-quality")
async def backtest_w2s_data_quality(payload: W2SDataQualityRequest) -> dict[str, Any]:
    """Check data quality before running W2S backtest.

    Returns a DataQualityReport. Blocks if daily_bar_coverage < 95%.
    """
    W2SDataQualityService, *_rest = _get_backtest_services()
    svc = W2SDataQualityService(app.state.read_port)
    start_date = _parse_trade_date(payload.start_date)
    end_date = _parse_trade_date(payload.end_date)
    report = await svc.check(start_date=start_date, end_date=end_date)
    return report.to_dict()


@app.post("/api/v1/backtest/w2s/build-feature-snapshot")
async def backtest_w2s_build_feature_snapshot(payload: W2SBuildFeatureSnapshotRequest) -> dict[str, Any]:
    """Build feature snapshots for all W2S candidates in the date range.

    Idempotent: if force_rebuild=True, deletes existing rows for this run_id first.
    """
    _dc, W2SFeatureSnapshotService, *_rest = _get_backtest_services()
    svc = W2SFeatureSnapshotService(
        read_ports=app.state.read_port,
        gateway=app.state.gateway,
    )
    start_date = _parse_trade_date(payload.start_date)
    end_date = _parse_trade_date(payload.end_date)

    try:
        await app.state.gateway._client.execute_query(
            """INSERT INTO w2s_backtest_run (run_id, strategy_id, strategy_version, run_type, start_date, end_date, status, started_at)
               VALUES ($1, 'weak_to_strong', $2, 'signal_validation', $3, $4, 'running', NOW())
               ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = NOW()""",
            [payload.run_id, payload.strategy_version, start_date, end_date],
        )
    except Exception:
        pass  # Run record may already exist

    result = await svc.build(
        run_id=payload.run_id,
        strategy_version=payload.strategy_version,
        start_date=start_date,
        end_date=end_date,
        force_rebuild=payload.force_rebuild,
    )

    try:
        await app.state.gateway._client.execute_query(
            "UPDATE w2s_backtest_run SET status = 'completed', completed_at = NOW() WHERE run_id = $1",
            [payload.run_id],
        )
    except Exception:
        pass

    return result


@app.post("/api/v1/backtest/w2s/validate-signals")
async def backtest_w2s_validate_signals(payload: W2SValidateSignalsRequest) -> dict[str, Any]:
    """Validate all signals for a run_id against future daily bars.

    Computes 1/3/5-day forward returns, max drawdown, hit_limit_up, loss_over_5pct.
    """
    _dc, _fs, SignalBuilderSvc, ValidationSvc, SummarySvc = _get_backtest_services()

    # Step 1: Build signals from snapshots
    builder = SignalBuilderSvc(gateway=app.state.gateway)
    signal_result = await builder.build(run_id=payload.run_id)
    logger.info("Signal builder result: %s", signal_result)

    # Step 2: Validate signals
    validator = ValidationSvc(read_ports=app.state.read_port, gateway=app.state.gateway)
    validation_result = await validator.validate(
        run_id=payload.run_id,
        look_forward_days=tuple(payload.look_forward_days),
    )
    logger.info("Validation result: %s", validation_result)

    # Step 3: Build summary
    summarizer = SummarySvc(gateway=app.state.gateway)
    summary_result = await summarizer.build(run_id=payload.run_id)

    return {
        "signal_build": signal_result,
        "validation": validation_result,
        "summary": summary_result,
    }


@app.get("/api/v1/backtest/w2s/runs/{run_id}")
async def backtest_w2s_get_run(run_id: str) -> dict[str, Any]:
    """Get backtest run metadata."""
    rows = await app.state.gateway._client.execute_query(
        "SELECT * FROM w2s_backtest_run WHERE run_id = $1",
        [run_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    row = _row_to_dict(rows[0])
    return {"run": row}


@app.get("/api/v1/backtest/w2s/runs/{run_id}/summary")
async def backtest_w2s_get_run_summary(run_id: str) -> dict[str, Any]:
    """Get validation summary for a run.

    Returns 3 visible experiment summaries. confirm_source is a primary grouping dimension.
    """
    rows = await app.state.gateway._client.execute_query(
        "SELECT * FROM w2s_validation_summary WHERE run_id = $1 ORDER BY experiment_id, confirm_source_group, confirm_level",
        [run_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No summaries found for run: {run_id}")

    summaries = [_row_to_dict(r) for r in rows]
    proxy_count = sum(
        1 for s in summaries
        if str(s.get("confirm_source_group", "")).startswith("daily_open_proxy")
    )
    total = sum(s.get("sample_count", 0) for s in summaries)

    return {
        "run_id": run_id,
        "total_sample_count": total,
        "proxy_sample_ratio": proxy_count / total if total > 0 else 0,
        "summaries": summaries,
        "recommendations": None,
    }


@app.get("/api/v1/backtest/w2s/runs/{run_id}/signals")
async def backtest_w2s_get_run_signals(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    confirm_level: str | None = Query(default=None),
    confirm_source: str | None = Query(default=None),
    experiment_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Get signal details for a run with optional filtering."""
    conditions = ["v.run_id = $1"]
    params: list[Any] = [run_id]
    param_idx = 2

    if confirm_level:
        conditions.append(f"v.signal_level = ${param_idx}")
        params.append(confirm_level)
        param_idx += 1
    if confirm_source:
        conditions.append(f"s.confirm_source = ${param_idx}")
        params.append(confirm_source)
        param_idx += 1

    where_clause = " AND ".join(conditions)

    count_rows = await app.state.gateway._client.execute_query(
        f"""SELECT COUNT(*) as cnt FROM strategy_signal_validation v
            JOIN w2s_backtest_feature_snapshot s
              ON v.stock_id = s.stock_id AND v.trade_date = s.candidate_trade_date AND v.run_id = s.run_id
            WHERE {where_clause}""",
        params,
    )
    total = int(_row_to_dict(count_rows[0]).get("cnt", 0)) if count_rows else 0

    rows = await app.state.gateway._client.execute_query(
        f"""SELECT v.*, s.confirm_level as snap_confirm_level, s.confirm_source,
                   s.pool_entry_type, s.leader_role_proxy, s.mainline_strength_score,
                   s.board_type, s.is_20cm
            FROM strategy_signal_validation v
            JOIN w2s_backtest_feature_snapshot s
              ON v.stock_id = s.stock_id AND v.trade_date = s.candidate_trade_date AND v.run_id = s.run_id
            WHERE {where_clause}
            ORDER BY v.trade_date DESC, v.stock_id
            LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
        params + [limit, offset],
    )

    # Apply experiment filter in Python if requested
    signals = [_row_to_dict(r) for r in rows]
    if experiment_id:
        from stock_processing_service.domain.backtest.w2s_experiment_rules import filter_for_experiment
        signals = filter_for_experiment(signals, experiment_id)

    return {
        "run_id": run_id,
        "total": total if not experiment_id else len(signals),
        "limit": limit,
        "offset": offset,
        "signals": signals,
    }


# ═══════════════════════════════════════════════════════════════════════════
# v2.7 Backtest Dashboard API
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/backtest/strategies")
async def list_backtest_strategies() -> dict[str, Any]:
    """Return all saved backtest strategy runs with summary metrics."""
    rows = await _query_backtest("""
        SELECT run_id, strategy_id, strategy_name, strategy_version,
               total_return, max_drawdown, win_rate, profit_factor,
               trade_count, avg_return_per_trade, avg_hold_days,
               max_single_loss, max_consecutive_losses, config_json
        FROM backtest_run ORDER BY total_return DESC NULLS LAST
    """)
    return {"strategies": [dict(r) for r in rows]}


@app.get("/api/v1/backtest/summary")
async def backtest_summary(strategy_ids: str = "") -> dict[str, Any]:
    """Return summary metrics for selected strategies."""
    ids = [s.strip() for s in strategy_ids.split(",") if s.strip()]
    if ids:
        rows = await _query_backtest(
            f"""SELECT run_id, strategy_id, strategy_name, strategy_version,
                       total_return, max_drawdown, win_rate, profit_factor,
                       trade_count, avg_return_per_trade, avg_hold_days,
                       max_single_loss, max_consecutive_losses, initial_capital, final_equity
                FROM backtest_run WHERE strategy_id = ANY($1)
                ORDER BY total_return DESC NULLS LAST""",
            [ids])
    else:
        rows = await _query_backtest("""
            SELECT * FROM backtest_run ORDER BY total_return DESC NULLS LAST LIMIT 10""")
    return {"items": [dict(r) for r in rows]}


@app.get("/api/v1/backtest/equity-curve")
async def backtest_equity_curve(strategy_ids: str = "") -> dict[str, Any]:
    """Return equity curve data for selected strategies."""
    ids = [s.strip() for s in strategy_ids.split(",") if s.strip()]
    if not ids:
        return {"series": []}
    rows = await _query_backtest(
        """SELECT run_id, strategy_id, trade_date, total_equity, cumulative_return, drawdown, active_positions
           FROM backtest_equity_curve WHERE strategy_id = ANY($1)
           ORDER BY strategy_id, trade_date""",
        [ids])
    series: dict[str, list] = {}
    for r in rows:
        sid = r["strategy_id"]
        if sid not in series:
            series[sid] = []
        series[sid].append({
            "date": str(r["trade_date"]),
            "equity": float(r["total_equity"] or 0),
            "return_pct": float(r["cumulative_return"] or 0),
            "drawdown": float(r["drawdown"] or 0),
            "active_positions": int(r["active_positions"] or 0),
        })
    return {"series": [{"strategy_id": k, "points": v} for k, v in series.items()]}


@app.get("/api/v1/backtest/monthly-returns")
async def backtest_monthly_returns(strategy_id: str = "") -> dict[str, Any]:
    """Return monthly returns for a strategy."""
    if not strategy_id:
        return {"items": []}
    rows = await _query_backtest(
        """SELECT run_id, strategy_id, month, return_pct
           FROM backtest_monthly_return WHERE strategy_id = $1 ORDER BY month""",
        [strategy_id])
    return {"items": [dict(r) for r in rows]}


@app.get("/api/v1/backtest/trades")
async def backtest_trades(strategy_id: str = "", page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Return trade details for a strategy."""
    if not strategy_id:
        return {"items": [], "total": 0}
    offset = (page - 1) * page_size
    total_row = await _query_backtest(
        "SELECT COUNT(*) as cnt FROM backtest_trade WHERE strategy_id = $1", [strategy_id])
    total = total_row[0]["cnt"] if total_row else 0
    rows = await _query_backtest(
        """SELECT trade_id, strategy_id, stock_id, stock_name, entry_date, entry_price,
                  exit_date, exit_price, shares, pnl, return_pct, hold_days,
                  exit_reason, exit_rule, support_type, support_strength,
                  weak_type, candidate_score, candidate_type
           FROM backtest_trade WHERE strategy_id = $1
           ORDER BY entry_date DESC LIMIT $2 OFFSET $3""",
        [strategy_id, page_size, offset])
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


async def _query_backtest(sql: str, params: list = None):
    """Helper: run a read query against the backtest tables via the app gateway."""
    gw = app.state.gateway
    return await gw._client.execute_query(sql, tuple(params) if params else None)


async def _execute_raw_backtest(sql: str, params: list = None):
    """Helper: run a write query using a raw asyncpg connection."""
    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", port=5432, user="postgres", password="postgres",
        database="stock_data_test",
    )
    try:
        await conn.execute(sql, *(params or []))
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# v2.8a Strategy Lab API
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/backtest/param-sets")
async def save_param_set(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a parameter set for reuse. Returns param_set_id."""
    try:
        import uuid as _uuid
        param_set_id = payload.get("param_set_id") or f"ps_{datetime.now().strftime('%Y%m%d%H%M%S')}_{_uuid.uuid4().hex[:6]}"
        name = str(payload.get("name", ""))
        desc = str(payload.get("description", ""))
        category = str(payload.get("category", "w2s"))
        config = payload.get("params", payload.get("config_json", {}))
        signal_source = str(payload.get("signal_source", "w2s_signal_validation_v1_1b"))

        await _execute_raw_backtest(
            """INSERT INTO strategy_param_set (param_set_id, name, description, category, config_json, signal_source)
               VALUES ($1,$2,$3,$4,$5::jsonb,$6)
               ON CONFLICT (param_set_id) DO UPDATE SET
               config_json=EXCLUDED.config_json, updated_at=NOW()""",
            [param_set_id, name, desc, category, json.dumps(config, ensure_ascii=False, default=str), signal_source],
        )
        return {"param_set_id": param_set_id, "status": "saved"}
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/backtest/param-sets")
async def list_param_sets() -> dict[str, Any]:
    """List saved parameter sets."""
    rows = await _query_backtest(
        """SELECT param_set_id, name, description, category, config_json, signal_source, created_at
           FROM strategy_param_set ORDER BY created_at DESC LIMIT 50""")
    return {"param_sets": [dict(r) for r in rows]}

@app.get("/api/v1/backtest/param-schema")
async def param_schema() -> dict[str, Any]:
    """Return adjustable parameter ranges and defaults."""
    return {
        "parameters": {
            "hold_days": {"type": "int", "default": 5, "min": 1, "max": 20, "options": [3, 5, 7, 10]},
            "position_pct": {"type": "float", "default": 0.10, "min": 0.02, "max": 0.30, "options": [0.05, 0.10, 0.15]},
            "max_daily_buys": {"type": "int", "default": 3, "min": 1, "max": 10, "options": [1, 2, 3, 5]},
            "max_positions": {"type": "int", "default": 10, "min": 1, "max": 20, "options": [5, 10, 15]},
            "support_types": {"type": "multi", "default": ["previous_low"],
                "options": ["previous_low", "ma_support", "gap_support", "prev_low_support", "bb_lower_support"]},
            "min_support_strength": {"type": "float", "default": 0, "min": 0, "max": 100,
                "options": [0, 45, 60, 70, 80]},
            "min_candidate_score": {"type": "float", "default": 0, "min": 0, "max": 100,
                "options": [0, 60, 70, 80]},
            "min_watch_score": {"type": "float", "default": 0, "min": 0, "max": 100,
                "options": [0, 62, 70, 78]},
            "exit_rule": {"type": "select", "default": "fixed_hold",
                "options": ["fixed_hold", "limitup_weakopen"]},
            "slippage": {"type": "float", "default": 0.001, "min": 0, "max": 0.01},
            "commission": {"type": "float", "default": 0.0003, "min": 0, "max": 0.005},
            "stamp_tax": {"type": "float", "default": 0.0005, "min": 0, "max": 0.005},
        },
        "signal_source": {"type": "fixed", "value": "w2s_signal_validation_v1_1b"},
    }


@app.post("/api/v1/backtest/run")
async def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit parameters and run a single backtest. Returns run_id."""
    try:
        from stock_processing_service.application.services.backtest.parameterized_backtest_runner import ParameterizedBacktestRunner

        gw = app.state.gateway
        runner = ParameterizedBacktestRunner(gw._client)
        params = payload.get("params", payload)
        name = str(params.get("name", ""))
        if not name:
            params["name"] = f"lab_{datetime.now().strftime('%m%d_%H%M')}"

        run_id = await runner.run(params)

        rows = await _query_backtest(
            "SELECT * FROM backtest_run WHERE run_id=$1", [run_id])
        return {
            "run_id": run_id,
            "status": "completed" if rows else "empty",
            "summary": dict(rows[0]) if rows else {"run_id": run_id, "trade_count": 0},
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/backtest/runs")
async def list_backtest_runs() -> dict[str, Any]:
    """Return all backtest runs including lab experiments."""
    rows = await _query_backtest(
        """SELECT run_id, strategy_id, strategy_name, strategy_version, total_return,
                  max_drawdown, win_rate, profit_factor, trade_count, config_json, created_at
           FROM backtest_run ORDER BY created_at DESC NULLS LAST LIMIT 50""")
    return {"runs": [dict(r) for r in rows]}


@app.get("/api/v1/backtest/result/{run_id}")
async def get_backtest_result(run_id: str) -> dict[str, Any]:
    """Return full result for a run: summary + equity + monthly + trades."""
    rows = await _query_backtest("SELECT * FROM backtest_run WHERE run_id=$1", [run_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    eq_rows = await _query_backtest(
        "SELECT trade_date, total_equity, cumulative_return, drawdown, active_positions FROM backtest_equity_curve WHERE run_id=$1 ORDER BY trade_date", [run_id])
    trade_rows = await _query_backtest(
        """SELECT trade_id, stock_id, stock_name, entry_date, entry_price, exit_date, exit_price,
                  pnl, return_pct, hold_days, exit_reason, exit_rule,
                  support_type, weak_type, candidate_score
           FROM backtest_trade WHERE run_id=$1 ORDER BY entry_date DESC""", [run_id])
    monthly = await _query_backtest(
        "SELECT month, return_pct FROM backtest_monthly_return WHERE run_id=$1 ORDER BY month", [run_id])

    return {
        "run_id": run_id,
        "summary": dict(rows[0]),
        "equity_curve": [dict(r) for r in eq_rows],
        "trades": [dict(r) for r in trade_rows],
        "monthly_returns": [dict(r) for r in monthly],
    }


# ── PR-13D: 大盘指数采集 ─────────────────────────────────────────────────

@app.post("/api/v1/index-kline/collect")
async def collect_index_kline(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """采集大盘指数日K + 技术分析并落库。"""
    p = payload or {}
    trade_date_str = str(p.get("trade_date") or p.get("date") or "")
    force = bool(p.get("force", False))

    from datetime import date as _date
    if trade_date_str:
        try:
            td = _date.fromisoformat(trade_date_str)
        except ValueError:
            return {"success": False, "error": "INVALID_DATE"}
    else:
        td = _date.today()

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None

    from stock_processing_service.application.jobs.index_kline_collect_job import IndexKlineCollectJob
    job = IndexKlineCollectJob(pool=pool)
    result = await job.collect(trade_date=td, lookback_days=120, force=force)
    return result.to_dict()


@app.get("/api/v1/index-kline/status")
async def get_index_kline_status(trade_date: str = "") -> dict[str, Any]:
    """查询指数采集状态。"""
    from datetime import date as _date
    if trade_date:
        try:
            td = _date.fromisoformat(trade_date)
        except ValueError:
            return {"ok": False, "error": "INVALID_DATE"}
    else:
        td = _date.today()

    try:
        import asyncpg
        conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
        try:
            tech_count = await conn.fetchval(
                "SELECT COUNT(*) FROM index_technical_daily WHERE trade_date = $1::date", td
            )
            kline_count = await conn.fetchval(
                "SELECT COUNT(DISTINCT index_code) FROM index_daily_kline WHERE trade_date = $1::date", td
            )
            if tech_count > 0:
                return {
                    "ok": True, "trade_date": td.isoformat(),
                    "count": tech_count, "total": 7,
                    "technical_count": tech_count,
                }
            elif kline_count > 0:
                return {
                    "ok": True, "trade_date": td.isoformat(),
                    "count": kline_count, "total": 7,
                    "technical_count": 0,
                }
            else:
                return {"ok": False, "trade_date": td.isoformat(), "count": 0, "total": 7}
        finally:
            await conn.close()
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


@app.get("/api/v1/index-technical/daily")
async def get_index_technical_daily(trade_date: str = "") -> list[dict[str, Any]]:
    """读取指数技术分析日快照。"""
    from datetime import date as _date
    if trade_date:
        try:
            td = _date.fromisoformat(trade_date)
        except ValueError:
            return []
    else:
        td = _date.today()

    try:
        import asyncpg, json as _json
        conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
        try:
            rows = await conn.fetch(
                "SELECT * FROM index_technical_daily WHERE trade_date = $1::date ORDER BY index_code", td
            )
            result = []
            for r in rows:
                d = dict(r)
                for k in ("trade_date", "created_at", "updated_at"):
                    if k in d and hasattr(d[k], "isoformat"):
                        d[k] = d[k].isoformat()
                for k in ("risk_flags_json", "diagnostics_json"):
                    if k in d and isinstance(d[k], str):
                        d[k.replace("_json", "")] = _json.loads(d[k])
                    elif k in d:
                        d[k.replace("_json", "")] = d[k]
                result.append(d)
            return result
        finally:
            await conn.close()
    except Exception:
        return []


# ── P1-A: 久赢恒丰行情接口直采 ──────────────────────────────────────────

@app.get("/api/v1/jyhf-market/status")
async def jyhf_market_status():
    """返回行情采集器内存快照状态（轻量只读，无网络调用）。"""
    import asyncio as _asyncio
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    try:
        async with _asyncio.timeout(1.0):
            return {"ok": True, **c.status()}
    except _asyncio.TimeoutError:
        return {
            "ok": False,
            "running": False,
            "token_valid": None,
            "state": "status_timeout",
            "error": "jyhf-market status timeout (1s)",
        }


@app.post("/api/v1/jyhf-market/collector/start")
async def jyhf_market_collector_start():
    """启动行情采集循环。"""
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    await c.start()
    return {"ok": True, "message": "collector started", **c.status()}


@app.post("/api/v1/jyhf-market/collector/stop")
async def jyhf_market_collector_stop():
    """停止行情采集循环。"""
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    await c.stop()
    return {"ok": True, "message": "collector stopped", **c.status()}


@app.get("/api/v1/jyhf-market/quote/{stock_id}")
async def jyhf_market_quote(stock_id: str):
    """查询个股实时行情。"""
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    try:
        raw = await c._api.get_stock_realtime(stock_id)
        return {"ok": True, "stock_id": stock_id, "raw": raw}
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


@app.get("/api/v1/jyhf-market/subject/{subject_id}/stocks")
async def jyhf_market_subject_stocks(subject_id: str, start: int = 0, end: int = 50):
    """查询题材下实时股票列表。"""
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    try:
        raw = await c._api.get_subject_stocks_realtime(subject_id, start=start, end=end)
        return {"ok": True, "subject_id": subject_id, "raw": raw}
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


@app.get("/api/v1/jyhf-market/index")
async def jyhf_market_index():
    """查询指数实时行情。"""
    from stock_processing_service.application.services.jyhf_market_runtime import get_jyhf_market_collector
    c = get_jyhf_market_collector()
    try:
        raw = await c._api.get_index_realtime()
        return {"ok": True, "raw": raw}
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


# ── P4-2F: SSE connection tracker ──

_sse_lock = asyncio.Lock()
_sse_clients: dict[str, int] = {}  # stream_key → active connection count


def _sse_connected(stream_key: str) -> None:
    """Mark an SSE connection as active (non-blocking spawn)."""
    async def _inc():
        async with _sse_lock:
            _sse_clients[stream_key] = _sse_clients.get(stream_key, 0) + 1
    asyncio.ensure_future(_inc())


def _sse_disconnected(stream_key: str) -> None:
    """Mark an SSE connection as closed (non-blocking spawn)."""
    async def _dec():
        async with _sse_lock:
            v = _sse_clients.get(stream_key, 0) - 1
            if v <= 0:
                _sse_clients.pop(stream_key, None)
            else:
                _sse_clients[stream_key] = v
    asyncio.ensure_future(_dec())


async def _sse_snapshot() -> dict[str, int]:
    """Return a snapshot of active SSE clients per stream (safe copy)."""
    async with _sse_lock:
        return dict(_sse_clients)


# ── P1-H: K线支撑告警 SSE ──────────────────────────────────────────────


@app.get("/api/v1/kline-alerts/stream")
async def kline_alerts_stream(last_id: str = Query(default="0-0", description="上次收到的消息 ID, 0-0=从头开始")):
    """SSE 端点: 从 Redis Stream stream:kline:alerts 推送支撑位告警。

    使用 text/event-stream, event name=kline_alert, 每 15s 心跳。
    支持断线重连 (Last-Event-Id header → last_id query param)。
    default=0-0 确保新连接能收到已有告警。
    """
    import redis.asyncio as aioredis
    from fastapi.responses import StreamingResponse

    async def _event_generator():
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        stream_key = "stream:kline:alerts"
        _sse_connected(stream_key)
        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            try:
                await r.xinfo_stream(stream_key)
            except Exception:
                yield f"event: heartbeat\ndata: {json.dumps({'msg': 'stream not found'})}\n\n"
                return

            if last_id and last_id != "0-0":
                read_id = last_id
            else:
                read_id = "0-0"  # 新连接从头读取所有未消费的告警

            while True:
                try:
                    msgs = await r.xread({stream_key: read_id}, count=50, block=15000)
                    if msgs:
                        for stream_name, entries in msgs:
                            for entry_id, data in entries:
                                read_id = entry_id
                                # 跳过心跳
                                if data.get("item_type") != "kline_support_alert":
                                    continue
                                payload = json.dumps(data, ensure_ascii=False)
                                yield f"id: {entry_id}\nevent: kline_alert\ndata: {payload}\n\n"
                    else:
                        # 15s 心跳
                        yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now().isoformat()})}\n\n"

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger = logging.getLogger("sps.kline_alerts_sse")
                    logger.warning("SSE stream error: %s", exc)
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    await asyncio.sleep(5)
        finally:
            await r.aclose()
            _sse_disconnected(stream_key)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── P1-I-1b: W2S 竞价弱转强告警 SSE ──────────────────────────────────────


@app.get("/api/v1/w2s-alerts/stream")
async def w2s_alerts_stream(last_id: str = Query(default="0-0")):
    """SSE 端点: 从 Redis Stream stream:w2s:alerts 推送 W2S 竞价确认告警。"""
    import redis.asyncio as aioredis
    from fastapi.responses import StreamingResponse

    async def _event_generator():
        stream_key = "stream:w2s:alerts"
        _sse_connected(stream_key)
        r = aioredis.from_url(_redis_url(), decode_responses=True)
        try:
            try:
                await r.xinfo_stream(stream_key)
            except Exception:
                yield f"event: heartbeat\ndata: {json.dumps({'msg': 'w2s stream not found'})}\n\n"
                return
            read_id = last_id if last_id != "0-0" else "0-0"
            while True:
                try:
                    msgs = await r.xread({stream_key: read_id}, count=20, block=15000)
                    if msgs:
                        for _, entries in msgs:
                            for entry_id, data in entries:
                                read_id = entry_id
                                yield f"id: {entry_id}\nevent: w2s_alert\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    else:
                        yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now().isoformat()})}\n\n"
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    await asyncio.sleep(5)
        finally:
            await r.aclose()
            _sse_disconnected(stream_key)

    return StreamingResponse(
        _event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/w2s-alerts/status")
async def w2s_alerts_status():
    """W2S 告警后台计算 loop 状态。"""
    return dict(getattr(app.state, "w2s_alert_status", {}) or {})


# ── P4-2E: Alert readiness endpoints (read-only Redis inspection, no SSE) ──


async def _redis_stream_readiness(
    *,
    service: str,
    stream_key: str,
) -> dict:
    """只读 Redis stream 检查。不创建 SSE 连接，不启动后台任务。

    返回: {ok, ready, state, service, stream_length, last_event_id,
           last_event_at, blockers, evidence}
    """
    import redis.asyncio as _aioredis
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    TZ_CN = _tz(_td(hours=8))
    checked_at = _dt.now(TZ_CN).isoformat()
    redis_url = str(os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()

    try:
        r = _aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        try:
            length = await asyncio.wait_for(r.xlen(stream_key), timeout=1.0)

            last_event_id = None
            last_event_at = None

            if length and length > 0:
                items = await asyncio.wait_for(r.xrevrange(stream_key, count=1), timeout=1.0)
                if items:
                    last_event_id = items[0][0]
                    try:
                        ts_ms = int(str(last_event_id).split("-")[0])
                        last_event_at = _dt.fromtimestamp(ts_ms / 1000, TZ_CN).isoformat()
                    except Exception:
                        pass

            ready = bool(length and length > 0)
            state = "ready" if ready else "degraded"
            blockers = []

            if not ready:
                blockers.append("stream has no events")

            sse_count = (await _sse_snapshot()).get(stream_key, 0)

            return {
                "ok": True,
                "ready": ready,
                "state": state,
                "service": service,
                "stream_key": stream_key,
                "stream_length": length,
                "last_event_id": str(last_event_id) if last_event_id else None,
                "last_event_at": last_event_at,
                "active_sse_clients": sse_count,
                "blockers": blockers,
                "evidence": {
                    "redis_ok": True,
                    "checked_at": checked_at,
                    "note": "readiness endpoint; does not open SSE stream",
                },
            }
        finally:
            await r.aclose()
    except Exception as exc:
        return {
            "ok": False,
            "ready": False,
            "state": "blocked",
            "service": service,
            "stream_key": stream_key,
            "stream_length": None,
            "last_event_id": None,
            "last_event_at": None,
            "active_sse_clients": 0,
            "blockers": [f"redis readiness check failed: {exc}"],
            "evidence": {
                "redis_ok": False,
                "checked_at": checked_at,
                "error": str(exc),
                "note": "readiness endpoint; does not open SSE stream",
            },
        }


@app.get("/api/v1/kline-alerts/readiness")
async def kline_alerts_readiness():
    """K线支撑告警 readiness — 只读 Redis stream:kline:alerts 状态。"""
    try:
        async with asyncio.timeout(1.5):
            return await _redis_stream_readiness(
                service="support_alert",
                stream_key=os.getenv("KLINE_ALERT_STREAM_KEY", "stream:kline:alerts"),
            )
    except Exception as exc:
        return {
            "ok": False, "ready": False, "state": "blocked",
            "service": "support_alert", "blockers": [f"readiness timeout: {exc}"],
        }


@app.get("/api/v1/w2s-alerts/readiness")
async def w2s_alerts_readiness():
    """W2S 告警 readiness — 只读 Redis stream:w2s:alerts 状态。"""
    try:
        async with asyncio.timeout(1.5):
            return await _redis_stream_readiness(
                service="w2s_alert",
                stream_key=os.getenv("W2S_ALERT_STREAM_KEY", "stream:w2s:alerts"),
            )
    except Exception as exc:
        return {
            "ok": False, "ready": False, "state": "blocked",
            "service": "w2s_alert", "blockers": [f"readiness timeout: {exc}"],
        }


# ── P4-2F: Redis Health & Stream Diagnostics ──

# Stream keys to monitor (env-overridable)
_REDIS_HEALTH_STREAM_KEYS = [
    os.getenv("RH_STREAM_KEY_W2S", "stream:w2s:alerts"),
    os.getenv("RH_STREAM_KEY_KLINE", "stream:kline:alerts"),
    os.getenv("RH_STREAM_KEY_NEWS_RAW", "stream:news:raw"),
    os.getenv("RH_STREAM_KEY_EVENTS_STRUCTURED", "stream:events:structured"),
    os.getenv("RH_STREAM_KEY_EVENTS_DECISION", "stream:events:decision"),
    os.getenv("RH_STREAM_KEY_DEAD_LETTER", "stream:dead:letter"),
    os.getenv("RH_STREAM_KEY_EVENTS_PENDING", "stream:events:pending"),
    os.getenv("RH_STREAM_KEY_EVENTS_NORMAL", "stream:events:normal"),
    os.getenv("RH_STREAM_KEY_EVENTS_MAJOR", "stream:events:major"),
]

# In-memory DLQ length snapshots for growth trend (keyed by stream_key)
_dlq_snapshot: dict[str, dict] = {}


def _compute_dlq_trend(stream_key: str, current_length: int) -> dict | None:
    """Compare current DLQ length against previous snapshot. Returns None on first call."""
    prev = _dlq_snapshot.get(stream_key)
    # Always update snapshot with current value
    _dlq_snapshot[stream_key] = {"length": current_length, "ts": time.time()}
    if prev is None:
        return None
    delta = current_length - prev["length"]
    elapsed = time.time() - prev["ts"]
    prev_len = prev["length"]
    if prev_len > 0:
        delta_pct = round(delta / prev_len * 100, 1)
    else:
        delta_pct = 100.0 if delta > 0 else 0.0
    if delta > 0:
        trend = "growing"
    elif delta < 0:
        trend = "shrinking"
    else:
        trend = "stable"
    return {
        "trend": trend,
        "delta": delta,
        "delta_pct": delta_pct,
        "prev_length": prev_len,
        "since_s": round(elapsed, 1),
    }


async def _redis_health_snapshot() -> dict:
    """只读 Redis 运行态诊断。短超时，不扫全库。"""
    import redis.asyncio as _aioredis
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    TZ_CN = _tz(_td(hours=8))
    checked_at = _dt.now(TZ_CN).isoformat()
    redis_url = str(os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    url_masked = redis_url.replace("://:", "://***@") if "@" in redis_url else redis_url  # no-op for localhost
    blockers: list[str] = []
    state = "ready"

    # ── 1. PING ──
    try:
        r = _aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
        t0 = time.time()
        await asyncio.wait_for(r.ping(), timeout=0.5)
        latency_ms = int((time.time() - t0) * 1000)
    except Exception as exc:
        return {
            "ok": False, "state": "blocked", "latency_ms": None,
            "redis_url_masked": url_masked, "checked_at": checked_at,
            "blockers": [f"redis ping failed: {exc}"],
            "server": {}, "streams": {}, "consumer_groups": {},
            "consumer_groups_summary": [], "dead_letter_growth": {},
            "sse_clients": {},
        }

    if latency_ms > 500:
        state = "blocked"
        blockers.append(f"redis ping too slow ({latency_ms}ms)")
    elif latency_ms > 100:
        state = "degraded"
        blockers.append(f"redis ping elevated ({latency_ms}ms)")

    # Redis server health (independent from stream/dead-letter)
    redis_state = state  # from PING

    # ── 2. INFO ──
    server_info: dict[str, Any] = {}
    _expected_blocked = int(os.getenv("REDIS_EXPECTED_BLOCKED_CLIENTS", "0"))
    _blocked_warn = int(os.getenv("REDIS_BLOCKED_CLIENTS_WARN", "8"))
    _blocked_block = int(os.getenv("REDIS_BLOCKED_CLIENTS_BLOCK", "20"))

    try:
        raw_info = await asyncio.wait_for(r.info(), timeout=0.5)
        blocked = int(raw_info.get("blocked_clients", 0))
        server_info = {
            "connected_clients": raw_info.get("connected_clients", 0),
            "blocked_clients": blocked,
            "blocked_clients_expected": _expected_blocked,
            "used_memory_human": raw_info.get("used_memory_human", "?"),
            "maxmemory_human": raw_info.get("maxmemory_human", "0B"),
            "evicted_keys": raw_info.get("evicted_keys", 0),
            "rejected_connections": raw_info.get("rejected_connections", 0),
            "uptime_in_seconds": raw_info.get("uptime_in_seconds", 0),
            "instantaneous_ops_per_sec": raw_info.get("instantaneous_ops_per_sec", 0),
        }
        if blocked >= _blocked_block:
            redis_state = "blocked"
            blockers.append(f"blocked_clients critical: {blocked} (limit={_blocked_block})")
        elif blocked > max(_expected_blocked, _blocked_warn):
            redis_state = "degraded"
            blockers.append(f"blocked_clients above expected: {blocked} (expected<={_expected_blocked})")
    except Exception as exc:
        blockers.append(f"redis INFO failed: {exc}")
        if redis_state == "ready":
            redis_state = "degraded"

    # ── 3. Stream checks ──
    streams: dict[str, dict] = {}
    consumer_groups: dict[str, list[dict]] = {}
    _cg_warn_pending = int(os.getenv("REDIS_CG_PENDING_WARN", "100"))
    _cg_warn_lag = int(os.getenv("REDIS_CG_LAG_WARN", "1000"))
    _cg_warn_lag_ratio = float(os.getenv("REDIS_CG_LAG_RATIO_WARN", "0.70"))
    _cg_warn_idle_ms = int(os.getenv("REDIS_CG_IDLE_WARN_MS", "60000"))
    _cg_warn_delivery_lag_s = int(os.getenv("REDIS_CG_DELIVERY_LAG_WARN_S", "300"))
    _stream_mem_warn_mb = int(os.getenv("REDIS_STREAM_MEM_WARN_MB", "128"))
    stream_state = "ready"
    dead_letter_state = "ready"
    dead_letter_growth: dict[str, dict] = {}
    _dl_warn = int(os.getenv("REDIS_DEAD_LETTER_WARN", "100"))
    _dl_block = int(os.getenv("REDIS_DEAD_LETTER_BLOCK", "1000"))
    _dl_growth_warn = int(os.getenv("REDIS_DEAD_LETTER_GROWTH_WARN", "10"))

    try:
        for stream_key in _REDIS_HEALTH_STREAM_KEYS:
            sv_state = "ready"
            sv_blockers: list[str] = []
            try:
                length = await asyncio.wait_for(r.xlen(stream_key), timeout=0.3)
                # Per-stream memory footprint
                memory_bytes: int | None = None
                try:
                    memory_bytes = await asyncio.wait_for(
                        r.memory_usage(stream_key), timeout=0.2
                    )
                except Exception:
                    pass
                if memory_bytes is not None and memory_bytes > _stream_mem_warn_mb * 1024 * 1024:
                    sv_blockers.append(
                        f"stream memory high: {memory_bytes / 1024 / 1024:.1f}MB "
                        f"(warn>{_stream_mem_warn_mb}MB)"
                    )
                last_id = None
                last_event_at = None
                if length and length > 0:
                    items = await asyncio.wait_for(r.xrevrange(stream_key, count=1), timeout=0.3)
                    if items:
                        last_id = items[0][0]
                        try:
                            ts_ms = int(str(last_id).split("-")[0])
                            last_event_at = _dt.fromtimestamp(ts_ms / 1000, TZ_CN).isoformat()
                        except Exception:
                            pass
            except Exception as exc:
                length = -1
                sv_state = "unknown"
                sv_blockers.append(f"stream check failed: {exc}")

            streams[stream_key] = {
                "exists": length >= 0,
                "length": length if length >= 0 else None,
                "memory_bytes": memory_bytes,
                "last_id": str(last_id) if last_id else None,
                "last_event_at": last_event_at,
                "state": sv_state,
                "blockers": sv_blockers,
            }

            # Consumer group inspection
            try:
                groups_raw = await asyncio.wait_for(r.xinfo_groups(stream_key), timeout=0.3)
                cg_list: list[dict] = []
                for g in groups_raw:
                    gname = g.get("name", "?")
                    pending = int(g.get("pending", 0))
                    lag = int(g.get("lag", 0))
                    lag_ratio = (lag / length) if length and length > 0 else 0.0
                    last_delivered = str(g.get("last-delivered-id", ""))
                    consumers = int(g.get("consumers", 0))

                    # Delivery lag: time gap between stream's latest entry and group's last-delivered
                    delivery_lag_s: float | None = None
                    if last_id and last_delivered:
                        try:
                            ts_last = int(str(last_id).split("-")[0]) / 1000.0
                            ts_delivered = int(last_delivered.split("-")[0]) / 1000.0
                            delivery_lag_s = round(ts_last - ts_delivered, 1)
                        except Exception:
                            pass

                    # Per-consumer idle times (XINFO CONSUMERS)
                    consumers_detail: list[dict] = []
                    try:
                        cons_raw = await asyncio.wait_for(
                            r.xinfo_consumers(stream_key, gname), timeout=0.2
                        )
                        for c in cons_raw:
                            cname = str(c.get("name", "?"))
                            cidle = int(c.get("idle", 0))
                            cpending = int(c.get("pending", 0))
                            consumers_detail.append({
                                "name": cname,
                                "idle_ms": cidle,
                                "pending": cpending,
                            })
                            if cidle > _cg_warn_idle_ms:
                                sv_blockers.append(
                                    f"consumer {gname}/{cname}: idle={cidle}ms "
                                    f"(warn>{_cg_warn_idle_ms}ms)"
                                )
                    except Exception:
                        pass  # XINFO CONSUMERS may fail or be unsupported

                    cg_entry = {
                        "name": gname,
                        "consumers": consumers,
                        "pending": pending,
                        "lag": lag,
                        "lag_ratio": round(lag_ratio, 4),
                        "last_delivered_id": last_delivered,
                        "delivery_lag_s": delivery_lag_s,
                        "consumers_detail": consumers_detail,
                    }
                    cg_list.append(cg_entry)
                    if pending > _cg_warn_pending:
                        sv_blockers.append(f"group {gname}: pending={pending} (warn>{_cg_warn_pending})")
                    if lag > _cg_warn_lag:
                        sv_blockers.append(f"group {gname}: lag={lag} (warn>{_cg_warn_lag})")
                    if lag_ratio > _cg_warn_lag_ratio:
                        sv_blockers.append(
                            f"group {gname}: lag_ratio={lag_ratio:.2f} "
                            f"(lag={lag}, xlen={length}, warn>{_cg_warn_lag_ratio:.2f})"
                        )
                    if delivery_lag_s is not None and delivery_lag_s > _cg_warn_delivery_lag_s:
                        sv_blockers.append(
                            f"group {gname}: delivery lag={delivery_lag_s}s "
                            f"(warn>{_cg_warn_delivery_lag_s}s)"
                        )
                if cg_list:
                    consumer_groups[stream_key] = cg_list
            except Exception:
                pass  # stream may not have groups

            if sv_state == "ready" and sv_blockers:
                sv_state = "degraded"
                streams[stream_key]["state"] = sv_state

            # Dead letter: separate health axis
            if "dead" in stream_key and length is not None and length > 0:
                if length >= _dl_block:
                    dead_letter_state = "blocked"
                    blockers.append(f"dead letter critical backlog: {length} (limit={_dl_block})")
                elif length > _dl_warn:
                    dead_letter_state = "degraded"
                    blockers.append(f"dead letter backlog: {length} (warn>{_dl_warn})")

                # DLQ growth trend — compare against previous snapshot
                dlq_trend = _compute_dlq_trend(stream_key, length)
                if dlq_trend is not None:
                    dead_letter_growth[stream_key] = dlq_trend
                    if dlq_trend["trend"] == "growing" and dlq_trend["delta"] >= _dl_growth_warn:
                        if dead_letter_state == "ready":
                            dead_letter_state = "degraded"
                        blockers.append(
                            f"dead letter growing: {stream_key} +{dlq_trend['delta']} "
                            f"({dlq_trend['delta_pct']}%, was {dlq_trend['prev_length']} "
                            f"{dlq_trend['since_s']}s ago)"
                        )
                # Don't affect redis_state or stream_state from dead letter

            # Stream aggregate: if any key stream is unhealthy, mark stream_state
            if sv_state != "ready" and "dead" not in stream_key:
                if stream_state == "ready":
                    stream_state = sv_state
    finally:
        try:
            await r.aclose()
        except Exception:
            pass

    # Aggregate overall state: worst of redis/stream/dead_letter
    overall = redis_state
    if stream_state == "blocked" or dead_letter_state == "blocked":
        overall = "blocked"
    elif stream_state == "degraded" or dead_letter_state == "degraded":
        overall = "degraded"

    # SSE client snapshot
    sse_clients = await _sse_snapshot()

    # Consumer groups flat summary for operational visibility
    cg_summary: list[dict] = []
    for sk, cg_list in consumer_groups.items():
        for cg in cg_list:
            cg_summary.append({
                "stream": sk,
                "group": cg["name"],
                "consumers": cg["consumers"],
                "pending": cg["pending"],
                "lag": cg["lag"],
                "lag_ratio": cg.get("lag_ratio"),
                "delivery_lag_s": cg.get("delivery_lag_s"),
            })

    return {
        "ok": True,
        "state": overall,
        "redis_state": redis_state,
        "stream_state": stream_state,
        "dead_letter_state": dead_letter_state,
        "consumer_groups": consumer_groups,
        "consumer_groups_summary": cg_summary,
        "dead_letter_growth": dead_letter_growth,
        "sse_clients": sse_clients,
        "latency_ms": latency_ms,
        "redis_url_masked": url_masked,
        "checked_at": checked_at,
        "server": server_info,
        "streams": streams,
        "blockers": blockers,
    }


@app.get("/api/v1/runtime/redis-health")
async def redis_health():
    """Redis 运行态健康诊断：PING + INFO + 关键 Stream 检查。

    只读，短超时，不扫全库，不创建连接池。"""
    try:
        async with asyncio.timeout(1.5):
            return await _redis_health_snapshot()
    except Exception as exc:
        return {
            "ok": False,
            "state": "blocked",
            "latency_ms": None,
            "redis_url_masked": str(os.getenv("REDIS_URL", "redis://localhost:6379/0")).strip(),
            "checked_at": "",
            "server": {},
            "streams": {},
            "consumer_groups": {},
            "consumer_groups_summary": [],
            "dead_letter_growth": {},
            "sse_clients": {},
            "blockers": [f"redis health timeout/error: {exc}"],
        }


# ── P1-3.2: Decision 消费侧试点 — 统一读取 _decision 字段 ──

@app.get("/api/v1/decision/latest")
async def decision_latest(limit: int = Query(default=10, ge=1, le=50)):
    """消费侧试点：从 Kline + W2S alert streams 读取最新 _decision。

    优先消费 _decision 字段（P1-3.1 producer 产出），
    legacy 无 _decision 的消息用 ensure_decision() fallback 包装。
    """
    import redis.asyncio as aioredis

    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    decisions: list[dict] = []

    try:
        for stream_key in ("stream:kline:alerts", "stream:w2s:alerts"):
            try:
                entries = await r.xrevrange(stream_key, "+", "-", count=limit)
            except Exception:
                continue

            for entry_id, data in entries:
                # 优先读取 _decision
                dec = data.get("_decision")
                if dec:
                    try:
                        decisions.append(json.loads(dec))
                    except (json.JSONDecodeError, TypeError):
                        pass
                else:
                    # legacy fallback: 用 ensure_decision 包装
                    try:
                        from core.contracts.decision import ensure_decision, ALERT
                        dt = "support_alert" if "kline" in stream_key else "w2s_alert"
                        d = ensure_decision(data, decision_type=dt, level=ALERT)
                        decisions.append(d.to_dict())
                    except Exception:
                        pass
    finally:
        await r.aclose()

    return {
        "total": len(decisions),
        "source": "stream:kline:alerts + stream:w2s:alerts",
        "prefer": "_decision (P1-3.1 producer), fallback ensure_decision()",
        "decisions": decisions,
    }


async def _auto_start_realtime_stack(app: FastAPI) -> None:
    """SPS 启动 5 秒后自动拉起实时管线进程。"""
    await asyncio.sleep(5)
    try:
        mgr: RealtimeStackManager = app.state.realtime_manager
        await mgr.start()
        logger.warning("AUTO_START realtime stack: ok")
    except Exception as exc:
        logger.warning("AUTO_START realtime stack failed: %s", exc)


async def _run_kline_break_detector_loop(app: FastAPI) -> None:
    """P1-G: 支撑位突破检测后台循环 (盘中自动运行, 10s 间隔)。"""
    logger_kline = logging.getLogger("sps.kline_break_detector.loop")
    await asyncio.sleep(5)  # 等待服务完全就绪

    from stock_processing_service.domain.services.kline_break_detector import KlineBreakDetector
    from stock_processing_service.sinks.kline_alert_redis_pusher import KlineAlertRedisPusher

    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock_data_test")
    redis_url = _redis_url()
    detector = KlineBreakDetector(dsn, redis_url=redis_url)
    pusher = KlineAlertRedisPusher(redis_url)

    while True:
        try:
            now = datetime.now()
            # 仅交易日盘中运行
            if now.weekday() >= 5:
                await asyncio.sleep(60)
                continue
            h, m = now.hour, now.minute
            # 竞价+盘中: 9:15-15:05
            in_session = (h == 9 and m >= 15) or (10 <= h <= 14) or (h == 15 and m <= 5)
            if not in_session:
                await asyncio.sleep(30)
                continue

            result = await detector.detect()
            if result.alerts:
                pushed = await pusher.push_alerts(result.alerts)
                if pushed:
                    logger_kline.warning(
                        "KLINE_ALERTS: %d pushed (checked=%d with_quotes=%d "
                        "suppressed_cooldown=%d suppressed_confirm=%d elapsed=%dms)",
                        pushed, result.checked, result.with_quotes,
                        result.suppressed_by_cooldown, result.suppressed_by_confirm,
                        result.elapsed_ms,
                    )

            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger_kline.warning("Kline break detector error: %s", exc)
            await asyncio.sleep(30)

    await detector.close()
    await pusher.close()


def _w2s_intraday_session(now: datetime) -> bool:
    h, m = now.hour, now.minute
    return (h == 9 and m >= 30) or (10 <= h <= 14) or (h == 15 and m <= 5)


def _w2s_auction_session(now: datetime) -> bool:
    h, m = now.hour, now.minute
    return h == 9 and 25 <= m <= 29


async def _resolve_w2s_candidate_date(confirm_trade_date: date) -> date:
    try:
        return await _resolve_prev_trade_date(confirm_trade_date)
    except Exception:
        from datetime import timedelta
        return confirm_trade_date - timedelta(days=1)


async def _run_w2s_alert_loop(app: FastAPI) -> None:
    """P1-I: 弱转强统一告警后台循环。

    这个 loop 负责把文档里的 w2s_unified_alert_service 托管起来：
    9:25-9:29 运行竞价确认，9:30-15:05 运行盘中 v2.2 观察，
    输出统一进入 stream:w2s:alerts，前端 W2S 勾选框只负责 SSE 订阅。
    """
    logger_w2s = logging.getLogger("sps.w2s_alert.loop")
    await asyncio.sleep(float(os.getenv("SPS_W2S_ALERT_LOOP_BOOT_DELAY", "8") or 8))

    from stock_processing_service.domain.services.w2s_unified_alert_service import W2SUnifiedAlertService
    from stock_processing_service.sinks.w2s_alert_redis_pusher import W2SAlertRedisPusher

    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock_data_test")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    intraday_interval = max(int(os.getenv("SPS_W2S_INTRADAY_INTERVAL_SECONDS", "30") or 30), 5)
    idle_interval = max(int(os.getenv("SPS_W2S_IDLE_INTERVAL_SECONDS", "30") or 30), 10)
    auction_retry_interval = max(int(os.getenv("SPS_W2S_AUCTION_RETRY_SECONDS", "20") or 20), 5)

    svc = W2SUnifiedAlertService(dsn, redis_url=redis_url)
    pusher = W2SAlertRedisPusher(redis_url)
    status = app.state.w2s_alert_status
    status["enabled"] = True
    status["running"] = True
    auction_done_for: str | None = None

    try:
        while True:
            try:
                now = datetime.now(ZoneInfo("Asia/Shanghai"))
                trade_date = now.date()
                status["running"] = True
                status["last_run_at"] = now.isoformat()
                status["trade_date"] = trade_date.isoformat()

                if now.weekday() >= 5:
                    status["phase"] = "weekend_idle"
                    await asyncio.sleep(60)
                    continue

                candidate_date = await _resolve_w2s_candidate_date(trade_date)
                status["candidate_trade_date"] = candidate_date.isoformat()

                if _w2s_auction_session(now):
                    status["phase"] = "auction"
                    alerts = await svc.build_auction_alerts(candidate_date.isoformat(), trade_date.isoformat())
                    pushed = await pusher.push_unified_alerts(alerts)
                    status["last_built"] = len(alerts)
                    status["last_pushed"] = pushed
                    status["total_built"] = int(status.get("total_built") or 0) + len(alerts)
                    status["total_pushed"] = int(status.get("total_pushed") or 0) + pushed
                    status["last_success_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
                    status["last_error"] = None
                    if pushed or alerts:
                        auction_done_for = trade_date.isoformat()
                        logger_w2s.warning(
                            "W2S auction loop: built=%d pushed=%d candidate=%s confirm=%s",
                            len(alerts), pushed, candidate_date, trade_date,
                        )
                    await asyncio.sleep(auction_retry_interval if auction_done_for != trade_date.isoformat() else 60)
                    continue

                if _w2s_intraday_session(now):
                    status["phase"] = "intraday"
                    alerts = await svc.build_intraday_alerts(trade_date.isoformat())
                    pushed = await pusher.push_unified_alerts(alerts)
                    status["last_built"] = len(alerts)
                    status["last_pushed"] = pushed
                    status["total_built"] = int(status.get("total_built") or 0) + len(alerts)
                    status["total_pushed"] = int(status.get("total_pushed") or 0) + pushed
                    status["last_success_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
                    status["last_error"] = None
                    if pushed:
                        logger_w2s.warning("W2S intraday loop: built=%d pushed=%d trade=%s", len(alerts), pushed, trade_date)
                    await asyncio.sleep(intraday_interval)
                    continue

                status["phase"] = "idle"
                await asyncio.sleep(idle_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status["last_error"] = str(exc)
                logger_w2s.warning("W2S alert loop error: %s", exc)
                await asyncio.sleep(30)
    finally:
        status["running"] = False
        await svc.close()
        await pusher.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row to a dict."""
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)


# ── PR-12.5: Mainline Review API ──

@app.get("/api/v2/mainline-review/queue")
async def get_mainline_review_queue(
    trade_date: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """查询主线审核队列。"""
    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return {"items": [], "total": 0}
    td = date.fromisoformat(trade_date) if trade_date else None
    async with pool.acquire() as conn:
        where = []; params: list = []; i = 0
        if td is not None: i += 1; where.append(f"trade_date = ${i}::date"); params.append(td)
        if status is not None: i += 1; where.append(f"review_status = ${i}"); params.append(status)
        i += 1; params.append(min(limit, 500))
        cond = ("WHERE " + " AND ".join(where)) if where else ""
        rows = await conn.fetch(
            f"SELECT * FROM mainline_review_queue {cond} ORDER BY review_priority DESC NULLS LAST LIMIT ${i}",
            *params,
        )
        items = [_row_to_dict(r) for r in rows]

        # ── 解析数字型 theme_name → 中文名 ──
        numeric_sks: list[str] = []
        for item in items:
            tn = str(item.get("theme_name") or "")
            sk = str(item.get("subject_key") or "")
            if (not tn or tn == sk or (tn.isdigit() and len(tn) >= 5)):
                if sk not in numeric_sks:
                    numeric_sks.append(sk)
        if numeric_sks:
            import re as _re
            name_map: dict[str, str] = {}
            try:
                name_rows = await conn.fetch(
                    "SELECT subject_key, subject_name FROM event_subject_map"
                    " WHERE subject_key = ANY($1::text[])",
                    numeric_sks,
                )
                for nr in name_rows:
                    name = str(nr.get("subject_name") or "").strip()
                    if name:
                        name_map[str(nr["subject_key"])] = name
            except Exception:
                pass
            try:
                stage_rows = await conn.fetch(
                    "SELECT subject_key, subject_name FROM subject_node_staging"
                    " WHERE subject_key = ANY($1::text[])",
                    [sk for sk in numeric_sks if sk not in name_map],
                )
                for sr in stage_rows:
                    name = str(sr.get("subject_name") or "").strip()
                    if name:
                        name_map[str(sr["subject_key"])] = name
            except Exception:
                pass
            try:
                hist_rows = await conn.fetch(
                    "SELECT DISTINCT ON (subject_key) subject_key, subject_name"
                    " FROM subject_history_staging"
                    " WHERE subject_key = ANY($1::text[]) AND subject_name IS NOT NULL AND subject_name != ''",
                    [sk for sk in numeric_sks if sk not in name_map],
                )
                for hr in hist_rows:
                    name = str(hr.get("subject_name") or "").strip()
                    if name:
                        name_map[str(hr["subject_key"])] = name
            except Exception:
                pass
            for item in items:
                sk = str(item.get("subject_key") or "")
                resolved = name_map.get(sk, "")
                if resolved:
                    item["theme_name"] = resolved

        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM mainline_review_queue WHERE review_status = $1", "pending",
        ) if not status else None
        return {"items": items, "total": pending, "pending_count": pending}


@app.get("/api/v2/mainline-review/registry")
async def get_mainline_registry(trade_date: str | None = None, limit: int = 100) -> dict[str, Any]:
    """查询已确认的主线注册表。"""
    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return {"items": [], "total": 0}
    async with pool.acquire() as conn:
        td = date.fromisoformat(trade_date) if trade_date else None
        params: list = []; i = 0
        if td is not None: i += 1; params.append(td); w = f"valid_from <= ${i}::date AND (valid_to IS NULL OR valid_to >= ${i}::date)"
        else: w = "1=1"
        i += 1; params.append(min(limit, 100))
        rows = await conn.fetch(f"SELECT * FROM mainline_registry WHERE identity_status = 'confirmed' AND {w} ORDER BY valid_from DESC LIMIT ${i}", *params)
    return {"items": [_row_to_dict(r) for r in rows], "total": len(rows)}


@app.post("/api/v2/mainline-review/import-candidates")
async def import_mainline_review_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    """导入当日主线候选。从 recap snapshot 读取 analyst_review_items。"""
    td_str = str(payload.get("trade_date") or "")
    if not td_str:
        return {"ok": False, "error": "trade_date required"}
    try:
        d = date.fromisoformat(td_str)
    except ValueError:
        return {"ok": False, "error": "invalid date"}
    try:
        row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
        if not row:
            return {"ok": False, "error": "no snapshot for date"}
        payload_data = _normalize_recap_payload(row)
        rd = payload_data.get("recap_doc") or payload_data
        items = rd.get("analyst_review_items") if isinstance(rd, dict) else None
        if not isinstance(items, list) or not items:
            return {"ok": False, "error": "no analyst_review_items in snapshot", "count": 0}
        pool = getattr(getattr(app.state, "gateway", None), "_client", None)
        pool = getattr(pool, "pool", None) if pool else None
        if pool is None:
            return {"ok": False, "error": "no db pool"}
        count = 0
        from database_service.managers.postgres_manager import _row_to_dict as _rd
        async with pool.acquire() as conn:
            for item in items:
                try:
                    await conn.execute("""
                        INSERT INTO mainline_review_queue
                          (review_id, trade_date, subject_key, theme_name, machine_state, mainline_type,
                           confirmation_path, trigger_mode, review_reason, review_priority, review_status,
                           suggested_human_decision, scores_json, evidence_json, risk_flags_json, diagnostics_json)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                        ON CONFLICT (review_id) DO NOTHING
                    """, str(item.get("review_id", "")), d, str(item.get("subject_key", "")),
                        str(item.get("theme_name", "")), str(item.get("machine_state", "")),
                        str(item.get("mainline_type", "")), str(item.get("confirmation_path", "")),
                        str(item.get("trigger_mode", "")), str(item.get("review_reason", "")),
                        float(item.get("review_priority", 0)), str(item.get("review_status", "pending")),
                        str(item.get("suggested_human_decision", "")),
                        json.dumps(item.get("scores", {})), json.dumps(item.get("evidence", {})),
                        json.dumps(item.get("risk_flags", {})), json.dumps(item.get("diagnostics", {})),
                    )
                    count += 1
                except Exception:
                    pass
        return {"ok": True, "count": count}
    except Exception as exc:
        logger.error("import mainline candidates failed: %s", exc)
        return {"ok": False, "error": str(exc)[:200]}


@app.post("/api/v2/mainline-review/{review_id}/decision")
async def submit_mainline_review_decision(review_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """提交人工审核决策。"""
    decision = str(payload.get("human_decision", ""))
    valid = {"confirm_mainline", "watch", "reject", "downgrade_to_theme", "merge_into_existing_mainline"}
    if decision not in valid:
        return {"ok": False, "error": f"invalid decision: {decision}", "valid": list(valid)}

    pool = getattr(getattr(app.state, "gateway", None), "_client", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return {"ok": False, "error": "no db pool"}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    reviewed_by = str(payload.get("human_reviewer", "system") or "system")
    notes = str(payload.get("human_notes", "") or "")

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM mainline_review_queue WHERE review_id = $1", review_id)
        if not row:
            return {"ok": False, "error": "review not found"}

        td = row["trade_date"]

        # Update the review queue entry
        await conn.execute("""
            UPDATE mainline_review_queue SET review_status = 'reviewed', human_decision = $2,
              human_reviewer = $3, human_notes = $4, reviewed_at = $5 WHERE review_id = $1
        """, review_id, decision, reviewed_by, notes, now)

        if decision == "confirm_mainline":
            csk = str(payload.get("canonical_subject_key", "") or "")
            ml_name = str(payload.get("mainline_name", "") or row["theme_name"] or "")
            if not csk:
                return {"ok": False, "error": "confirm_mainline requires canonical_subject_key"}
            mid = f"ml_{csk}_{td.strftime('%Y%m') if td else 'unknown'}"
            await conn.execute("""
                INSERT INTO mainline_registry (mainline_id, mainline_name, canonical_subject_key, identity_status, valid_from,
                  mainline_type, source_review_id, core_subject_keys_json, related_subject_keys_json, human_reviewer, human_notes)
                VALUES ($1,$2,$3,'confirmed',$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (mainline_id) DO UPDATE SET
                  mainline_name=$2, identity_status='confirmed', updated_at=NOW()
            """, mid, ml_name, csk, td,
                str(row.get("mainline_type") or ""), review_id,
                json.dumps([csk]), json.dumps(payload.get("related_subject_keys", []) or []),
                reviewed_by, notes)
            return {"ok": True, "action": "confirmed", "mainline_id": mid}

        if decision == "merge_into_existing_mainline":
            target = str(payload.get("merge_target_mainline_id", "") or "")
            if not target:
                return {"ok": False, "error": "merge requires merge_target_mainline_id"}
            related = list(payload.get("related_subject_keys", []) or [])
            existing = await conn.fetchval("SELECT related_subject_keys_json FROM mainline_registry WHERE mainline_id = $1", target)
            current = json.loads(existing) if isinstance(existing, str) else (existing or [])
            merged = list(set(current + related + [str(row["subject_key"] or "")]))
            await conn.execute("UPDATE mainline_registry SET related_subject_keys_json = $2, updated_at = NOW() WHERE mainline_id = $1", target, json.dumps(merged))
            return {"ok": True, "action": "merged", "target": target}

        # watch / reject / downgrade_to_theme — queue only, no registry
        return {"ok": True, "action": decision, "registry_written": False}


# ── M4g: Recap Read Model API ───────────────────────────────────


@app.get("/api/v1/recap/latest")
async def get_recap_latest() -> dict[str, Any]:
    """Return the most recent market recap snapshot."""
    try:
        from asyncpg import connect as _pg_connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await _pg_connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
        try:
            row = await conn.fetchrow(
                "SELECT recap_json, trade_date, created_at "
                "FROM market_recap_snapshot ORDER BY trade_date DESC LIMIT 1"
            )
            if not row:
                raise HTTPException(status_code=404, detail="no recap snapshot found")
            data = row["recap_json"] if isinstance(row["recap_json"], dict) else json.loads(row["recap_json"])
            data["_meta"] = {
                "trade_date": str(row["trade_date"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            return data
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/recap/{trade_date}")
async def get_recap_by_date(trade_date: str) -> dict[str, Any]:
    """Return market recap for a specific trade date."""
    try:
        from asyncpg import connect as _pg_connect
        import json as _json
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await _pg_connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
        try:
            td_date = date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
            row = await conn.fetchrow(
                "SELECT recap_json, trade_date, created_at "
                "FROM market_recap_snapshot WHERE trade_date = $1::date",
                td_date,
            )
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"no recap snapshot for {trade_date}",
                )
            data = row["recap_json"] if isinstance(row["recap_json"], dict) else _json.loads(row["recap_json"])
            data["_meta"] = {
                "trade_date": str(row["trade_date"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            return data
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/themes/top")
async def get_top_themes(
    trade_date: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top themes by strength score."""
    try:
        from asyncpg import connect as _pg_connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await _pg_connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
        try:
            if trade_date:
                rows = await conn.fetch(
                    "SELECT theme_name, strength_score, rank, stock_count, "
                    "leader_count, top_stocks, evidence_sources "
                    "FROM theme_strength_snapshot "
                    "WHERE trade_date = $1::date ORDER BY rank LIMIT $2",
                    trade_date, min(limit, 20),
                )
            else:
                rows = await conn.fetch(
                    "SELECT DISTINCT ON (theme_name) theme_name, strength_score, "
                    "rank, stock_count, leader_count, top_stocks, evidence_sources, trade_date "
                    "FROM theme_strength_snapshot "
                    "ORDER BY theme_name, trade_date DESC "
                    "LIMIT $1",
                    min(limit, 20),
                )
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.1 Attention Radar ──

@app.get("/api/v1/attention/{trade_date}")
async def get_attention_state(trade_date: str) -> dict[str, Any]:
    """Return MarketAttentionState for a trading day."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_cognition.attention_engine import (
        AttentionEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        engine = AttentionEngine()
        state = await engine.run_async(td)
        return state.to_dict()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/attention/{trade_date}/override")
async def record_attention_override(
    trade_date: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Record an analyst override to attention state."""
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from stock_processing_service.contracts.analyst_attention import AttentionOverride
    import json as _json
    from pathlib import Path as _Path

    try:
        td = _date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")

    override = AttentionOverride(
        trade_date=td,
        subject_id=body.get("subject_id", ""),
        field_name=body.get("field", "level"),
        ai_value=str(body.get("ai_value", "")),
        analyst_value=str(body.get("analyst_value", "")),
        override_reason=body.get("reason", ""),
        analyst_id=body.get("analyst_id", "analyst"),
        created_at=_dt.now(_tz.utc),
    )

    # Persist to JSONL file
    log_dir = _Path("tmp/analyst_overrides")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{trade_date}_overrides.jsonl"
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(_json.dumps({
            "trade_date": override.trade_date.isoformat(),
            "subject_id": override.subject_id,
            "field_name": override.field_name,
            "ai_value": override.ai_value,
            "analyst_value": override.analyst_value,
            "override_reason": override.override_reason,
            "analyst_id": override.analyst_id,
            "created_at": override.created_at.isoformat() if override.created_at else None,
        }, ensure_ascii=False) + "\n")

    return {"status": "recorded", "trade_date": trade_date, "subject_id": override.subject_id}


# ── P2.2 Cognition Workspace ──

@app.get("/api/v1/cognition/{trade_date}/{subject_id}")
async def get_cognition_card(trade_date: str, subject_id: str) -> dict[str, Any]:
    """Return AI-generated CognitionCard for a subject."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_cognition.cognition_card_builder import (
        CognitionCardBuilder,
    )
    try:
        td = _date.fromisoformat(trade_date)
        builder = CognitionCardBuilder()
        card = await builder.build_async(td, subject_id)
        return card
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/cognition/{trade_date}/{subject_id}/save")
async def save_cognition_card(
    trade_date: str,
    subject_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Save analyst-modified CognitionCard and log all overrides."""
    from datetime import date as _date, datetime as _dt, timezone as _tz
    import json as _json
    from pathlib import Path as _Path

    try:
        td = _date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")

    overrides = body.get("analyst_overrides", {})
    override_count = 0

    # Log each override
    if overrides:
        log_dir = _Path("tmp/analyst_overrides")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{trade_date}_cognition_overrides.jsonl"

        for field_name, change in overrides.items():
            if isinstance(change, dict):
                with open(log_file, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps({
                        "trade_date": trade_date,
                        "subject_id": subject_id,
                        "object_type": "cognition_card",
                        "field_name": field_name,
                        "ai_value": str(change.get("ai_value", "")),
                        "analyst_value": str(change.get("analyst_value", "")),
                        "override_reason": str(change.get("reason", "")),
                        "analyst_id": "analyst",
                        "created_at": _dt.now(_tz.utc).isoformat(),
                    }, ensure_ascii=False) + "\n")
                override_count += 1

    # Save card to JSON
    save_dir = _Path("tmp/cognition_cards")
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_id = subject_id.replace("/", "_")
    save_path = save_dir / f"{trade_date}_{safe_id}.json"
    save_path.write_text(_json.dumps({
        **body,
        "analyst_reviewed": True,
        "ai_draft": False,
        "saved_at": _dt.now(_tz.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "saved",
        "trade_date": trade_date,
        "subject_id": subject_id,
        "overrides_recorded": override_count,
        "path": str(save_path),
    }


# ── P2.4 Playbook Builder ──

@app.get("/api/v1/playbook/{trade_date}/{subject_id}")
async def get_playbook(trade_date: str, subject_id: str) -> dict[str, Any]:
    """Return AI-generated MarketPlaybook for a subject."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_cognition.cognition_card_builder import (
        CognitionCardBuilder,
    )
    from stock_processing_service.application.services.market_cognition.playbook_builder import (
        PlaybookBuilder,
    )
    try:
        td = _date.fromisoformat(trade_date)
        card_builder = CognitionCardBuilder()
        card = await card_builder.build_async(td, subject_id)
        pb = PlaybookBuilder()
        playbook = pb.build(card)
        playbook["review"] = pb.build_review(card)
        return playbook
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/playbook/{trade_date}/{subject_id}/save")
async def save_playbook(
    trade_date: str,
    subject_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Save analyst-modified Playbook and log overrides."""
    from datetime import date as _date, datetime as _dt, timezone as _tz
    import json as _json
    from pathlib import Path as _Path

    try:
        td = _date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")

    overrides = body.get("analyst_overrides", {})
    override_count = 0

    if overrides:
        log_dir = _Path("tmp/analyst_overrides")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{trade_date}_playbook_overrides.jsonl"
        for field_name, change in overrides.items():
            if isinstance(change, dict):
                with open(log_file, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps({
                        "trade_date": trade_date,
                        "subject_id": subject_id,
                        "object_type": "playbook",
                        "field_name": field_name,
                        "ai_value": str(change.get("ai_value", "")),
                        "analyst_value": str(change.get("analyst_value", "")),
                        "override_reason": str(change.get("reason", "")),
                        "created_at": _dt.now(_tz.utc).isoformat(),
                    }, ensure_ascii=False) + "\n")
                override_count += 1

    save_dir = _Path("tmp/playbooks")
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_id = subject_id.replace("/", "_")
    save_path = save_dir / f"{trade_date}_{safe_id}.json"
    save_path.write_text(_json.dumps({
        **body,
        "analyst_reviewed": True,
        "ai_draft": False,
        "saved_at": _dt.now(_tz.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "saved",
        "trade_date": trade_date,
        "subject_id": subject_id,
        "overrides_recorded": override_count,
    }


# ── M2.5 Market Metrics (canonical facts) ──

@app.get("/api/v1/market-metrics/{trade_date}")
async def get_market_metrics(trade_date: str, em: bool = False) -> dict[str, Any]:
    """Return MarketMetricsSnapshot — canonical facts for a trading day.

    Query params:
      em=true — include Eastmoney board pool data (a-stock-data 打板层)
    """
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    try:
        td = _date.fromisoformat(trade_date)

        # ── Board pool provider (a-stock-data Eastmoney API) ──
        em_board = None; em_pool = em_fried = em_dt = None
        board_prov = None
        if em:
            try:
                from application.services.market_metrics.board_pool_provider import (
                    create_board_provider,
                )
                bp = create_board_provider()
                board_prov = bp
                em_board = await bp.get_sentiment(td)
                em_pool = await bp.get_limit_up_pool(td)
                em_fried = await bp.get_fried_pool(td)
                em_dt = await bp.get_dt_pool(td)
            except Exception:
                pass

        svc = MarketMetricsService(board_provider=board_prov)
        snap = await svc.get_async(td)
        if board_prov:
            try:
                await board_prov.close()
            except Exception:
                pass
        result = {
            "trade_date": snap.trade_date.isoformat(),
            "calibration_applied": snap.calibration_applied,
            "calibration_source": snap.calibration_source,
            "calibration_fields": list(snap.calibration_fields),
            "breadth": {
                "up_count": snap.breadth.up_count,
                "down_count": snap.breadth.down_count,
                "limit_up_count": snap.breadth.limit_up_count,
                "limit_down_count": snap.breadth.limit_down_count,
                "up_ratio": snap.breadth.up_ratio,
                "turnover_yi": snap.breadth.turnover_yi,
                "turnover_display": f"{snap.breadth.turnover_yi / 10000:.2f}万亿" if snap.breadth.turnover_yi >= 10000 else f"{snap.breadth.turnover_yi:.1f}亿",
                "source": snap.breadth.source.source_type,
                "is_calibrated": snap.breadth.source.is_calibrated,
            },
            "limitup": {
                "total_count": snap.limitup.total_count,
                "sealed_count": snap.limitup.sealed_count,
                "fried_board_count": snap.limitup.fried_board_count,
                "sealed_board_ratio": snap.limitup.sealed_board_ratio,
                "chain_board_count": snap.limitup.chain_board_count,
                "current_board_height": snap.limitup.current_board_height,
                "historical_streak_height": snap.limitup.historical_streak_height,
                "max_board_height": snap.limitup.max_board_height,
                "max_turnover_board_height": snap.limitup.max_turnover_board_height,
                "first_board_count": snap.limitup.first_board_count,
                "first_board_success_rate": snap.limitup.first_board_success_rate,
                "high_board_count": snap.limitup.high_board_count,
                "avg_turnover_rate": snap.limitup.avg_turnover_rate,
                "avg_amount_yi": snap.limitup.avg_amount_yi,
                "avg_big_order_net_yi": snap.limitup.avg_big_order_net_yi,
                "fried_amount_ratio": snap.limitup.fried_amount_ratio,
                "board_type_counts": snap.limitup.board_type_counts,
                "source": snap.limitup.source.source_type,
            },
            "relay": {
                "promotion_1_to_2": snap.relay.promotion_1_to_2,
                "promotion_2_to_3": snap.relay.promotion_2_to_3,
                "promotion_3_to_4": snap.relay.promotion_3_to_4,
                "chain_board_count": snap.relay.chain_board_count,
                "max_board_height": snap.relay.max_board_height,
                "max_turnover_board_height": snap.relay.max_turnover_board_height,
                "yesterday_limitup_count": snap.relay.yesterday_limitup_count,
                "today_continue_count": snap.relay.today_continue_count,
                "continue_ratio": snap.relay.continue_ratio,
                "yesterday_big_loss_count": snap.relay.yesterday_big_loss_count,
                "yesterday_avg_return_pct": snap.relay.yesterday_avg_return_pct,
                "feedback_score": snap.relay.feedback_score,
                "feedback_label": snap.relay.feedback_label,
                "feedback_components": snap.relay.feedback_components,
                "high_board_count": snap.relay.high_board_count,
                "high_board_break_count": snap.relay.high_board_break_count,
            },
            "loss_effect": None if snap.loss_effect is None else {
                "limit_down_count": snap.loss_effect.limit_down_count,
                "limit_down_ratio": snap.loss_effect.limit_down_ratio,
                "limit_down_amount_yi": snap.loss_effect.limit_down_amount_yi,
                "big_loss_count": snap.loss_effect.big_loss_count,
                "big_loss_from_yesterday_ratio": snap.loss_effect.big_loss_from_yesterday_ratio,
                "high_board_break_count": snap.loss_effect.high_board_break_count,
                "loss_effect_score": snap.loss_effect.loss_effect_score,
                "loss_effect_label": snap.loss_effect.loss_effect_label,
                "total_damage_count": snap.loss_effect.total_damage_count,
                "damage_ratio": snap.loss_effect.damage_ratio,
            },
            "leader_evolution": None if snap.leader_evolution is None else {
                "leader_count": len(snap.leader_evolution.leaders),
                "yesterday_leader_count": snap.leader_evolution.yesterday_leader_count,
                "continue_count": snap.leader_evolution.continue_count,
                "super_continue_count": snap.leader_evolution.super_continue_count,
                "weaken_expected_count": snap.leader_evolution.weaken_expected_count,
                "weaken_unexpected_count": snap.leader_evolution.weaken_unexpected_count,
                "break_count": snap.leader_evolution.break_count,
                "new_leader_count": snap.leader_evolution.new_leader_count,
                "replaced_count": snap.leader_evolution.replaced_count,
                "leader_health_score": snap.leader_evolution.leader_health_score,
                "leader_health_label": snap.leader_evolution.leader_health_label,
                "leader_break_alert": snap.leader_evolution.leader_break_alert,
                "avg_surprise_score": snap.leader_evolution.avg_surprise_score,
                "leaders": [{
                    "stock_code": l.stock_code,
                    "stock_name": l.stock_name,
                    "board_height": l.board_height,
                    "status": l.status,
                    "expected_height": l.expected_height,
                    "surprise_score": l.surprise_score,
                    "strength_score": l.strength_score,
                    "risk_score": l.risk_score,
                    "sealed": l.sealed,
                    "theme_hint": l.theme_hint,
                    "reason": l.reason,
                } for l in snap.leader_evolution.leaders],
            },
            "high_position_death": None if snap.high_position_death is None else {
                "death_index": snap.high_position_death.death_index,
                "death_label": snap.high_position_death.death_label,
                "leader_break_count": snap.high_position_death.leader_break_count,
                "high_board_loss_count": snap.high_position_death.high_board_loss_count,
                "big_loss_count": snap.high_position_death.big_loss_count,
                "death_conclusion": snap.high_position_death.death_conclusion,
                "risk_escalation": snap.high_position_death.risk_escalation,
            },
            "loss_attribution": None if snap.loss_attribution is None else {
                "limit_down_count": snap.loss_attribution.limit_down_count,
                "high_board_loss_count": snap.loss_attribution.high_board_loss_count,
                "yesterday_limitup_loss_count": snap.loss_attribution.yesterday_limitup_loss_count,
                "leader_loss_count": snap.loss_attribution.leader_loss_count,
                "theme_loss": snap.loss_attribution.theme_loss,
                "primary_loss_theme": snap.loss_attribution.primary_loss_theme,
                "primary_loss_count": snap.loss_attribution.primary_loss_count,
                "concentrated_high_board": snap.loss_attribution.concentrated_high_board,
                "concentrated_leader": snap.loss_attribution.concentrated_leader,
                "loss_conclusion": snap.loss_attribution.loss_conclusion,
            },
            "capital": {
                "total_turnover_yi": snap.capital.total_turnover_yi,
                "total_turnover_display": f"{snap.capital.total_turnover_yi / 10000:.2f}万亿" if snap.capital.total_turnover_yi >= 10000 else f"{snap.capital.total_turnover_yi:.0f}亿",
                "active_limitup_amount_yi": snap.capital.active_limitup_amount_yi,
                "active_ratio": snap.capital.active_ratio,
            },
            "emotion_momentum": {
                "momentum_raw": snap.emotion_momentum.momentum_raw,
                "momentum_normalized": snap.emotion_momentum.momentum_normalized,
                "first_board_red_ratio": snap.emotion_momentum.first_board_red_ratio,
                "first_board_big_loss_ratio": snap.emotion_momentum.first_board_big_loss_ratio,
                "chain_board_red_ratio": snap.emotion_momentum.chain_board_red_ratio,
                "chain_board_ratio": snap.emotion_momentum.chain_board_ratio,
                "chain_board_big_loss_ratio": snap.emotion_momentum.chain_board_big_loss_ratio,
                "yesterday_chain_not_limit_red_ratio": snap.emotion_momentum.yesterday_chain_not_limit_red_ratio,
            },
            # ── Eastmoney Board Pool (a-stock-data 打板层) ──
            "eastmoney_board": None if em_board is None else {
                "source": "eastmoney_push2ex",
                "zt_count": em_board["zt_count"],
                "zb_count": em_board["zb_count"],
                "dt_count": em_board["dt_count"],
                "break_rate": em_board["break_rate"],
                "max_height": em_board["max_height"],
                "ladder": em_board["ladder"],
                "zt_pool_top5": [{
                    "code": s["code"], "name": s["name"],
                    "limit_days": s["limit_days"], "pct": s["pct"],
                    "zt_stat": s["zt_stat"], "break_times": s["break_times"],
                    "turnover": s["turnover"], "industry": s["industry"],
                } for s in (em_pool or [])[:5]] if em_pool else [],
                "fried_pool_summary": {
                    "count": len(em_fried or []),
                    "avg_break_times": round(sum(s["break_times"] for s in (em_fried or [])) / max(len(em_fried or []), 1), 1),
                } if em_fried else None,
                "dt_pool_summary": {
                    "count": len(em_dt or []),
                    "avg_dt_days": round(sum(s.get("dt_days", 0) for s in (em_dt or [])) / max(len(em_dt or []), 1), 1),
                } if em_dt else None,
            },
        }
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M8.6 Market Diagnosis ──

@app.get("/api/v1/diagnosis/{trade_date}")
async def get_market_diagnosis(trade_date: str) -> dict[str, Any]:
    """Return MarketDiagnosis tree for a trading day."""
    from datetime import date as _date
    from stock_processing_service.application.services.analyst_charts.diagnosis_engine import (
        DiagnosisEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        engine = DiagnosisEngine()
        diagnosis = await engine.run_async(td)
        return diagnosis.to_dict()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.7 Analyst Charts (multi-day trends) ──

@app.get("/api/v1/analyst-charts/{trade_date}/trends")
async def get_analyst_chart_trends(trade_date: str, days: int = 7) -> dict[str, Any]:
    """Return multi-day trend data for line charts.

    Data flow: MarketMetricsService.get_range() → ChartEngine.build_trend()
    """
    from datetime import date as _date, timedelta
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.analyst_charts.chart_engine import (
        ChartReproductionEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        start = td - timedelta(days=days + 5)  # extra buffer for non-trading days
        snapshots = await MarketMetricsService()._get_range_async(start, td)
        return ChartReproductionEngine.build_trend(snapshots)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.7 Analyst Charts ──

@app.get("/api/v1/analyst-charts/{trade_date}")
async def get_analyst_charts(trade_date: str) -> list[dict[str, Any]]:
    """Return analyst chart data for a trading day.

    Data flow: MarketMetricsService → snapshot → ChartEngine.build()
    Charts 1-4 from snapshot metrics, 5-7 from recap narrative data.
    """
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.analyst_charts.chart_engine import (
        ChartReproductionEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)

        # ── Load canonical metrics ──
        snap = await MarketMetricsService().get_async(td)

        # ── Load recap for thematic charts 5-7 ──
        recap = await _load_recap_doc(td)

        # ── Load PDF calibration ──
        pdf_cal = ChartReproductionEngine.load_pdf_calibration(td)

        # ── Build charts (no DB inside engine) ──
        engine = ChartReproductionEngine()
        return engine.build(snap, recap, pdf_cal)

    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


async def _load_recap_doc(trade_date) -> dict:
    """Load post_market_recap_snapshot for a trading date. Single source for recap loading."""
    import json
    import asyncpg
    conn = await asyncpg.connect("postgresql://localhost:5432/stock_data_test", user="postgres", password="")
    try:
        row = await conn.fetchrow(
            "SELECT payload FROM post_market_recap_snapshot "
            "WHERE trade_date = $1::date ORDER BY created_at DESC LIMIT 1",
            trade_date,
        )
        if not row:
            return {}
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload.get("recap_doc", payload)
    finally:
        await conn.close()


# ── M2.5 Phase 0.5: Metrics Validation ──

@app.get("/api/v1/metrics/validation/{trade_date}")
async def get_metrics_validation(trade_date: str) -> dict[str, Any]:
    """Return validation report: system snapshot vs analyst PDF reference."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.validation import (
        MetricsValidator,
    )
    from stock_processing_service.application.services.analyst_charts.chart_engine import (
        ChartReproductionEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        snap = await MarketMetricsService().get_async(td)
        pdf_cal = ChartReproductionEngine.load_pdf_calibration(td)
        analyst_ref: dict = {}
        if pdf_cal:
            analyst_ref = {"lu": pdf_cal.get("lu"), "turnover": pdf_cal.get("turnover")}
        report = MetricsValidator.compare(snap, analyst_ref or None)
        frozen = MetricsValidator.freeze(snap)
        return {
            "trade_date": trade_date,
            "snapshot_frozen": frozen,
            "report": {
                "overall_status": report.overall_status,
                "match_count": report.match_count,
                "diverged_count": report.diverged_count,
                "missing_analyst_count": report.missing_analyst_count,
                "missing_system_count": report.missing_system_count,
                "notes": list(report.notes),
                "diffs": [{
                    "metric_name": d.metric_name,
                    "system_value": d.system_value,
                    "analyst_value": d.analyst_value,
                    "absolute_diff": d.absolute_diff,
                    "relative_diff_pct": d.relative_diff_pct,
                    "status": d.status,
                } for d in report.diffs],
            },
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M2.5 Phase 1: Metric Registry / Data Lineage ──

@app.get("/api/v1/metrics/lineage")
async def get_metrics_lineage() -> dict[str, Any]:
    """Return complete data lineage for all registered metrics.

    Shows: metric → source_table → owner → consumers.
    No module should compute any market metric outside this registry.
    """
    from stock_processing_service.application.services.market_metrics.registry import (
        to_lineage_dict,
    )
    return to_lineage_dict()


# ── M2.5 Phase 3.0: Causal Narrative ──

@app.get("/api/v1/market-narrative/{trade_date}")
async def get_market_narrative(trade_date: str) -> dict[str, Any]:
    """Return analyst-style market narrative from canonical metrics.

    Rule-driven, not LLM. Every claim is bound to a registered metric.
    """
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.narrative_engine import (
        NarrativeEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        snap = await MarketMetricsService().get_async(td)
        engine = NarrativeEngine()
        story = engine.generate(snap)
        return story.to_dict()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M2.5 Phase 3.1b: Analyst Replay Benchmark ──

# ── M2.5 Phase 3.3: Market Memory ──

@app.get("/api/v1/market-memory/{trade_date}")
async def get_market_memory(trade_date: str, top_n: int = 5) -> dict[str, Any]:
    """Return similar historical market states and transition analysis.

    Retrieves top-N most similar trading days from history and analyzes
    what happened next — the AI equivalent of "I have seen this before."
    """
    from datetime import date as _date, timedelta
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.market_memory import (
        MarketMemoryEngine,
        MarketFingerprint,
    )
    try:
        td = _date.fromisoformat(trade_date)

        # Build memory from recent history (last 90 days)
        engine = MarketMemoryEngine()
        svc = MarketMetricsService()
        snapshots = svc.get_range(td - timedelta(days=90), td)
        for s in snapshots:
            fp = MarketFingerprint.from_snapshot(s)
            engine.remember(fp)

        # Build sequence fingerprints (4-day trajectories)
        engine.build_sequences(seq_len=4)

        # Query today
        snap_today = svc.get(td)
        query_fp = MarketFingerprint.from_snapshot(snap_today)
        analysis = engine.analyze_transition(query_fp, top_n=top_n)
        v2 = engine.analyze_transition_v2(query_fp, top_n=top_n)

        return {
            "query_date": trade_date,
            "query_fingerprint": {
                "phase_bucket": query_fp.phase_bucket,
                "death_bucket": query_fp.death_bucket,
                "feedback_bucket": query_fp.feedback_bucket,
                "raw_values": query_fp.raw_values,
            },
            "similar_days": [{
                "date": s.trade_date.isoformat(),
                "distance": s.distance,
                "similarity_pct": s.similarity_pct,
                "transition_label": s.transition_label,
                "next_day_phase": s.next_day_phase,
            } for s in analysis.similar_days],
            "transition": {
                "total_similar": analysis.total_similar,
                "improved_pct": analysis.improved_pct,
                "worsened_pct": analysis.worsened_pct,
                "stable_pct": analysis.stable_pct,
                "expected_next_phase": analysis.expected_next_phase,
                "avg_next_feedback": analysis.avg_next_feedback,
            },
            "memory_summary": analysis.memory_summary,
            "best_match": {
                "date": analysis.best_match_date.isoformat() if analysis.best_match_date else None,
                "narrative": analysis.best_match_narrative,
            },
            "v2_confidence": {
                "confidence": v2["confidence"],
                "sample_size_warning": v2.get("sample_size_warning", ""),
                "repair_probability": v2["repair_probability"],
                "worsen_probability": v2["worsen_probability"],
                "stable_probability": v2["stable_probability"],
            },
            "sequence_matches": [],
            "failure_warnings": engine.get_failure_lessons(query_fp),
            "failure_warnings": engine.get_failure_lessons(query_fp),
        }
        # Add sequence matches if available
        seq = engine._sequences.get(td)
        if seq:
            result["sequence_matches"] = [{
                "date": dt.isoformat(), "distance": d,
                "path_signature": sig, "similarity_pct": sim,
            } for dt, d, sig, sim in engine.find_similar_sequence(seq, top_n=5)]
            result["query_path"] = seq.path_signature
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M2.5 Phase 3.4: Replay Benchmark ──

@app.get("/api/v1/metrics/replay-benchmark/{trade_date}")
async def get_replay_benchmark(trade_date: str) -> dict[str, Any]:
    """Score AI vs analyst alignment for a trading day (100-point scale).

    L0(50): fact accuracy — limit-up, turnover, height, relay, sealed
    L1(25): state recognition — phase/emotion match
    L2(15): risk recognition — death index + risk level match
    L3(10): strategy alignment — allowed/forbidden match
    """
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.narrative_engine import (
        NarrativeEngine,
    )
    from stock_processing_service.application.services.market_metrics.replay_benchmark import (
        ReplayEngine,
        build_20260707_reference,
    )
    try:
        td = _date.fromisoformat(trade_date)
        snap = await MarketMetricsService().get_async(td)
        story = NarrativeEngine().generate(snap)

        engine = ReplayEngine()
        # Register known reference cases
        if td == _date(2026, 7, 7):
            engine.add_reference(build_20260707_reference())

        result = engine.score_one(snap, story)
        return {
            "trade_date": trade_date,
            "ai": {
                "phase": result.ai_phase,
                "risk": result.ai_risk,
                "death_label": result.ai_death_label,
                "death_index": result.ai_death_index,
                "headline": result.ai_headline,
                "strategy": result.ai_strategy,
            },
            "reference": {
                "phase": result.reference.market_phase,
                "risk": result.reference.risk_level,
                "notes": result.reference.analyst_notes,
            },
            "scores": {
                "l0_facts": result.scores.l0_total,
                "l1_state": result.scores.l1_total,
                "l2_risk": result.scores.l2_total,
                "l3_strategy": result.scores.l3_total,
                "overall": result.scores.overall,
                "grade": result.scores.grade,
            },
            "matches": result.scores.match_details,
            "mismatches": result.scores.mismatch_details,
            "explain": result.explain,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M2.5 Phase 3.4: Calibration Loop ──

@app.get("/api/v1/metrics/calibration/{trade_date}")
async def get_calibration_drift(trade_date: str) -> dict[str, Any]:
    """Compute AI↔Analyst drift for a trading day."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.calibration import (
        CalibrationEngine,
        build_20260707_calibration_ref,
    )
    try:
        td = _date.fromisoformat(trade_date)
        snap = await MarketMetricsService().get_async(td)
        r = snap.relay; l = snap.limitup

        engine = CalibrationEngine()
        if td == _date(2026, 7, 7):
            engine.add_reference(build_20260707_calibration_ref())

        report = engine.compute_drift(
            td,
            ai_facts={"limit_up": l.total_count, "max_board": l.max_board_height,
                       "relay_1_2": r.promotion_1_to_2},
            ai_phase="PANIC", ai_risk="CRITICAL",
            ai_emotion=snap.emotion_momentum.momentum_raw,
        )
        if report is None:
            return {"trade_date": trade_date, "status": "no_reference"}

        proposals = engine.propose_weights(min_evidence=1)

        return {
            "trade_date": trade_date,
            "report": report.to_dict(),
            "weight_proposals": [{
                "target": p.target_component,
                "current": p.current_weight, "proposed": p.proposed_weight,
                "delta": p.delta, "rationale": p.rationale,
                "confidence": p.confidence, "status": p.status,
            } for p in proposals],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── M2.5 Phase 3.5: Calibration Dashboard ──

@app.get("/api/v1/metrics/calibration-dashboard")
async def get_calibration_dashboard() -> dict[str, Any]:
    """Return calibration dashboard: phase accuracy, error attribution, bias trends."""
    from stock_processing_service.application.services.market_metrics.calibration import (
        CalibrationEngine, CalibrationConfig,
        build_20260707_calibration_ref,
    )
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from datetime import date as _date
    try:
        config = CalibrationConfig(window_days=60, min_samples=10, confidence_threshold=0.7)
        engine = CalibrationEngine(config)

        # Register known references
        engine.add_reference(build_20260707_calibration_ref())

        # Run calibration for 7/7
        snap = await MarketMetricsService().get_async(_date(2026, 7, 7))
        r = snap.relay; l = snap.limitup
        engine.compute_drift(
            _date(2026, 7, 7),
            ai_facts={"limit_up": l.total_count, "max_board": l.max_board_height,
                       "relay_1_2": r.promotion_1_to_2},
            ai_phase="PANIC", ai_risk="CRITICAL",
            ai_emotion=snap.emotion_momentum.momentum_raw,
        )
        engine.propose_weights(min_evidence=1)
        return engine.dashboard()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.6.1 Evidence Artifacts ──

@app.get("/api/v1/evidence-artifacts/{trade_date}")
async def get_evidence_artifacts(
    trade_date: str, module: str | None = None
) -> list[dict[str, Any]]:
    """Return evidence artifacts for a trading day, optionally filtered by module."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_cognition.evidence_artifact_service import (
        EvidenceArtifactService,
    )
    try:
        td = _date.fromisoformat(trade_date)
        service = EvidenceArtifactService()
        artifacts = service.list(td, module)

        # Also include auto-generated charts from ChartReproductionEngine
        try:
            from stock_processing_service.application.services.analyst_charts.chart_engine import (
                ChartReproductionEngine,
            )
            engine = ChartReproductionEngine()
            charts = await engine.run_async(td)
            # Convert charts to artifact format
            for c in charts:
                if module and c.get("module") != module:
                    continue
                artifacts.append({
                    "artifact_id": c["chart_id"],
                    "trade_date": c["trade_date"],
                    "artifact_type": "chart",
                    "chart_type": c.get("chart_type", ""),
                    "title": c["title"],
                    "source": "system_generated",
                    "related_module": c["module"],
                    "extracted_metrics": c.get("data", {}),
                    "summary": c.get("interpretation", ""),
                })
        except Exception:
            pass  # chart engine not available

        return artifacts
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.6 Market Emotion Engine ──

@app.get("/api/v1/emotion/{trade_date}")
async def get_market_emotion(trade_date: str) -> dict[str, Any]:
    """Return MarketEmotionState from MarketMetricsSnapshot (M2.5 canonical)."""
    from datetime import date as _date
    from stock_processing_service.application.services.market_metrics.service import (
        MarketMetricsService,
    )
    from stock_processing_service.application.services.market_metrics.narrative_engine import (
        NarrativeEngine,
    )
    try:
        td = _date.fromisoformat(trade_date)
        snap = await MarketMetricsService().get_async(td)
        story = NarrativeEngine().generate(snap)

        b = snap.breadth; l = snap.limitup; r = snap.relay
        c = snap.capital; loss = snap.loss_effect
        leader = snap.leader_evolution; death = snap.high_position_death

        # Reject empty/default snapshots (no actual market data)
        if b.up_count == 0 and b.down_count == 0 and l.total_count == 0:
            raise HTTPException(status_code=404, detail=f"No market data available for {trade_date}")

        # Phase mapping: NarrativeEngine phase → frontend node
        phase_map = {
            "恐慌/冰点": "ICE_POINT", "退潮": "FADE", "分歧": "DIVERGENCE",
            "修复": "REPAIR", "混沌": "CHAOS", "强势": "CLIMAX",
        }
        node = phase_map.get(story.market_phase, "CHAOS")

        # Star ratings (1-5)
        def stars(value: float, thresholds: list[float]) -> int:
            for i, t in enumerate(thresholds):
                if value <= t: return i + 1
            return 5

        return {
            "trade_date": td.isoformat(),
            "emotion_node": node,
            "emotion_desc": story.market_phase,
            "emotion_score": int(snap.emotion_momentum.momentum_normalized),
            "breadth_score": int(snap.emotion_momentum.momentum_normalized),
            "breadth_label": story.market_phase,
            "momentum_score": int(snap.emotion_momentum.momentum_raw),
            "momentum_label": snap.emotion_momentum.momentum_raw,
            "relay_score": int(r.feedback_score),
            "relay_label": r.feedback_label,
            "capital_score": int(c.active_ratio * 1000),
            "capital_label": f"活跃{c.active_limitup_amount_yi:.0f}亿",
            "style_score": death.death_index if death else 0,
            "style_label": death.death_label if death else "N/A",
            "key_evidence": [
                f"涨停 {l.total_count} 家，跌停 {loss.limit_down_count if loss else '?'} 家",
                f"上涨 {b.up_count} / 下跌 {b.down_count}",
                f"活跃资金 {c.active_limitup_amount_yi:.0f}亿",
                f"晋级率 1→2: {r.promotion_1_to_2:.1%}，反馈: {r.feedback_label}",
                f"龙头: {leader.leader_health_label if leader else 'N/A'}，死亡: {death.death_label if death else 'N/A'}",
            ],
            "strategy_bias": story.strategy_summary,
            "raw": {
                "limit_up": l.total_count,
                "limit_down": loss.limit_down_count if loss else 0,
                "up_count": b.up_count,
                "down_count": b.down_count,
                "active_capital_yi": c.active_limitup_amount_yi,
                "promotion_1_to_2": r.promotion_1_to_2,
                "phase": story.market_phase,
                "risk": story.risk_level,
                "confidence": story.confidence.get("overall", 0),
            },
            "confidence": story.confidence.get("overall", 0),
            "generated_at": _date.today().isoformat(),
            "source": "market_metrics_snapshot",
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── P2.5 Analyst Workspace ──

@app.get("/api/v1/analyst-workspace/{trade_date}")
async def get_analyst_workspace(trade_date: str) -> dict[str, Any]:
    """Return full workspace state for a trading day.

    Read-only. Reads from the workbench session store only.
    Does NOT trigger implicit AI generation or connect to the database.

    Priority:
      1. If approved snapshot exists → return it (analyst_finalized=true)
      2. Else if draft exists (DRAFT_READY+) → return draft data (is_ai_draft=true)
      3. Else → return NOT_STARTED + can_generate=true + empty payload
    """
    from datetime import date as _date
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    try:
        td = _date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")

    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _wb_base = _os.path.join(_project_root, "tmp", "analyst_workbench")

    # ── Try snapshot (approved → final analyst view) ──
    snapshot_path = _Path(_wb_base) / trade_date / "snapshot.json"
    if snapshot_path.exists():
        try:
            snap = _json.loads(snapshot_path.read_text(encoding="utf-8"))
            themes = _workspace_themes_from_cards(
                snap.get("cognition_cards", []),
                snap.get("attention_state", {}),
            )
            return {
                "trade_date": trade_date,
                "is_ai_draft": False,
                "analyst_finalized": True,
                "themes": themes,
                "watch_groups": [],
                "override_count": snap.get("override_summary", {}).get("total", 0),
            }
        except Exception:
            pass  # corrupt snapshot → fall through to draft

    # ── Try latest draft ──
    drafts_dir = _Path(_wb_base) / trade_date / "drafts"
    if drafts_dir.exists():
        draft_files = sorted(drafts_dir.glob("draft_v*.json"))
        if draft_files:
            try:
                draft = _json.loads(draft_files[-1].read_text(encoding="utf-8"))
                themes = _workspace_themes_from_cards(
                    draft.get("cognition_cards", []),
                    draft.get("attention_state", {}),
                )
                return {
                    "trade_date": trade_date,
                    "is_ai_draft": True,
                    "analyst_finalized": False,
                    "themes": themes,
                    "watch_groups": [],
                    "override_count": 0,
                    "draft_version": draft.get("draft_version", 0),
                    "source_quality": draft.get("source_quality", 0),
                    "missing_fields": draft.get("missing_fields", []),
                }
            except Exception:
                pass  # corrupt draft → fall through to empty

    # ── Nothing available ──
    return {
        "trade_date": trade_date,
        "is_ai_draft": False,
        "analyst_finalized": False,
        "themes": [],
        "watch_groups": [],
        "override_count": 0,
        "can_generate": True,
    }


def _workspace_themes_from_cards(
    cognition_cards: list[dict],
    attention_state: dict,
) -> list[dict]:
    """Convert workbench cognition_cards into the workspace ThemeEntry format."""
    themes = []
    rank = 0
    for card in cognition_cards:
        name = card.get("subject_name", "") or card.get("name", "")
        if not name:
            continue
        score = card.get("score", 50)
        if rank < 5:
            level = "CRITICAL"
        elif rank < 10:
            level = "HIGH"
        else:
            level = "MEDIUM"
        themes.append({
            "subject_id": f"theme:{name}",
            "subject_name": name,
            "attention_level": level,
            "attention_score": score,
            "attention_reasons": [card.get("state", "")],
            "ai_recommended": True,
            "analyst_added": False,
            "trading_style": "",
            "long_identifiability": 0.5,
            "short_identifiability": 0.3,
            "old_leaders": "",
            "event_stimuli": [],
            "yesterday_view": "",
            "today_actual": "",
            "stage_judgement": card.get("state", ""),
            "intraday_understanding": "",
            "trader_sentiment": "",
            "index_resonance": "",
            "tomorrow_view": "",
            "analyst_notes": "",
            "is_ai_draft": True,
            "analyst_reviewed": False,
            "field_overrides": {},
            "leaders": [],
            "bull_pool": [],
            "bear_pool": [],
        })
        rank += 1
    return themes


@app.post("/api/v1/analyst-workspace/{trade_date}/save")
async def save_analyst_workspace(
    trade_date: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Save workspace state and log all overrides."""
    from datetime import date as _date, datetime as _dt
    import json as _json
    from pathlib import Path as _Path

    try:
        td = _date.fromisoformat(trade_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {trade_date}")

    # Log overrides
    override_count = 0
    log_dir = _Path("tmp/analyst_overrides")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{trade_date}_workspace_overrides.jsonl"

    themes = body.get("themes", [])
    for theme in themes:
        field_overrides = theme.get("field_overrides", {})
        for field_name, change in field_overrides.items():
            if isinstance(change, dict) and change.get("analyst_value") != change.get("ai_value"):
                with open(log_file, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps({
                        "trade_date": trade_date,
                        "subject_id": theme.get("subject_id", ""),
                        "object_type": "cognition_field",
                        "field_name": field_name,
                        "ai_value": str(change.get("ai_value", ""))[:200],
                        "analyst_value": str(change.get("analyst_value", ""))[:200],
                        "override_reason": str(change.get("reason", ""))[:200],
                        "analyst_id": "analyst",
                        "created_at": _dt.now(_tz.utc).isoformat(),
                    }, ensure_ascii=False) + "\n")
                override_count += 1

        # Log stock pool overrides
        for pool_type in ("leaders", "bull_pool", "bear_pool"):
            for stock in theme.get(pool_type, []):
                if stock.get("analyst_modified"):
                    with open(log_file, "a", encoding="utf-8") as fh:
                        fh.write(_json.dumps({
                            "trade_date": trade_date,
                            "subject_id": theme.get("subject_id", ""),
                            "object_type": f"stock_{pool_type}",
                            "field_name": "stock_entry",
                            "ai_value": "",
                            "analyst_value": _json.dumps(stock, ensure_ascii=False),
                            "override_reason": "analyst added/modified stock",
                            "analyst_id": "analyst",
                            "created_at": _dt.now(_tz.utc).isoformat(),
                        }, ensure_ascii=False) + "\n")
                    override_count += 1

    # Save workspace
    save_dir = _Path("tmp/analyst_workspace")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{trade_date}.json"
    save_path.write_text(_json.dumps({
        **body,
        "analyst_finalized": body.get("analyst_finalized", False),
        "is_ai_draft": False,
        "override_count": override_count,
        "saved_at": _dt.now(_tz.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "saved",
        "trade_date": trade_date,
        "themes_saved": len(themes),
        "overrides_recorded": override_count,
    }


# ── Phase 4.5 Analyst Workbench Session API ──

def _get_wb_session_store():
    import os as _os
    from stock_processing_service.application.services.analyst_workbench.session import (
        SessionStore, WorkbenchStatus,
    )
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    return SessionStore(base_dir=_os.path.join(_project_root, "tmp", "analyst_workbench")), WorkbenchStatus


def _get_wb_draft_store():
    import os as _os
    from stock_processing_service.application.services.analyst_workbench.draft import DraftStore
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    return DraftStore(base_dir=_os.path.join(_project_root, "tmp", "analyst_workbench"))


def _get_wb_snapshot_store():
    import os as _os
    from stock_processing_service.application.services.analyst_workbench.snapshot import (
        SnapshotStore, ReviewSnapshot,
    )
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    return SnapshotStore(base_dir=_os.path.join(_project_root, "tmp", "analyst_workbench")), ReviewSnapshot


def _load_saved_analyst_workspace(trade_date: str) -> dict[str, Any] | None:
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    candidates = [
        _Path(_project_root) / "tmp" / "analyst_workspace" / f"{trade_date}.json",
        _Path("tmp") / "analyst_workspace" / f"{trade_date}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


@app.get("/api/v1/analyst-workbench/{trade_date}/session")
async def get_workbench_session(trade_date: str) -> dict[str, Any]:
    """Return workbench session state. Does NOT trigger implicit generation."""
    from datetime import date as _date
    session_store, _ = _get_wb_session_store()
    draft_store = _get_wb_draft_store()
    snapshot_store, _ = _get_wb_snapshot_store()
    td = _date.fromisoformat(trade_date)
    session = session_store.get(td)
    draft_version = draft_store.latest_version(td)
    snapshot = snapshot_store.load(td)
    if draft_version > session.draft_version:
        session.draft_version = draft_version
    if snapshot and snapshot.snapshot_version > session.snapshot_version:
        session.snapshot_version = snapshot.snapshot_version
    return {
        "trade_date": trade_date,
        "status": session.status,
        "draft_version": session.draft_version,
        "snapshot_version": session.snapshot_version,
        "can_generate": session.can_generate,
        "can_review": session.can_review,
        "can_approve": session.can_approve,
        "can_publish": session.can_publish,
        "has_draft": session.has_draft,
        "has_snapshot": session.has_snapshot,
        "created_at": session.created_at,
        "generated_at": session.generated_at,
        "approved_at": session.approved_at,
        # ── Calibration metadata (Phase 4.5.1) ──
        "last_calibrated_at": session.last_calibrated_at,
        "calibration_status": session.calibration_status,
        "calibration_score": session.calibration_score,
        "calibration_grade": session.calibration_grade,
    }


def _update_trend_json(trade_date: str, charts: list[dict]) -> None:
    """Append the latest day data to each trend array in trend.json."""
    import os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    trend_path = Path(_project_root) / "frontend" / "public" / "api" / "analyst-charts" / "trend.json"
    if not trend_path.exists():
        return
    try:
        trend = json.loads(trend_path.read_text())
        # Only append if date not already present
        if trade_date in trend.get("dates", []):
            return
        trend.setdefault("dates", []).append(trade_date)

        # Extract data from charts
        breadth = _safe_get_chart(charts, "market_breadth")
        relay = _safe_get_chart(charts, "relay_ecology")
        capital = _safe_get_chart(charts, "active_capital")
        emotion = _safe_get_chart(charts, "emotion_momentum")

        if breadth:
            trend.setdefault("breadth", []).append({
                "date": trade_date,
                "limit_up": breadth.get("limit_up_count", 0),
                "chain_board": breadth.get("chain_board_count", 0),
                "up_ratio": breadth.get("up_ratio", 0),
            })
        if emotion:
            trend.setdefault("momentum", []).append({
                "date": trade_date,
                "score": emotion.get("emotion_momentum_score", 0),
            })
        if capital:
            trend.setdefault("capital", []).append({
                "date": trade_date,
                "active_amount_yi": capital.get("active_amount_yi", 0),
                "total_amount_yi": capital.get("total_amount_yi", 0),
            })
        if relay:
            trend.setdefault("relay", []).append({
                "date": trade_date,
                "max_height": relay.get("max_board_height", 0),
                "p1to2": relay.get("promotion_1_to_2", 0),
                "p2to3": relay.get("promotion_2_to_3", 0),
                "leaders": [],
            })
        trend_path.write_text(json.dumps(trend, ensure_ascii=False))
    except Exception:
        pass


def _safe_get_chart(charts: list[dict], chart_type: str) -> dict | None:
    for c in charts:
        if c.get("chart_type") == chart_type:
            return c.get("data", {})
    return None


@app.post("/api/v1/analyst-workbench/{trade_date}/generate")
async def generate_workbench_draft(trade_date: str) -> dict[str, Any]:
    """Trigger full AI analysis pipeline: chart + emotion + workbench draft.

    Step 1: Generate charts internally → write to disk
    Step 2: Generate emotion internally → write to disk
    Step 3: Run CLI to build workbench draft from the generated files
    """
    from datetime import date as _date
    import subprocess, sys, os, json as _json_mod
    td = _date.fromisoformat(trade_date)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    steps = []

    # Step 1: Generate & save charts
    try:
        charts = await get_analyst_charts(trade_date)
        chart_dir = Path(project_root) / "frontend" / "public" / "api" / "analyst-charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        (chart_dir / f"{trade_date}.json").write_text(
            _json_mod.dumps(charts, ensure_ascii=False, default=str))
        steps.append("charts")
        _update_trend_json(trade_date, charts)
    except Exception:
        pass

    # Step 2: Generate & save emotion
    try:
        emo = await get_market_emotion(trade_date)
        if emo and emo.get("emotion_node"):
            emo_dir = Path(project_root) / "frontend" / "public" / "api"
            emo_dir.mkdir(parents=True, exist_ok=True)
            (emo_dir / f"emotion-{trade_date}.json").write_text(
                _json_mod.dumps(emo, ensure_ascii=False, default=str))
            steps.append("emotion")
    except Exception:
        pass

    # Step 3: Run workbench CLI (reads chart+emotion from disk, no HTTP needed)
    script = os.path.join(project_root, "scripts", "generate_analyst_workbench.py")
    cli_failed = False
    cli_error = None
    try:
        result = subprocess.run(
            [sys.executable, script, "--date", trade_date],
            capture_output=True, text=True, timeout=120,
            cwd=project_root,
            env={**os.environ, "SPS_SKIP_FETCH": "1"},  # skip HTTP fetch in CLI
        )
        if result.returncode == 0:
            steps.append("workbench")
        else:
            cli_failed = True
            cli_error = (result.stderr or result.stdout or "").strip()[-300:]
    except Exception as e:
        cli_failed = True
        cli_error = str(e)

    session_store, _ = _get_wb_session_store()
    draft_store = _get_wb_draft_store()
    session = session_store.get(td)
    draft = draft_store.load(td) if session.draft_version > 0 else None

    # Determine truthful status
    if cli_failed:
        status = "failed"
    elif draft and draft.missing_fields:
        status = "partial"
    elif "workbench" in steps:
        status = "completed"
    else:
        status = "partial"

    return {
        "job_id": f"local_{trade_date}",
        "status": status,
        "steps_completed": steps,
        "session_status": session.status,
        "draft_version": session.draft_version,
        "error": cli_error,
        "missing_fields": draft.missing_fields if draft else [],
        "source_quality": draft.source_quality if draft else 0,
    }


@app.post("/api/v1/analyst-workbench/{trade_date}/save-review")
async def save_workbench_review(trade_date: str, body: dict[str, Any] = None) -> dict[str, Any]:
    """Save analyst review with overrides."""
    from datetime import date as _date, datetime as _dt
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    session_store, WorkbenchStatus = _get_wb_session_store()
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    td = _date.fromisoformat(trade_date)
    session = session_store.get(td)
    if session.status == WorkbenchStatus.PUBLISHED:
        return {"status": "error", "error": "Cannot review PUBLISHED session. Mark STALE first."}
    body = body or {}
    overrides = body.get("overrides", {})
    if overrides:
        d = _Path(_project_root) / "tmp" / "analyst_workbench" / trade_date
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "overrides.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps({"trade_date": trade_date, "timestamp": _dt.now(_tz.utc).isoformat(), "overrides": overrides}, ensure_ascii=False) + "\n")
    if session.status in (WorkbenchStatus.DRAFT_READY, WorkbenchStatus.IN_REVIEW):
        session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    return {"status": "saved", "session_status": session.status, "overrides_recorded": len(overrides)}


@app.post("/api/v1/analyst-workbench/{trade_date}/approve")
async def approve_workbench(trade_date: str, body: dict[str, Any] = None) -> dict[str, Any]:
    """Create approved ReviewSnapshot."""
    from datetime import date as _date
    from stock_processing_service.application.services.analyst_workbench.review_merger import (
        AnalystReviewMerger,
    )
    session_store, WorkbenchStatus = _get_wb_session_store()
    draft_store = _get_wb_draft_store()
    snapshot_store, ReviewSnapshot = _get_wb_snapshot_store()
    td = _date.fromisoformat(trade_date)
    session = session_store.get(td)
    if not session.can_approve:
        return {"status": "error", "error": f"Cannot approve from status {session.status}"}
    draft = draft_store.load(td)
    if draft is None:
        return {"status": "error", "error": "No draft found to approve"}
    body = body or {}
    workspace = _load_saved_analyst_workspace(trade_date)
    merged = AnalystReviewMerger().merge(
        draft=draft,
        workspace=workspace,
        overrides=body.get("overrides", {}),
    )
    snapshot = ReviewSnapshot.from_merged(
        trade_date=td,
        draft=draft,
        merged=merged,
        snapshot_version=session.snapshot_version + 1,
        approved_by=body.get("approved_by", "analyst"),
    )
    snapshot_store.save(snapshot)
    session = session_store.transition(session, WorkbenchStatus.APPROVED, snapshot_version=snapshot.snapshot_version, approved_by=snapshot.approved_by)
    return {
        "status": "approved",
        "session_status": session.status,
        "snapshot_version": session.snapshot_version,
        "based_on_draft_version": draft.draft_version,
        "snapshot_hash": snapshot.snapshot_hash,
        "merged_workspace": workspace is not None,
    }


@app.post("/api/v1/analyst-workbench/{trade_date}/publish")
async def publish_workbench(trade_date: str) -> dict[str, Any]:
    """Publish approved workbench."""
    from datetime import date as _date
    session_store, WorkbenchStatus = _get_wb_session_store()
    snapshot_store, _ = _get_wb_snapshot_store()
    td = _date.fromisoformat(trade_date)
    session = session_store.get(td)
    snapshot = snapshot_store.load(td)
    if not session.can_publish:
        return {"status": "error", "error": f"Cannot publish from status {session.status}"}
    if snapshot is None:
        return {"status": "error", "error": "No approved snapshot exists"}
    session = session_store.transition(session, WorkbenchStatus.PUBLISHED)
    return {"status": "published", "session_status": session.status, "published_at": session.published_at}


# ── Phase 4.5.2 Report Composer Approval Gate ──

def _get_approval_gate():
    import os as _os
    from stock_processing_service.application.services.analyst_workbench.approval_gate import ApprovalGate
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    return ApprovalGate(base_dir=_os.path.join(_project_root, "tmp", "analyst_workbench"))


@app.get("/api/v1/analyst-workbench/{trade_date}/report-approval")
async def check_report_approval(trade_date: str) -> dict[str, Any]:
    """Check whether a formal report can be composed for this trade date.

    Returns:
      mode: "preview" | "formal" | "published"
      can_generate_report: bool
      snapshot_version, approved_at, approved_by: metadata if available
      reason: human-readable explanation
    """
    from datetime import date as _date
    gate = _get_approval_gate()
    td = _date.fromisoformat(trade_date)
    approval = gate.check(td)
    return {
        "trade_date": trade_date,
        "mode": approval.mode,
        "session_status": approval.session_status,
        "can_generate_report": approval.can_generate_report,
        "snapshot_version": approval.snapshot_version,
        "approved_at": approval.approved_at,
        "approved_by": approval.approved_by,
        "reason": approval.reason,
    }


async def _check_workbench_approval(trade_date: date) -> dict[str, Any]:
    """Lightweight, non-throwing workbench approval check for enriching reports."""
    gate = _get_approval_gate()
    approval = gate.check(trade_date)
    return {
        "mode": approval.mode,
        "can_generate_formal_report": approval.can_generate_report,
        "snapshot_version": approval.snapshot_version,
        "approved_at": approval.approved_at,
        "approved_by": approval.approved_by,
        "based_on_draft_version": (
            approval.snapshot.based_on_draft_version if approval.snapshot else 0
        ),
        "session_status": approval.session_status,
        "reason": approval.reason,
    }


def _enrich_v2_with_workbench_sections(v2: dict[str, Any], trade_date: date) -> dict[str, Any]:
    """Inject workbench section content into the DailyReview V2 response.

    Priority: approved snapshot > latest draft.
    Only injects fields that are not already present in v2.
    """
    import json, os as _os
    from pathlib import Path as _Path

    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _wb_base = _Path(_project_root) / "tmp" / "analyst_workbench" / trade_date.isoformat()

    # ── Prefer newer source: snapshot (immutable) or draft (latest calibration) ──
    snap_path = _wb_base / "snapshot.json"
    drafts_dir = _wb_base / "drafts"
    draft_path = None
    if drafts_dir.exists():
        draft_files = sorted(drafts_dir.glob("draft_v*.json"))
        if draft_files:
            draft_path = draft_files[-1]

    snap_mtime = snap_path.stat().st_mtime if snap_path.exists() else 0
    draft_mtime = draft_path.stat().st_mtime if draft_path else 0

    # Use newer of snapshot vs draft
    if draft_mtime > snap_mtime and draft_path:
        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            return _inject_sections(v2, draft)
        except Exception:
            pass

    if snap_path.exists():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            return _inject_sections(v2, snap)
        except Exception:
            pass

    # Fallback: older draft still beats nothing
    if draft_path:
        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            return _inject_sections(v2, draft)
        except Exception:
            pass

    return v2


def _inject_sections(v2: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Inject workbench section fields from source into v2, preserving existing values."""
    # Map source keys → v2 keys (some are the same, some differ)
    mappings = [
        ("emotion_review", "emotion_review"),
        ("chart_reviews", "market_chart_reviews"),
        ("attention_state", "attention_review"),
        ("cognition_cards", "cognition_reviews"),
        ("narrative", "narrative_review"),
        ("playbook", "playbook_review"),
        ("override_summary", "analyst_override_review"),
    ]
    for src_key, v2_key in mappings:
        # Only inject if not already set by compose-from-workbench
        if v2_key not in v2 or not v2.get(v2_key):
            val = source.get(src_key)
            if val is not None and val != [] and val != {}:
                v2[v2_key] = val

    # Also inject workbench_data if not present
    if "workbench_data" not in v2:
        v2["workbench_data"] = {
            "attention_state": source.get("attention_state", {}),
            "cognition_cards": source.get("cognition_cards", []),
            "narrative": source.get("narrative", {}),
            "playbook": source.get("playbook", {}),
            "override_summary": source.get("override_summary", {}),
            "emotion_review": source.get("emotion_review", {}),
            "chart_reviews": source.get("chart_reviews", []),
        }

    return v2


@app.post("/api/v2/daily-review-v2/compose-from-workbench")
async def compose_daily_review_from_workbench(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compose a formal DailyReview V2 gated by workbench approval.

    Requires an APPROVED or PUBLISHED workbench snapshot.
    Reads the existing recap_doc from post_market_recap_snapshot as evidence
    base, enriches it with workbench snapshot data, and composes the report.

    Returns 409 Conflict if no approved snapshot exists.
    """
    from datetime import date as _date
    p = payload or {}
    trade_date_str = p.get("trade_date") or p.get("date")
    if not trade_date_str:
        raise HTTPException(status_code=400, detail="trade_date is required")
    try:
        d = _date.fromisoformat(trade_date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid date: {trade_date_str}")

    # ── Gate: require formal approval ──
    from stock_processing_service.application.services.analyst_workbench.report_composer import (
        WorkbenchReportComposer,
    )
    import os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    wb_composer = WorkbenchReportComposer(
        workbench_base_dir=_os.path.join(_project_root, "tmp", "analyst_workbench"),
    )

    try:
        approval = wb_composer.require_formal(d)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    # ── Load recap_doc from post_market_recap_snapshot ──
    from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
        PostMarketDailyReviewV2Builder,
    )
    builder = PostMarketDailyReviewV2Builder()
    row = await _fetch_latest_post_market_recap_snapshot_row(d)
    recap_doc: dict[str, Any] = {}
    if row:
        payload_data = _normalize_recap_payload(row)
        recap_doc = payload_data.get("recap_doc") or payload_data
        if not isinstance(recap_doc, dict):
            recap_doc = {}

    # ── Compose from workbench ──
    result = wb_composer.compose(d, recap_doc)

    # ── Build DailyReviewV2 structure around the composed report ──
    v2 = builder.build(
        trade_date=d,
        recap_doc=recap_doc,
        recap_snapshot_version=str(row.get("snapshot_version") or "") if row else "",
    )
    v2 = {**v2, **result.report}

    v2 = await _enrich_v2_theme_names(v2, d)
    v2["watchlists"] = await _build_one_to_two_watchlists(d)
    v2 = _trim_daily_review_v2_response(v2)

    return v2


# ── Phase 4.5.5.2 Analyst Reference Import ──

@app.post("/api/v1/analyst-reference/import")
async def import_analyst_reference(body: dict[str, Any]) -> dict[str, Any]:
    """Import analyst recap markdown content into the reference store.

    Body:
      trade_date: str   — YYYY-MM-DD
      content: str      — markdown file content (DeepSeek structured format)

    Returns parsed record summary + extraction quality.
    After import, the reference is available for alignment/calibration.
    """
    from datetime import date as _date
    import os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    reference_dir = _os.path.join(_project_root, "tmp", "analyst_reference")

    td_str = body.get("trade_date", "")
    if not td_str:
        raise HTTPException(status_code=400, detail="trade_date is required")
    try:
        td = _date.fromisoformat(td_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {td_str}")

    content = body.get("content", "")
    if not content or len(content.strip()) < 50:
        raise HTTPException(status_code=400, detail="content is required (min 50 chars of markdown)")

    from stock_processing_service.application.services.analyst_reference.markdown_ingestion import (
        MarkdownReferenceParser,
    )
    from stock_processing_service.application.services.analyst_reference.store import (
        AnalystReferenceStore,
    )

    import tempfile
    # ── Pre-validation: warn only on severe issues, let parser decide ──
    validation_issues: list[str] = []

    if len(content) < 100:
        validation_issues.append(f"内容过短（{len(content)} 字符），可能缺少完整复盘数据。")

    # ── Parse markdown ──
    try:
        # Write content to temp file for MarkdownReferenceParser
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        parser = MarkdownReferenceParser()
        record = parser.parse_file(tmp_path, trade_date=td)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Markdown 解析失败: {e}")
    finally:
        try:
            _os.unlink(tmp_path)
        except Exception:
            pass

    # ── Post-validation: extraction quality ──
    quality = record.quality
    extraction_status = (
        quality.extraction_status.value
        if hasattr(quality.extraction_status, 'value') else str(quality.extraction_status)
    )
    core_coverage = quality.required_field_coverage if hasattr(quality, 'required_field_coverage') else 0.0
    full_coverage = quality.optional_field_coverage if hasattr(quality, 'optional_field_coverage') else 0.0
    missing = list(quality.missing_fields) if quality.missing_fields else []
    low_conf = list(quality.low_confidence_fields) if quality.low_confidence_fields else []

    # Quality gate: require FULL extraction — all-or-nothing
    if extraction_status not in ("full_complete", "core_complete"):
        raise HTTPException(
            status_code=422,
            detail=f"数据提取不完整（extraction_status={extraction_status}）。"
                   f"核心覆盖率: {core_coverage:.0%}。"
                   f"缺失字段: {missing[:10] if missing else '无'}。"
                   f"请确认 .md 文件包含完整的 DeepSeek 结构化 JSON 数据。",
        )
    if core_coverage < 1.0:
        raise HTTPException(
            status_code=422,
            detail=f"核心字段缺失（覆盖率 {core_coverage:.0%}，要求 100%）。"
                   f"缺失: {missing[:10] if missing else '无'}。"
                   f"请补充缺失字段后重新导入。",
        )
    if full_coverage < 0.5:
        raise HTTPException(
            status_code=422,
            detail=f"完整字段覆盖率不足（{full_coverage:.0%}，要求至少 50%）。"
                   f"缺失: {missing[:10] if missing else '无'}。",
        )

    # ── Store ──
    try:
        store = AnalystReferenceStore(base_dir=reference_dir)
        content_hash = store.append(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"存储失败: {e}")

    return {
        "status": "imported",
        "trade_date": td_str,
        "content_hash": content_hash,
        "extraction_status": extraction_status,
        "coverage": {"core_coverage": core_coverage, "full_coverage": full_coverage},
        "missing_fields": missing,
        "low_confidence_fields": low_conf,
        "validation_issues": validation_issues,
        "market_phase": record.emotion_label.market_phase or "",
        "risk_level": record.emotion_label.risk_level or "",
        "emotion_momentum": record.emotion_label.emotion_momentum,
        "strategy": record.emotion_label.strategy or record.strategy_label.summary or "",
        "limit_up_count": record.market_facts.limit_up_count,
        "max_board_height": record.market_facts.max_board_height,
        "active_capital_yi": record.market_facts.active_capital_yi,
    }


# ── Phase 4.5.6 Calibration Comparison ──

@app.get("/api/v1/analyst-workbench/{trade_date}/comparison")
async def get_ai_analyst_comparison(trade_date: str) -> dict[str, Any]:
    """Return AI vs Analyst side-by-side comparison for each dimension."""
    from datetime import date as _date
    import os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    td = _date.fromisoformat(trade_date)

    # Load AI draft
    draft_store = _get_wb_draft_store()
    draft = draft_store.load(td)

    # Load analyst reference
    from stock_processing_service.application.services.analyst_reference.store import (
        AnalystReferenceStore,
    )
    ref_dir = _os.path.join(_project_root, "tmp", "analyst_reference")
    ref_store = AnalystReferenceStore(base_dir=ref_dir)
    ref = ref_store.get_by_date(td)

    # Build comparison rows
    cal = (draft.calibration if draft else {}) or {}
    scores = cal.get("component_scores", {})

    # AI values
    emo = (draft.emotion_review if draft else {}) or {}
    ai_phase = emo.get("emotion_node", "")
    ai_risk = emo.get("risk_level", "")
    ai_strategy = emo.get("strategy_bias", "")
    ai_limit_up = emo.get("key_metrics", {}).get("limit_up_count", "—")

    # Analyst values
    if ref:
        an_phase = ref.emotion_label.market_phase or ""
        an_risk = ref.emotion_label.risk_level or ""
        an_strategy = ref.emotion_label.strategy or ref.strategy_label.summary or ""
        an_limit_up = ref.market_facts.limit_up_count
    else:
        an_phase = an_risk = an_strategy = ""
        an_limit_up = None

    # Chinese label map
    PHASE_CN: dict[str, str] = {
        "REBOUND": "修复反弹", "CLIMAX": "高潮", "ACCELERATION": "加速",
        "FERMENTATION": "发酵", "DIVERGENCE": "退潮分歧", "FADE": "衰退",
        "ICE_POINT": "冰点", "CHAOS": "混沌", "REPAIR_WATCH": "观察修复",
        "PANIC": "恐慌", "FREEZE": "冻结", "DISTRIBUTION": "派发",
    }

    RISK_CN: dict[str, str] = {
        "LOW": "低风险", "MEDIUM": "中等风险", "MEDIUM_HIGH": "中高风险",
        "HIGH": "高风险", "EXTREME": "极高风险", "CRITICAL": "危险",
    }

    def cn_phase(v: str) -> str:
        return PHASE_CN.get(v, v or "—")

    def cn_risk(v: str) -> str:
        return RISK_CN.get(v, v or "—")

    rows = [
        {
            "key": "phase", "label": "市场阶段",
            "ai_value": cn_phase(ai_phase),
            "analyst_value": cn_phase(an_phase),
            "score": scores.get("phase", 0),
        },
        {
            "key": "risk", "label": "风险等级",
            "ai_value": cn_risk(ai_risk) or "—",
            "analyst_value": cn_risk(an_risk) or "—",
            "score": scores.get("risk", 1),
        },
        {
            "key": "facts", "label": "市场事实",
            "ai_value": f"涨停 {ai_limit_up}" if ai_limit_up != "—" else "—",
            "analyst_value": f"涨停 {an_limit_up}" if an_limit_up else "—",
            "score": scores.get("facts", 0),
        },
        {
            "key": "relay", "label": "接力生态",
            "ai_value": emo.get("relay_label", "—"),
            "analyst_value": "—",
            "score": scores.get("relay", 0),
        },
        {
            "key": "strategy", "label": "交易策略",
            "ai_value": (ai_strategy or "—")[:50],
            "analyst_value": (an_strategy or "—")[:50],
            "score": scores.get("strategy", 0),
        },
        {
            "key": "theme_leader", "label": "题材龙头",
            "ai_value": "—",
            "analyst_value": "—",
            "score": scores.get("theme_leader", 0),
        },
    ]

    return {
        "trade_date": trade_date,
        "rows": rows,
        "overall_score": cal.get("overall_score", 0),
        "grade": cal.get("grade", ""),
        "has_reference": ref is not None,
    }


# ── Phase 4.5.6 Apply Calibration Corrections ──

@app.post("/api/v1/analyst-workbench/{trade_date}/apply-calibration")
async def apply_calibration_to_draft(trade_date: str) -> dict[str, Any]:
    """Apply calibration corrections to the latest draft.

    Reads the analyst reference data and calibration results, then
    updates the draft's emotion_review with analyst-confirmed values.
    Only applies corrections where calibration confidence is high.
    """
    from datetime import date as _date
    import os as _os, json, json as _json_mod
    from pathlib import Path
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    td = _date.fromisoformat(trade_date)

    # Load draft
    draft_store = _get_wb_draft_store()
    draft = draft_store.load(td)
    if draft is None:
        raise HTTPException(status_code=409, detail="No draft exists. Generate first.")

    # Load calibration
    calibration = draft.calibration or {}
    component_scores = calibration.get("component_scores", {})

    # Load analyst reference
    from stock_processing_service.application.services.analyst_reference.store import (
        AnalystReferenceStore,
    )
    ref_dir = _os.path.join(_project_root, "tmp", "analyst_reference")
    ref_store = AnalystReferenceStore(base_dir=ref_dir)
    ref_record = ref_store.get_by_date(td)

    applied: list[str] = []

    emo = dict(draft.emotion_review) if draft.emotion_review else {}

    if ref_record is not None:
        # Phase correction
        analyst_phase = ref_record.emotion_label.market_phase or ""
        if analyst_phase and component_scores.get("phase", 0) < 0.5:
            old_phase = emo.get("emotion_node", "")
            if old_phase != analyst_phase:
                emo["emotion_node"] = analyst_phase
                emo["analyst_adjustment"] = {
                    "modified": True,
                    "from": old_phase,
                    "to": analyst_phase,
                    "reason": f"校准修正: phase 偏差 ({component_scores.get('phase', 0):.0%} 匹配)",
                }
                applied.append(f"emotion_node: {old_phase} → {analyst_phase}")

        # Strategy correction
        analyst_strategy = ref_record.emotion_label.strategy or ref_record.strategy_label.summary or ""
        if analyst_strategy and component_scores.get("strategy", 0) < 0.5:
            old_strategy = emo.get("strategy_bias", "")
            if old_strategy != analyst_strategy:
                emo["strategy_bias"] = analyst_strategy
                applied.append(f"strategy_bias: {old_strategy[:20]} → {analyst_strategy[:20]}")

        # Risk correction (only if mismatch, but risk usually aligns)
        analyst_risk = ref_record.emotion_label.risk_level or ""
        if analyst_risk and component_scores.get("risk", 1) < 0.8:
            old_risk = emo.get("risk_level", "")
            if old_risk != analyst_risk:
                emo["risk_level"] = analyst_risk
                applied.append(f"risk_level: {old_risk} → {analyst_risk}")

    else:
        applied.append("(no analyst reference data available)")

    # Extract tomorrow watchpoints from analyst reference
    if ref_record is not None:
        emo["tomorrow_watchpoints"] = list(ref_record.strategy_label.watch_points or [])
        emo["tomorrow_forbidden"] = list(ref_record.strategy_label.forbidden or [])
        emo["tomorrow_outlook"] = ref_record.strategy_label.summary or ""

    # Save updated draft
    draft.emotion_review = emo
    draft_store.save(draft)

    # Also update static emotion JSON so EmotionDashboard reflects changes
    emo_path = Path(_project_root) / "frontend" / "public" / "api" / f"emotion-{trade_date}.json"
    if emo_path.exists():
        try:
            static_emo = json.loads(emo_path.read_text(encoding="utf-8"))
            if emo.get("emotion_node"):
                static_emo["emotion_node"] = emo["emotion_node"]
            if emo.get("strategy_bias"):
                static_emo["strategy_bias"] = emo["strategy_bias"]
            if emo.get("risk_level"):
                static_emo["risk_level"] = emo.get("risk_level", static_emo.get("risk_level", ""))
            emo_path.write_text(_json_mod.dumps(static_emo, ensure_ascii=False, default=str))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to update static emotion JSON: {e}")

    return {
        "status": "applied",
        "corrections": applied,
        "emotion_node": emo.get("emotion_node", ""),
        "strategy_bias": emo.get("strategy_bias", ""),
        "risk_level": emo.get("risk_level", ""),
    }


# ── Phase 4.5.1 Calibration Persistence ──

@app.post("/api/v1/analyst-workbench/{trade_date}/calibrate")
async def calibrate_workbench_draft(trade_date: str, body: dict[str, Any] = None) -> dict[str, Any]:
    """Persist calibration result into the latest draft and session metadata.

    Body should contain the Turing Score payload from run_analyst_alignment:
      { overall_score, grade, component_scores, calibration_hints, ... }
    """
    from datetime import date as _date
    session_store, _ = _get_wb_session_store()
    td = _date.fromisoformat(trade_date)
    body = body or {}

    try:
        session = session_store.apply_calibration(td, body)
        return {
            "status": "calibrated",
            "session_status": session.status,
            "calibration_score": session.calibration_score,
            "calibration_grade": session.calibration_grade,
            "calibrated_at": session.last_calibrated_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Phase 4.5 Analyst Alignment Quick Compare ──

@app.post("/api/v1/analyst-alignment/{trade_date}")
async def run_analyst_alignment_for_date(trade_date: str, body: dict[str, Any] = None) -> dict[str, Any]:
    """Run AI↔Analyst alignment for a single date.

    Requires:
    - AI chart JSON at frontend/public/api/analyst-charts/{date}.json
    - Emotion JSON at frontend/public/api/emotion-{date}.json
    - Analyst reference in configured reference dir

    Reference dir resolution (in priority order):
      1. Body field: { "reference_dir": "tmp/analyst_reference" }
      2. Env var: ANALYST_REFERENCE_DIR
      3. Default: tmp/analyst_reference
    """
    import subprocess, sys as _sys, os as _os, json
    from pathlib import Path as _Path
    body = body or {}
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    reference_dir = _os.path.join(
        _project_root,
        body.get("reference_dir")
        or _os.environ.get("ANALYST_REFERENCE_DIR")
        or "tmp/analyst_reference",
    )
    output_dir = _os.path.join(_project_root, f"tmp/analyst_alignment_{trade_date}")
    # Force fresh re-run: remove any stale output from previous calibration
    import shutil
    if _os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    script = _os.path.join(_project_root, "scripts", "run_analyst_alignment.py")
    chart_dir = _os.path.join(_project_root, "frontend", "public", "api", "analyst-charts")
    result = subprocess.run(
        [_sys.executable, script,
         "--start", trade_date, "--end", trade_date,
         "--reference-dir", reference_dir,
         "--ai-source", "charts",
         "--ai-chart-dir", chart_dir,
         "--output", output_dir],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode != 0:
        return {"status": "error", "error": result.stderr.strip()[-300:]}
    # Read the daily turing score
    ts_path = _Path(output_dir) / "daily" / f"{trade_date}.turing.json"
    if ts_path.exists():
        ts = json.loads(ts_path.read_text())
        return {
            "status": "completed",
            "trade_date": trade_date,
            "overall_score": ts["scores"]["overall"],
            "grade": ts["grade"],
            "component_scores": {
                "phase": ts["scores"]["phase"],
                "risk": ts["scores"]["risk"],
                "facts": ts["scores"]["facts"],
                "relay": ts["scores"]["relay"],
                "strategy": ts["scores"]["strategy"],
                "theme_leader": ts["scores"]["theme_leader"],
            },
            "calibration_hints": ts.get("calibration_hints", []),
        }
    return {"status": "completed", "trade_date": trade_date, "note": "No reference available for comparison"}


@app.get("/api/v1/leaders/{theme_name}")
async def get_theme_leaders(
    theme_name: str,
    trade_date: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return leader scores for a specific theme."""
    try:
        from asyncpg import connect as _pg_connect
        db = os.environ.get("PG_DATABASE", "stock_data_test")
        conn = await _pg_connect(
            host="localhost", port=5432, database=db,
            user=os.environ.get("PG_USERNAME", "postgres"),
            password=os.environ.get("PG_PASSWORD", ""),
        )
        try:
            if trade_date:
                rows = await conn.fetch(
                    "SELECT stock_code, stock_name, leader_score, event_score, "
                    "expectation_score, resonance_score, board_strength_score, "
                    "rank_in_theme, evidence_sources "
                    "FROM leader_score_snapshot "
                    "WHERE trade_date = $1::date AND theme_name = $2 "
                    "ORDER BY rank_in_theme LIMIT $3",
                    trade_date, theme_name, min(limit, 20),
                )
            else:
                rows = await conn.fetch(
                    "SELECT stock_code, stock_name, leader_score, event_score, "
                    "expectation_score, resonance_score, board_strength_score, "
                    "rank_in_theme, evidence_sources, trade_date "
                    "FROM leader_score_snapshot "
                    "WHERE theme_name = $1 "
                    "ORDER BY trade_date DESC, rank_in_theme "
                    "LIMIT $2",
                    theme_name, min(limit, 20),
                )
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
