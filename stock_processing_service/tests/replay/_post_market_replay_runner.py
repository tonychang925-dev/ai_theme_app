from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any

from database_service.gateway import DatabaseGateway
from database_service.config import DatabaseConfig, DatabaseType
from stock_processing_service.application.jobs import (
    BuildDailySnapshotJob,
    BuildPostMarketRecapJob,
    BuildPreMarketBriefJob,
)
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRefreshService
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
    StockEventGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
    StockIdempotencyGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_write_gateway_adapter import (
    StockWriteGatewayAdapter,
)


@dataclass(frozen=True)
class ReplayExecutionResult:
    trade_date: date
    snapshot_version: str
    daily_status: str
    daily_affected_rows: int
    recap_status: str
    recap_doc: dict[str, Any]
    target_diagnostics: dict[str, Any]


@dataclass(frozen=True)
class PreMarketReplayExecutionResult:
    trade_date: date
    snapshot_version: str
    pre_market_status: str
    brief_doc: dict[str, Any]
    target_diagnostics: dict[str, Any]


class _ReplayDatabaseStockFacade:
    """Runtime facade to adapt DatabaseGateway signatures to stock-processing ports."""

    def __init__(self, gateway: DatabaseGateway) -> None:
        self._gateway = gateway

    async def get_trade_calendar(self, trade_date: date):
        return await self._gateway.get_trade_calendar(trade_date)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None):
        return await self._gateway.get_stock_daily_bars(trade_date, stock_ids=stock_ids)

    async def get_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
    ):
        return await self._gateway.get_stock_daily_bars_range(start_date, end_date, stock_ids=stock_ids)

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids: list[str] | None = None):
        return await self._gateway.get_stock_auction_snapshot(trade_date, stock_ids=stock_ids)

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return await self._gateway.get_subject_stock_pool_by_trade_date(trade_date)

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return await self._gateway.get_subject_context_by_subject_keys(subject_keys, trade_date)

    async def get_prior_stock_daily_snapshots(
        self,
        trade_date: date,
        lookback_days: int,
        stock_ids: list[str] | None = None,
    ):
        return await self._gateway.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=stock_ids,
        )

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date):
        return await self._gateway.get_existing_pre_market_brief_snapshot(trade_date)

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return await self._gateway.get_existing_post_market_recap_snapshot(trade_date)

    async def upsert_stock_daily_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self._gateway.upsert_stock_daily_snapshot_rows(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self._gateway.upsert_subject_stock_daily_snapshot_rows(rows)

    async def upsert_stock_abnormal_event_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self._gateway.upsert_stock_abnormal_event_rows(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self._gateway.upsert_theme_stock_leaderboard_rows(rows)

    async def upsert_pre_market_brief_snapshot(self, doc: dict[str, Any]) -> int:
        return await self._gateway.upsert_pre_market_brief_snapshot(doc)

    async def upsert_post_market_recap_snapshot(self, doc: dict[str, Any]) -> int:
        return await self._gateway.upsert_post_market_recap_snapshot(doc)

    async def upsert_theme_mainline_identity_registry_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._gateway, "upsert_theme_mainline_identity_registry_rows", None)
        if callable(fn):
            return int(await fn(rows) or 0)
        return len(rows)

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._gateway, "upsert_mainline_identity_review_queue_rows", None)
        if callable(fn):
            return int(await fn(rows) or 0)
        return len(rows)

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._gateway, "upsert_strong_watch_history_rows", None)
        if callable(fn):
            return int(await fn(rows) or 0)
        return len(rows)

    async def publish_stock_processing_event(self, event: dict[str, Any]) -> str:
        event_name = str(event.get("event_name", "unknown"))
        payload = dict(event.get("payload") or {})
        payload.setdefault("trade_date", str(event.get("trade_date", "")))
        return await self._gateway.publish_stock_processing_event(event_name, payload)

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        return await self._gateway.acquire_job_idempotency(job_key, ttl_seconds)

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        await self._gateway.mark_job_completed(job_key, metadata or {})

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str) -> str:
        fn = getattr(self._gateway, "record_dead_letter", None)
        if callable(fn):
            return str(await fn(event_name, payload, reason))
        return ""


def replay_enabled() -> bool:
    return os.getenv("RUN_REPLAY_DB", "0") == "1"


def ensure_replay_write_ack() -> None:
    if os.getenv("REPLAY_DB_WRITE_OK", "0") != "1":
        raise RuntimeError(
            "Replay test writes snapshots/events. Set REPLAY_DB_WRITE_OK=1 and run only on a dedicated test DB."
        )


