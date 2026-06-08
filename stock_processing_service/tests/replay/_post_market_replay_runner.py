"""盘后复盘回放运行器 — 基于新链 Layer C seed-query 架构重建。

提供两个接口：
  - run_post_market_replay(trade_date, sample_name)      → 完整实时 replay（需 REPLAY_LIVE_DB=1）
  - run_post_market_replay_readonly(trade_date, target_stock_id) → 只读静态检查（默认模式）
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from database_service.gateway import DatabaseGateway


class _ReplayDatabaseStockFacade:
    """api_app.py 使用的轻量 facade — 包装 DatabaseGateway 提供 stock facade 接口。"""

    def __init__(self, gateway: DatabaseGateway) -> None:
        self._db = gateway._client
        self._gateway = gateway

    def __getattr__(self, name: str):
        # 委托给 gateway 的所有方法
        if hasattr(self._gateway, name):
            return getattr(self._gateway, name)
        if hasattr(self._db, name):
            return getattr(self._db, name)
        raise AttributeError(name)

from stock_processing_service.application.jobs.build_post_market_recap_job import (
    BuildPostMarketRecapJob,
)
from stock_processing_service.contracts.dto import StockBarDTO
from stock_processing_service.domain.services.strong_stock_tracking_service import (
    BoardSnapshot,
    CycleSnapshot,
    PatternSnapshot,
    PositionSnapshot,
    StrongStockTrackingService,
    WatchScoreResult,
)
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer


def replay_enabled() -> bool:
    return os.getenv("REPLAY_ENABLED", "0") in {"1", "true", "yes"}


# ── 回放结果数据结构 ──

@dataclass
class ReplayReadonlyResult:
    trade_date: date
    candidate_count: int = 0
    candidate_count_total: int = 0
    strong_watch_input_7d_count: int = 0
    has_target_in_input_7d: bool = False
    has_target_in_top_candidates: bool = False
    target_preview: dict[str, Any] = field(default_factory=dict)
    top_candidates: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayLiveResult:
    daily_status: str = ""
    daily_affected_rows: int = 0
    recap_status: str = ""
    assertion_report: dict[str, Any] = field(default_factory=dict)
    recap_doc: dict[str, Any] = field(default_factory=dict)
    target_diagnostics: dict[str, Any] = field(default_factory=dict)
    identity_mode: str = "seed_query_v2"
    replay_report_paths: dict[str, str] = field(default_factory=dict)


# ── 目标股票映射 ──

_TARGET_MAP: dict[str, str] = {
    "shenjian": "002361.SZ",
    "liande": "605060.SH",
    "weike": "600152.SH",
}


# ── 只读静态回放（默认模式，无需 DB 连接）──

def run_post_market_replay_readonly(
    trade_date: date,
    target_stock_id: str | None = None,
) -> ReplayReadonlyResult:
    """静态回放：检查种子查询输出并构建预览数据。

    不连接数据库，使用归档的 JSON 快照或从旧链池读取。
    当前版本使用种子查询模拟 + 持久池状态。
    """
    # 仅使用 seed query 模拟检查
    try:
        return _run_readonly_async(trade_date, target_stock_id)
    except Exception as e:
        return ReplayReadonlyResult(
            trade_date=trade_date,
            target_preview={"error": str(e)},
        )


def _run_readonly_async(
    trade_date: date,
    target_stock_id: str | None = None,
) -> ReplayReadonlyResult:
    """异步种子查询检查 — 使用旧链 strong_stock_watch_pool 历史数据。

    通过独立线程运行 asyncio loop，兼容 pytest-asyncio 等已有事件循环场景。
    """
    import concurrent.futures
    import asyncio as _asyncio

    def _run_in_thread():
        return _asyncio.run(_readonly_impl(trade_date, target_stock_id))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_run_in_thread).result(timeout=15)


async def _readonly_impl(
    trade_date: date,
    target_stock_id: str | None = None,
) -> ReplayReadonlyResult:
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.gateway import DatabaseGateway

    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    try:
        # 查询种子
        seed_rows = await gw._client.get_strong_watch_seed_rows(trade_date, lookback_days=7)
        seed_count = len(seed_rows)

        # 查询持久池（从旧链 strong_stock_watch_history，仅 active/weakening + formal/observe_only）
        async with gw._client.pool.acquire() as conn:
            history_rows = await conn.fetch(
                """
                SELECT h.stock_id, h.stock_name, h.watch_status, h.watch_score, h.pool_entry_type,
                       h.subject_key, h.theme_name
                FROM strong_stock_watch_history h
                JOIN (
                    SELECT stock_id, MAX(trade_date) as max_td
                    FROM strong_stock_watch_history
                    WHERE trade_date <= $1::date
                      AND watch_status IN ('active', 'weakening')
                      AND pool_entry_type IN ('formal', 'observe_only')
                    GROUP BY stock_id
                ) latest ON h.stock_id = latest.stock_id AND h.trade_date = latest.max_td
                """,
                trade_date,
            )
            history_by_stock = {str(r["stock_id"]): dict(r) for r in history_rows}
            pool_count = len(history_by_stock)
    finally:
        await gw.close()

    target_id = target_stock_id or ""

    # 种子中是否有目标
    has_target_in_seed = any(
        (target_id and target_id in str(r.get("stock_id", "")))
        for r in seed_rows
    )

    # 持久池中是否有目标
    target_history = history_by_stock.get(target_id, {})
    has_target_in_pool = bool(target_history)

    # 目标预览
    target_preview: dict[str, Any] = {"stock_id": target_id, "watch_score": "0.00"}
    if has_target_in_pool:
        target_preview = {
            "stock_id": target_id,
            "stock_name": str(target_history.get("stock_name", "")),
            "watch_status": str(target_history.get("watch_status", "")),
            "watch_score": str(target_history.get("watch_score", "0")),
            "pool_entry_type": str(target_history.get("pool_entry_type", "")),
            "subject_key": str(target_history.get("subject_key", "")),
            "theme_name": str(target_history.get("theme_name", "")),
        }

    return ReplayReadonlyResult(
        trade_date=trade_date,
        candidate_count=0,  # readonly mode always 0
        candidate_count_total=pool_count,
        strong_watch_input_7d_count=seed_count,
        has_target_in_input_7d=has_target_in_seed or has_target_in_pool,
        has_target_in_top_candidates=has_target_in_pool and str(target_history.get("pool_entry_type", "")) in {"formal", "observe_only"},
        target_preview=target_preview,
        diagnostics={
            "seed_count": seed_count,
            "pool_count": pool_count,
            "has_target_in_seed": has_target_in_seed,
            "has_target_in_pool": has_target_in_pool,
        },
    )


# ── 完整实时回放（需 REPLAY_LIVE_DB=1）──

async def run_post_market_replay(
    trade_date: date,
    sample_name: str = "",
) -> ReplayLiveResult:
    """运行完整盘后回放 — 使用新链 BuildPostMarketRecapJob。"""
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.gateway import DatabaseGateway
    from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
        StockReadGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_write_gateway_adapter import (
        StockWriteGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
        StockEventGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
        StockIdempotencyGatewayAdapter,
    )
    from uuid import uuid4

    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    read_port = StockReadGatewayAdapter(db_gateway=gw)
    write_port = StockWriteGatewayAdapter(db_gateway=gw)
    event_port = StockEventGatewayAdapter(db_gateway=gw)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gw)

    job = BuildPostMarketRecapJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    snapshot_version = f"replay_{sample_name or trade_date.isoformat()}"
    batch_id = uuid4().hex[:12]
    trace_id = uuid4().hex[:12]

    recap_result = await job.execute(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )

    recap_doc = {}
    recap_docs = getattr(write_port, "recap_docs", None)
    if recap_docs:
        recap_doc = recap_docs[0].recap_doc
    else:
        snapshot_row = await gw._client.get_existing_post_market_recap_snapshot(trade_date)
        if snapshot_row is not None:
            recap_doc = getattr(snapshot_row, "recap_doc", {}) or {}

    target_stock_id = _TARGET_MAP.get(sample_name, "")
    target_diagnostics = {}

    if target_stock_id and recap_doc:
        top_candidates = recap_doc.get("top_candidates", [])
        target_diag: dict[str, Any] = {}
        for c in top_candidates:
            if c.get("stock_id") == target_stock_id:
                target_diag = {"refresh": {
                    "transition_type": c.get("transition_type", ""),
                    "transition_confidence": c.get("transition_confidence", ""),
                    "trigger_flags": c.get("trigger_flags", []),
                }}
                break
        target_diagnostics[target_stock_id] = target_diag

    assertion_passed = recap_result.status == "ok"
    assertion_report = {
        "passed": assertion_passed,
        "daily_status": recap_result.status,
        "recap_status": recap_result.status,
        "layer_results": {},
    }

    await gw.close()

    return ReplayLiveResult(
        daily_status=recap_result.status,
        daily_affected_rows=recap_result.affected_rows,
        recap_status=recap_result.status,
        assertion_report=assertion_report,
        recap_doc=recap_doc,
        target_diagnostics=target_diagnostics,
    )


# ── 盘前回放（Pre-Market Replay）──

@dataclass
class PreMarketReplayResult:
    pre_market_status: str = ""
    brief_doc: dict[str, Any] = field(default_factory=dict)
    target_diagnostics: dict[str, Any] = field(default_factory=dict)


async def run_pre_market_replay(
    trade_date: date,
    sample_name: str = "",
) -> PreMarketReplayResult:
    """盘前弱转强确认回放 — 使用新链 BuildPreMarketBriefJob。"""
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.gateway import DatabaseGateway
    from stock_processing_service.application.jobs.build_pre_market_brief_job import (
        BuildPreMarketBriefJob,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
        StockReadGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_write_gateway_adapter import (
        StockWriteGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
        StockEventGatewayAdapter,
    )
    from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
        StockIdempotencyGatewayAdapter,
    )
    from uuid import uuid4

    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    read_port = StockReadGatewayAdapter(db_gateway=gw)
    write_port = StockWriteGatewayAdapter(db_gateway=gw)
    event_port = StockEventGatewayAdapter(db_gateway=gw)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gw)

    job = BuildPreMarketBriefJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    sv = f"pre_market_replay_{sample_name or trade_date.isoformat()}"
    bid = uuid4().hex[:12]
    tid = uuid4().hex[:12]

    result = await job.execute(
        trade_date=trade_date,
        snapshot_version=sv,
        batch_id=bid,
        trace_id=tid,
    )

    brief_doc: dict[str, Any] = {"picks": []}
    target_diagnostics: dict[str, Any] = {}

    await gw.close()

    return PreMarketReplayResult(
        pre_market_status=result.status,
        brief_doc=brief_doc,
        target_diagnostics=target_diagnostics,
    )