async def _assert_required_schema(gateway: DatabaseGateway, *, pre_market: bool = False) -> None:
    required_tables = {
        "stock_daily_snapshot",
        "subject_stock_daily_snapshot",
        "stock_abnormal_event",
        "theme_stock_leaderboard",
        "post_market_recap_snapshot",
    }
    if pre_market:
        required_tables.add("pre_market_brief_snapshot")

    required_columns = {
        ("subject_stock_daily_snapshot", "subject_name"),
    }

    async with gateway._client.pool.acquire() as conn:  # test-only strict preflight
        current_db = await conn.fetchval("SELECT current_database()")
        expected_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
        if str(current_db) != expected_db:
            raise RuntimeError(f"replay strict mode: wrong database connected: {current_db}, expected: {expected_db}")

        for table in sorted(required_tables):
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = $1
                )
                """,
                table,
            )
            if not exists:
                raise RuntimeError(f"replay strict mode: required table missing: {table}")

        for table, column in sorted(required_columns):
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = $1
                      AND column_name = $2
                )
                """,
                table,
                column,
            )
            if not exists:
                raise RuntimeError(f"replay strict mode: required column missing: {table}.{column}")


async def _get_replay_gateway() -> DatabaseGateway:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")

    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.postgres_ssl_mode = os.getenv("PG_SSL_MODE", "prefer")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    # Force singleton reconnect with explicit replay config.
    old = DatabaseGateway._instance
    if old is not None and getattr(old, "_client", None) is not None:
        try:
            await old._client.close()
        except Exception:
            pass
    DatabaseGateway._instance = None
    DatabaseGateway._client = None
    DatabaseGateway._initialized = False
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


async def run_post_market_replay(
    trade_date: date,
    sample_name: str,
) -> ReplayExecutionResult:
    ensure_replay_write_ack()
    gateway = await _get_replay_gateway()
    await _assert_required_schema(gateway, pre_market=False)
    facade = _ReplayDatabaseStockFacade(gateway)

    read_port = StockReadGatewayAdapter(db_gateway=facade)
    write_port = StockWriteGatewayAdapter(db_gateway=facade)
    event_port = StockEventGatewayAdapter(db_gateway=facade)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=facade)

    snapshot_version = f"replay_{trade_date.isoformat()}_{sample_name}_v1"
    batch_id = f"replay_{trade_date.isoformat()}"
    trace_id = f"replay_{sample_name}_{trade_date.isoformat()}"

    daily_job = BuildDailySnapshotJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
        cache_port=None,
    )
    recap_job = BuildPostMarketRecapJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
        cache_port=None,
    )

    daily_result = await daily_job.execute(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )
    recap_result = await recap_job.execute(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )
    recap_snapshot = await read_port.get_existing_post_market_recap_snapshot(trade_date)
    recap_doc = recap_snapshot.recap_doc if recap_snapshot else {}
    target_diagnostics = await _build_target_diagnostics(
        trade_date=trade_date,
        read_port=read_port,
        target_stock_ids=["002361.SZ", "605060.SH"],
    )

    return ReplayExecutionResult(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        daily_status=daily_result.status,
        daily_affected_rows=daily_result.affected_rows,
        recap_status=recap_result.status,
        recap_doc=recap_doc,
        target_diagnostics=target_diagnostics,
    )


async def run_pre_market_replay(
    trade_date: date,
    sample_name: str,
) -> PreMarketReplayExecutionResult:
    ensure_replay_write_ack()
    gateway = await _get_replay_gateway()
    await _assert_required_schema(gateway, pre_market=True)
    facade = _ReplayDatabaseStockFacade(gateway)

    read_port = StockReadGatewayAdapter(db_gateway=facade)
    write_port = StockWriteGatewayAdapter(db_gateway=facade)
    event_port = StockEventGatewayAdapter(db_gateway=facade)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=facade)

    snapshot_version = f"replay_{trade_date.isoformat()}_{sample_name}_v1"
    batch_id = f"replay_{trade_date.isoformat()}"
    trace_id = f"replay_pre_market_{sample_name}_{trade_date.isoformat()}"

    pre_market_job = BuildPreMarketBriefJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
        cache_port=None,
    )
    pre_market_result = await pre_market_job.execute(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )
    brief_snapshot = await read_port.get_existing_pre_market_brief_snapshot(trade_date)
    brief_doc = brief_snapshot.brief_doc if brief_snapshot else {}
    target_diagnostics = await _build_target_diagnostics(
        trade_date=trade_date,
        read_port=read_port,
        target_stock_ids=["605060.SH"],
    )

    return PreMarketReplayExecutionResult(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        pre_market_status=pre_market_result.status,
        brief_doc=brief_doc,
        target_diagnostics=target_diagnostics,
    )


async def _build_target_diagnostics(
    *,
    trade_date: date,
    read_port: StockReadGatewayAdapter,
    target_stock_ids: list[str],
) -> dict[str, Any]:
    bars = await read_port.get_stock_daily_bars(trade_date)
    bars_by_stock = {b.stock_id: b for b in bars}
    pool_rows = await read_port.get_subject_stock_pool_by_trade_date(trade_date)
    seed_service = StrongWatchSeedService()
    refresh_service = StrongWatchRefreshService()
    prune_service = StrongWatchPruneService()
    promote_service = StrongWatchPromoteService()
    prior_rows = await read_port.get_prior_stock_daily_snapshots(
        trade_date=trade_date,
        lookback_days=7,
        stock_ids=target_stock_ids,
    )
    seeded_rows = seed_service.seed(pool_rows)
    refreshed_rows = refresh_service.refresh(seeded_rows, bars, prior_rows=prior_rows)
    kept_rows, pruned_rows = prune_service.prune(refreshed_rows)
    promoted_rows = promote_service.promote(trade_date, kept_rows)
    kept_by_stock = {r.stock_id: r for r in kept_rows}
    pruned_by_stock = {r.stock_id: r for r in pruned_rows}
    refreshed_by_stock = {r.stock_id: r for r in refreshed_rows}
    prior_by_stock = {p.stock_id: p for p in prior_rows}
    candidate_svc = W2SCandidateService()

    diagnostics: dict[str, Any] = {}
    for stock_id in target_stock_ids:
        stock_pool_rows = [r for r in pool_rows if r.stock_id == stock_id]
        promoted_for_stock = [r for r in promoted_rows if r.stock_id == stock_id]
        sorted_promoted = sorted(promoted_for_stock, key=lambda r: (r.pool_rank is None, r.pool_rank or 9999))
        selected_row = sorted_promoted[0] if sorted_promoted else None
        bar = bars_by_stock.get(stock_id)
        prior = prior_by_stock.get(stock_id)
        refreshed = refreshed_by_stock.get(stock_id)
        kept = kept_by_stock.get(stock_id)
        pruned = pruned_by_stock.get(stock_id)
        base_trace = {
            "present_in_pool": bool(stock_pool_rows),
            "present_in_refreshed": refreshed is not None,
            "present_in_kept": kept is not None,
            "present_in_pruned": pruned is not None,
            "present_in_promoted_pool": bool(promoted_for_stock),
            "pool_subject_count": len(stock_pool_rows),
        }
        if refreshed is not None:
            base_trace["refresh"] = {
                "watch_score": str(refreshed.watch_score),
                "strong_grade": refreshed.strong_grade,
                "mainline_context_score": str(refreshed.mainline_context_score),
                "strong_gene_score": str(refreshed.strong_gene_score),
                "support_score": str(refreshed.support_score),
                "support_type": refreshed.support_type,
                "weakness_tolerance_score": str(refreshed.weakness_tolerance_score),
                "support_refs": list(refreshed.support_refs or []),
                "legacy_gap_candidates": [
                    x for x in list(refreshed.support_refs or []) if isinstance(x, str) and x.startswith("legacy_gap_candidate")
                ],
                "prior7_limitup_days": refreshed.prior7_limitup_days,
                "prior7_strong_days": refreshed.prior7_strong_days,
                "prior7_best_watch_score": str(refreshed.prior7_best_watch_score),
                "prior7_peak_rank": refreshed.prior7_peak_rank,
                "watch_status": refreshed.watch_status,
            }
        if pruned is not None:
            base_trace["prune"] = {
                "watch_status": pruned.watch_status,
                "prune_mode": pruned.prune_mode,
                "prune_reason_code": pruned.prune_reason_code,
                "removed_reason": pruned.removed_reason,
                "kept_because": pruned.kept_because,
            }
        if kept is not None:
            base_trace["kept"] = {
                "watch_status": kept.watch_status,
                "weak_days": kept.weak_days,
                "strong_grade": kept.strong_grade,
                "kept_because": kept.kept_because,
            }

        if selected_row is None:
            reject_reason = "not_in_promoted_pool"
            if pruned is not None and pruned.prune_reason_code:
                reject_reason = f"pruned:{pruned.prune_reason_code}"
            diagnostics[stock_id] = {
                **base_trace,
                "candidate_source": "not_promoted",
                "candidate_level": "reject",
                "reject_reason": reject_reason,
            }
            continue

        explain = candidate_svc.explain_candidate(
            row=selected_row,
            bar=bar,
            prior=prior,
            prior_rows=prior_rows,
        )
        explain.update(base_trace)
        diagnostics[stock_id] = explain
    return diagnostics
