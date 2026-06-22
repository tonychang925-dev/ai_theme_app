"""Collection task Runner implementations

- ScriptCommandRunner: legacy script (subprocess)
- PostMarketRecapRunner: serviced recap (BuildPostMarketRecapJob)
- ProcessIsolatedRunner: process-isolated heavy tasks
- EvidenceRecapGenerateRunner: M4/M5 evidence fusion to recap snapshot
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
PYTHON_BIN = os.environ.get("COLLECTION_PYTHON_BIN", str(PROJECT_ROOT / ".venv" / "bin" / "python"))

from stock_processing_service.application.services.collection_task_registry import (
    CollectionTaskContext,
    CollectionTaskResult,
    CollectionTaskRunner,
    get_default_registry,
)
from stock_processing_service.application.services.f10_capital_evidence_service import F10CapitalEvidenceService
from stock_processing_service.application.services.f10_capital_parser import F10CapitalParser

# ── 注册表中已有的 Runner key ──
# "script.default"    → ScriptCommandRunner (兼容旧脚本)
# "recap.snapshot"    → PostMarketRecapRunner (服务化 recap)
# "abnormal.signal"   → BuildStockAbnormalSignalRunner (服务化异动检测)


class ScriptCommandRunner:
    """Legacy script runner: executes pre-defined commands via subprocess."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if not context.commands:
            return CollectionTaskResult(status="success", current_label="无命令执行", progress_percent=100)

        # 兼容 CollectionCommand 对象和原始 list[str]
        raw_commands: list[list[str]] = []
        for item in context.commands:
            if hasattr(item, "cmd"):
                raw_commands.append(list(item.cmd))
            elif isinstance(item, list):
                raw_commands.append(item)

        logs: list[str] = []
        for cmd in raw_commands:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, **context.env} if context.env else None,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    logs.append(stdout.decode("utf-8", errors="replace")[:2000])
                if stderr:
                    logs.append(stderr.decode("utf-8", errors="replace")[:2000])
                if proc.returncode != 0:
                    return CollectionTaskResult(
                        status="failed",
                        current_label=f"命令失败 (exit={proc.returncode})",
                        logs=logs,
                        error_message=f"Command failed: {' '.join(cmd[:3])}...",
                    )
            except Exception as e:
                return CollectionTaskResult(
                    status="failed",
                    current_label="命令执行异常",
                    logs=logs,
                    error_message=str(e),
                )
        return CollectionTaskResult(status="success", current_label="脚本命令执行完成", logs=logs)


class BuildStockAbnormalSignalRunner:
    """Abnormal signal detection Runner via BuildStockAbnormalSignalJob."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date as _date
            payload = context.payload
            options = payload.get("options") or {}
            abnormal_filters = payload.get("abnormal_filters") or {}
            token = context.env.get("TUSHARE_TOKEN", "")
            trade_date_val = _date.fromisoformat(context.trade_date)

            job = context.container.build_stock_abnormal_signal
            result = await job.execute(
                trade_date=trade_date_val,
                tushare_token=token,
                min_turnover_rate=float(options.get("min_turnover_rate", 3.0)),
                min_composite_score=float(options.get("min_composite_score", 40.0)),
            )
            ok = result.status in ("ok", "ok_no_signals", "ok_no_inputs")
            return CollectionTaskResult(
                status="success" if ok else "failed",
                current_label=f"异动信号检测完成 ({result.status})",
                logs=[f"abnormal_signal status={result.status}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="异动信号检测异常", error_message=str(e))


class BuildStockKlineJudgementsRunner:
    """Stock K-line position/pattern Runner -- in-process script entry."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys
            _orig = _sys.argv[:]
            _sys.argv = ["build_stock_kline_judgements.py", "--trade-date", context.trade_date]
            try:
                from database_service.scripts.build_stock_kline_judgements import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig
            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"个股K线位置与形态判断完成 (exit={exit_code})",
                logs=[f"stock_kline_judgements exit_code={exit_code}"],
                error_message="" if (exit_code or 0) == 0 else f"stock_kline_judgements exit_code={exit_code}",
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="个股K线位置与形态判断异常",
                error_message=f"{type(e).__name__}: {e!r}",
            )


class PostMarketReportContextRunner:
    """Post-market report context Runner

    This Runner queries new-chain context only; does not write legacy tables.
    Exposes market/theme flow collection status before recap.snapshot.
    Final report still written by BuildPostMarketRecapJob to snapshot.
    """

    def __init__(self, context_key: str, label: str) -> None:
        self._context_key = context_key
        self._label = label

    @staticmethod
    def _db_pool(gateway):
        facade = getattr(gateway, "_db", None)
        db_client = getattr(facade, "_db", None)
        return getattr(db_client, "pool", None)

    async def _run_light_probe(self, gateway, trade_date_val: date) -> tuple[bool, str] | None:
        pool = self._db_pool(gateway)
        if pool is None:
            return None

        if self._context_key == "market":
            sql = """
            SELECT
                COUNT(*) AS stock_count,
                COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) > 0) AS up_count,
                COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) < 0) AS down_count,
                COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE) OR COALESCE(pct_chg, 0) >= 9.8) AS limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
            """
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, trade_date_val)
            stock_count = int((row or {}).get("stock_count") or 0)
            summary = (
                f"market stock_count={stock_count} "
                f"up={int((row or {}).get('up_count') or 0)} "
                f"down={int((row or {}).get('down_count') or 0)} "
                f"limit_up={int((row or {}).get('limit_up_count') or 0)}"
            )
            return stock_count > 0, summary

        if self._context_key == "theme_capital_flow":
            sql = """
            SELECT COUNT(*) AS row_count
            FROM (
                SELECT 1
                FROM theme_cycle_judgement_v2 v2
                WHERE v2.trade_date = $1::date
                  AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
                  AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                  AND EXISTS (
                      SELECT 1
                      FROM subject_stock_daily_snapshot s
                      WHERE s.trade_date = v2.trade_date
                        AND s.subject_key = v2.subject_key
                  )
                LIMIT 50
            ) t
            """
            async with pool.acquire() as conn:
                row_count = int(await conn.fetchval(sql, trade_date_val) or 0)
            return row_count > 0, f"theme_capital_flow rows={row_count}"

        return None

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(
                status="failed",
                current_label="容器未注入",
                error_message="container is None: api_app 需要注入 container 到 CollectionJobManager",
            )

        try:
            trade_date_val = date.fromisoformat(context.trade_date)
            gateway = getattr(context.container, "report_context_gateway", None)
            if gateway is None:
                return CollectionTaskResult(
                    status="failed",
                    current_label=f"{self._label}异常",
                    error_message="container missing report_context_gateway",
                )

            probe = await self._run_light_probe(gateway, trade_date_val)
            if probe is not None:
                ok, summary = probe
            else:
                context_doc = await gateway.get_post_market_report_context(
                    trade_date=trade_date_val,
                    subject_keys=[],
                    stock_ids=[],
                )
                data = context_doc.get(self._context_key)
                if isinstance(data, list):
                    count = len(data)
                    ok = count > 0
                    summary = f"{self._context_key} rows={count}"
                else:
                    ok = bool(data)
                    source = (data or {}).get("source_type") if isinstance(data, dict) else ""
                    summary = f"{self._context_key} source={source or '--'}"

            # Phase 4E fix: theme_capital_flow 为空不得阻断 DailyReview 生成
            if self._context_key == "theme_capital_flow" and not ok:
                return CollectionTaskResult(
                    status="success",
                    current_label=f"{self._label}为空，继续生成",
                    logs=[
                        summary,
                        "theme_capital_flow empty: continue with diagnostics.partial",
                    ],
                    error_message="",
                )

            return CollectionTaskResult(
                status="success" if ok else "failed",
                current_label=f"{self._label}完成" if ok else f"{self._label}缺失",
                logs=[summary],
                error_message="" if ok else f"{self._context_key} missing for trade_date={context.trade_date}",
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label=f"{self._label}异常",
                error_message=f"{type(e).__name__}: {e!r}",
            )


class PostMarketPrerequisitesRunner:
    """Build new-chain post-market prerequisites before report context checks."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(
                status="failed",
                current_label="容器未注入",
                error_message="container is None: api_app 需要注入 container 到 CollectionJobManager",
            )

        try:
            trade_date_val = date.fromisoformat(context.trade_date)
            batch_id = uuid4().hex[:12]
            trace_id = uuid4().hex[:12]
            logs: list[str] = []

            jobs = [
                (
                    "evidence",
                    context.container.build_theme_cycle_evidence_daily.execute,
                    {
                        "trade_date": trade_date_val,
                        "snapshot_version": "collection.recap_prereq.evidence.v1",
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    },
                ),
                (
                    "cycle_pre_identity",
                    context.container.build_cycle_judgement.execute,
                    {
                        "trade_date": trade_date_val,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    },
                ),
                (
                    "identity",
                    context.container.build_identity.execute,
                    {
                        "trade_date": trade_date_val,
                        "snapshot_version": "collection.recap_prereq.identity.v1",
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    },
                ),
                (
                    "cycle_post_identity",
                    context.container.build_cycle_judgement.execute,
                    {
                        "trade_date": trade_date_val,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    },
                ),
                (
                    "mainline_state",
                    context.container.build_mainline_state.execute,
                    {
                        "trade_date": trade_date_val,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    },
                ),
            ]

            for name, fn, kwargs in jobs:
                result = await fn(**kwargs)
                status = str(getattr(result, "status", ""))
                affected_rows = getattr(result, "affected_rows", 0)
                logs.append(f"recap_prereq {name} status={status} rows={affected_rows}")
                if status.startswith("failed") or status == "error":
                    return CollectionTaskResult(
                        status="failed",
                        current_label=f"新链前置构建失败 ({name})",
                        logs=logs,
                        error_message=f"{name} failed: {status}",
                    )

            return CollectionTaskResult(
                status="success",
                current_label="新链盘后前置构建完成",
                logs=logs,
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="新链盘后前置构建异常",
                error_message=str(e),
            )


class BuildDragonTigerObjectRunner:
    """Dragon-tiger object build Runner -- new chain Job architecture."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(
                status="failed",
                current_label="容器未注入",
                error_message="container is None: api_app 需要注入 container 到 CollectionJobManager",
            )

        try:
            from datetime import date

            trade_date_val = date.fromisoformat(context.trade_date)
            token = context.env.get("TUSHARE_TOKEN", "")

            job = context.container.build_dragon_tiger_object
            result = await job.execute(trade_date=trade_date_val, tushare_token=token)
            warnings = list(getattr(result, "warnings", []) or [])
            metrics = dict(getattr(result, "metrics", {}) or {})
            if result.status == "skipped_no_data":
                detail = warnings[0] if warnings else "dragon_tiger raw snapshots exist but payload is empty"
                return CollectionTaskResult(
                    status="skipped",
                    current_label="数据为空，skip到下一个流程",
                    logs=[
                        f"龙虎榜数据为空，skip到下一个流程: rows={result.affected_rows}",
                        f"龙虎榜详情: {detail}",
                        f"龙虎榜指标: {metrics}",
                    ],
                )

            return CollectionTaskResult(
                status="success" if result.status.startswith("ok") else "failed",
                current_label=f"龙虎榜对象构建完成 ({result.affected_rows} rows)",
                logs=[f"dragon_tiger status={result.status} rows={result.affected_rows}"],
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="龙虎榜对象构建异常",
                error_message=str(e),
            )


class BuildHotMoneyTradingActivityRunner:
    """Hot-money activity table Runner -- standard script entry."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys

            token = context.env.get("TUSHARE_TOKEN", "")
            payload = context.payload or {}
            options = payload.get("hot_money_activity") or {}
            force_refresh = bool(options.get("force_refresh", False))
            argv = ["build_hot_money_trading_activity.py", "--trade-date", context.trade_date]
            if token:
                argv.extend(["--token", token])
            if force_refresh:
                argv.append("--force-refresh")

            _orig = _sys.argv[:]
            _sys.argv = argv
            try:
                from database_service.scripts.build_hot_money_trading_activity import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig

            logs = [f"hot_money_activity_build status={'success' if (exit_code or 0) == 0 else 'failed'}"]
            logs.append(f"hot_money_trading_activity exit_code={exit_code}")

            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"游资动向活动表构建完成 (exit={exit_code})",
                logs=logs,
                error_message="" if (exit_code or 0) == 0 else f"hot_money_trading_activity exit_code={exit_code}",
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="游资动向活动表构建异常",
                logs=["hot_money_activity_build status=failed"],
                error_message=f"{type(e).__name__}: {e!r}",
            )


class AuctionSnapshotRunner:
    """Auction snapshot Runner via BuildAuctionSnapshotJob."""

    def __init__(self, universe_source: str = "auction_watch_universe", max_stocks: int = 0) -> None:
        self._universe_source = universe_source
        self._max_stocks = max_stocks

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date as _date
            token = context.env.get("TUSHARE_TOKEN", "")
            trade_date_val = _date.fromisoformat(context.trade_date)
            job = context.container.build_auction_snapshot
            result = await job.execute(
                trade_date=trade_date_val,
                tushare_token=token,
                universe_source=self._universe_source,
                max_stocks=self._max_stocks,
            )
            if result.status == "ok_no_data":
                return CollectionTaskResult(
                    status="skipped",
                    current_label="竞价原始数据为空，已跳过",
                    logs=[
                        f"auction_snapshot status={result.status}",
                        "auction_snapshot skipped: no raw auction data available",
                    ],
                )
            return CollectionTaskResult(
                status="success" if result.status == "ok" else "failed",
                current_label=f"竞价快照完成 ({result.status})",
                logs=[f"auction_snapshot status={result.status}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价快照异常", error_message=str(e))


class JyhfSyncListsRunner:
    """JYHF subject list sync Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            ns = argparse.Namespace()
            ns.token = context.env.get("JYHF_AUTH_TOKEN") or context.env.get("AUTHORIZATION") or None
            ns.batch_id = None
            ns.subject = None
            ns.subjects_file = None
            ns.full = False
            ns.use_latest_list_subjects = False
            ns.limit = 0
            ns.types = "lists"
            ns.history_mode = "full"
            ns.history_page_size = 20
            ns.history_max_pages = 12
            ns.history_backfill_date = None
            ns.trade_date = None
            ns.resume = False
            ns.skip_existing = False
            ns.write_cursor = False
            from sync_jyhf_to_local import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 题材列表同步完成 (exit={exit_code})",
                logs=[f"jyhf_sync_lists exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 题材列表同步异常", error_message=str(e))


class JyhfLoadSubjectNodeStagingRunner:
    """JYHF subject node staging Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            from database_service.scripts.load_subject_node_staging import main_async
            exit_code = await main_async()
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 题材节点入库完成 (exit={exit_code})",
                logs=[f"jyhf_load_staging exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 题材节点入库异常", error_message=str(e))


class JyhfSyncDetailsRunner:
    """JYHF subject detail sync Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            ns = argparse.Namespace()
            ns.token = context.env.get("JYHF_AUTH_TOKEN") or context.env.get("AUTHORIZATION") or None
            ns.batch_id = None
            ns.subject = None
            ns.subjects_file = None
            ns.full = False
            ns.use_latest_list_subjects = True
            ns.limit = 0
            ns.types = "details"
            ns.history_mode = "full"
            ns.history_page_size = 20
            ns.history_max_pages = 12
            ns.history_backfill_date = None
            ns.trade_date = None
            ns.resume = False
            ns.skip_existing = False
            ns.write_cursor = False
            from sync_jyhf_to_local import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 题材详情同步完成 (exit={exit_code})",
                logs=[f"jyhf_sync_details exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 题材详情同步异常", error_message=str(e))


class JyhfSyncStockDetailsRunner:
    """JYHF stock detail sync Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            ns = argparse.Namespace()
            ns.token = context.env.get("JYHF_AUTH_TOKEN") or context.env.get("AUTHORIZATION") or None
            ns.batch_id = None
            ns.subject = None
            ns.subjects_file = None
            ns.full = False
            ns.use_latest_list_subjects = True
            ns.limit = 0
            ns.types = "stock_details"
            ns.history_mode = "full"
            ns.history_page_size = 20
            ns.history_max_pages = 12
            ns.history_backfill_date = None
            ns.trade_date = context.trade_date
            ns.resume = True
            ns.skip_existing = True
            ns.write_cursor = False
            from sync_jyhf_to_local import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 股票详情同步完成 (exit={exit_code})",
                logs=[f"jyhf_sync_stock_details exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 股票详情同步异常", error_message=str(e))


class JyhfImportStockDailyRunner:
    """JYHF stock daily snapshot Runner -- API to DB, no local JSONL."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        self._ctx = context  # 保存上下文，供 _collect_subject_records 使用 progress_callback
        try:
            from database_service.managers.postgres_manager import PostgresDatabaseManager
            from database_service.scripts.import_jyhf_stock_daily_incremental import (
                build_rows_from_subject_records,
                ensure_tables,
                get_postgres_config,
                load_rows,
                refresh_current_mapping,
            )
            from sync_jyhf_to_local import resolve_token
            from theme_collector import APIClient

            token = resolve_token(context.env.get("JYHF_AUTH_TOKEN") or context.env.get("AUTHORIZATION") or None)
            if not token:
                return CollectionTaskResult(
                    status="failed",
                    current_label="JYHF 股票日快照采集失败",
                    error_message="missing JYHF token",
                )

            batch_id = f"collection_jyhf_stock_daily_{context.trade_date.replace('-', '')}"
            force = bool(context.payload.get("force") or (context.payload.get("options") or {}).get("force"))
            limit = int(context.payload.get("limit") or (context.payload.get("options") or {}).get("limit") or 0)

            manager = PostgresDatabaseManager(get_postgres_config())
            await manager.connect()
            try:
                await ensure_tables(manager)
                subject_keys = await self._load_subject_keys(manager, limit=limit)
                if not subject_keys:
                    return CollectionTaskResult(
                        status="failed",
                        current_label="JYHF 股票日快照采集失败",
                        error_message="no jyhf subjects found in DB subject_node_staging/theme_master",
                    )
                collect_subjects = subject_keys if force else await self._filter_missing_subjects(
                    manager,
                    subject_keys,
                    context.trade_date,
                )
                if not collect_subjects:
                    return CollectionTaskResult(
                        status="skipped",
                        current_label=f"JYHF 股票日快照已存在 ({context.trade_date})",
                        logs=[f"db_existing_subjects={len(subject_keys)} trade_date={context.trade_date}"],
                    )

                client = APIClient(token)
                subject_records = await self._collect_subject_records(client, collect_subjects, context.trade_date)
                rows, touched_subjects = build_rows_from_subject_records(subject_records, context.trade_date, batch_id)
                count = await load_rows(manager, rows)
                map_count, staging_count, serving_count = await refresh_current_mapping(
                    manager,
                    touched_subjects,
                    context.trade_date,
                    batch_id,
                )
            finally:
                await manager.disconnect()

            exit_code = 0 if count > 0 else 1
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 股票日快照采集入库完成 (rows={count})",
                logs=[
                    "jyhf_stock_daily_api_to_db",
                    f"subjects_total={len(subject_keys)}",
                    f"subjects_collected={len(collect_subjects)}",
                    f"subjects_touched={len(touched_subjects)}",
                    f"rows={count}",
                    f"current_map={map_count} staging={staging_count} serving={serving_count}",
                    f"api_stats={json.dumps(client.stats, ensure_ascii=False)}",
                ],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 股票日快照采集入库异常", error_message=str(e))

    async def _load_subject_keys(self, manager: Any, limit: int = 0) -> list[str]:
        async with manager.pool.acquire() as conn:
            has_node = await conn.fetchval("SELECT to_regclass('public.subject_node_staging') IS NOT NULL")
            if has_node:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT subject_key
                    FROM subject_node_staging
                    WHERE subject_key IS NOT NULL
                    ORDER BY subject_key
                    """
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT source_id AS subject_key
                    FROM theme_master
                    WHERE source_system = 'jyhf'
                      AND source_id IS NOT NULL
                    ORDER BY source_id
                    """
                )
        subject_keys = [str(r["subject_key"]) for r in rows if str(r["subject_key"] or "").strip()]
        return subject_keys[:limit] if limit > 0 else subject_keys

    async def _filter_missing_subjects(self, manager: Any, subject_keys: list[str], trade_date: str) -> list[str]:
        async with manager.pool.acquire() as conn:
            existing = await conn.fetch(
                """
                SELECT DISTINCT subject_key
                FROM subject_stock_daily_snapshot
                WHERE trade_date = $1::date
                  AND subject_key = ANY($2::varchar[])
                """,
                date.fromisoformat(trade_date),
                subject_keys,
            )
        existing_keys = {str(r["subject_key"]) for r in existing}
        return [key for key in subject_keys if key not in existing_keys]

    async def _collect_subject_records(
        self,
        client: Any,
        subject_keys: list[str],
        trade_date: str,
    ) -> list[tuple[str, list[Any]]]:
        from theme_collector import DataCollector

        out: list[tuple[str, list[Any]]] = []
        completed = 0
        failed = 0
        total = len(subject_keys)
        sem = asyncio.Semaphore(20)  # 最多 20 个并发 API 请求
        lock = asyncio.Lock()
        progress_cb = self._ctx.progress_callback if hasattr(self, '_ctx') else None

        def _fetch(subject_key: str) -> tuple[str, list[Any] | None, str | None]:
            try:
                data = client.request(
                    "stock/realtime-by-subject/v2",
                    {
                        "sort": "pctChg",
                        "sortType": "desc",
                        "date": trade_date,
                        "subjectId": subject_key,
                        "start": 0,
                        "end": 1200,
                    },
                    f"stock_daily_{trade_date}",
                )
                rows = DataCollector.extract_items(data)
                valid = [row for row in rows if isinstance(row, list)]
                return (subject_key, valid, None)
            except Exception as e:
                return (subject_key, None, str(e))

        async def _fetch_with_sem(subject_key: str) -> None:
            nonlocal completed, failed
            async with sem:
                subj, rows, err = await asyncio.to_thread(_fetch, subject_key)
            async with lock:
                completed += 1
                if err:
                    failed += 1
                elif rows:
                    out.append((subj, rows))
                # 实时进度日志：每 20 个或每 10% 输出一次
                if completed % 20 == 0 or completed == total:
                    pct = round(completed / total * 100)
                    msg = f"股票快照API采集: {completed}/{total} ({pct}%) 成功={completed-failed} 失败={failed}"
                    if progress_cb:
                        progress_cb(msg)
                    logger.info("JYHF stock daily %s", msg)

        tasks = [_fetch_with_sem(k) for k in subject_keys]
        await asyncio.gather(*tasks)

        return out


class JyhfSyncHistoryRunner:
    """JYHF history event sync Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            batch_id = f"collection_jyhf_history_{context.trade_date.replace('-', '')}"
            ns = argparse.Namespace()
            ns.token = context.env.get("JYHF_AUTH_TOKEN") or context.env.get("AUTHORIZATION") or None
            ns.batch_id = batch_id
            ns.subject = None
            ns.subjects_file = None
            ns.full = False
            ns.use_latest_list_subjects = True
            ns.limit = 0
            ns.types = "history"
            ns.history_mode = "incremental"
            ns.history_page_size = 20
            ns.history_max_pages = 12
            ns.history_backfill_date = context.trade_date
            ns.trade_date = None
            ns.resume = False
            ns.skip_existing = False
            ns.write_cursor = False
            from sync_jyhf_to_local import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 历史事件同步完成 (exit={exit_code})",
                logs=[f"jyhf_sync_history exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 历史事件同步异常", error_message=str(e))


class JyhfImportHistoryRunner:
    """JYHF history import Runner -- in-process semi-service mode."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            batch_id = f"collection_jyhf_history_{context.trade_date.replace('-', '')}"
            ns = argparse.Namespace()
            ns.subjects_file = context.payload.get("subjects_file", "")
            ns.batch_id = batch_id
            ns.mode = "append"
            from database_service.scripts.import_jyhf_history_incremental import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 历史事件导入完成 (exit={exit_code})",
                logs=[f"jyhf_import_history exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 历史事件导入异常", error_message=str(e))


class AuctionSignalRunner:
    """竞价信号 Runner -- 委托到 BuildAuctionSignalJob（新链 Job 架构）"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date as _date
            trade_date_val = _date.fromisoformat(context.trade_date)
            job = context.container.build_auction_signal
            result = await job.execute(trade_date=trade_date_val)
            if result.status in ("ok_no_data", "skipped_no_data", "no_data"):
                return CollectionTaskResult(
                    status="skipped",
                    current_label="竞价信号无数据，已跳过",
                    logs=[f"auction_signal status={result.status}"],
                )
            return CollectionTaskResult(
                status="success" if result.status == "ok" else "failed",
                current_label=f"竞价信号生成完成 ({result.status})",
                logs=[f"auction_signal status={result.status}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价信号生成异常", error_message=str(e))


class AuctionWatchUniverseRunner:
    """竞价观察池构建 Runner -- 新链 Job 架构"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date
            trade_date_val = date.fromisoformat(context.trade_date)
            job = context.container.build_auction_watch_universe
            result = await job.execute(trade_date=trade_date_val)
            return CollectionTaskResult(
                status="success" if result.status.startswith("ok") else "failed",
                current_label=f"竞价观察池构建完成 ({result.affected_rows} rows)",
                logs=[f"auction_watch_universe status={result.status} rows={result.affected_rows}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价观察池构建异常", error_message=str(e))


class TushareDailyBasicRunner:
    """Tushare daily_basic 换手率采集 Runner."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date as _date
            trade_date_val = _date.fromisoformat(context.trade_date)
            job = context.container.build_tushare_daily_basic
            result = await job.execute(trade_date=trade_date_val)
            ok = result.status == "ok"
            metrics = getattr(result, "metrics", {}) or {}
            return CollectionTaskResult(
                status="success" if ok else "failed",
                current_label=f"daily_basic采集完成 ({result.status})",
                logs=[
                    f"tushare_daily_basic status={result.status}",
                    f"rows={metrics.get('rows_upserted', result.affected_rows)}",
                    f"turnover_non_null={metrics.get('turnover_rate_non_null', 'N/A')}",
                    f"volume_ratio_non_null={metrics.get('volume_ratio_non_null', 'N/A')}",
                ],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="daily_basic采集异常", error_message=str(e))


class F10CapitalCollectRunner:
    """F10 资金动向快照采集 Runner -- 通过本地脚本采集并落库"""

    MAX_CONCURRENT_REQUESTS = 5
    MAX_SUCCESS_LOG_SAMPLES = 20

    def __init__(
        self,
        parser: F10CapitalParser | None = None,
        evidence_service: F10CapitalEvidenceService | None = None,
    ) -> None:
        self._parser = parser or F10CapitalParser()
        self._evidence_service = evidence_service or F10CapitalEvidenceService(self._parser)

    @staticmethod
    def _normalize_stock_ids(payload: dict[str, Any]) -> list[str]:
        stock_ids = payload.get("stock_ids") or payload.get("options", {}).get("stock_ids") or []
        if isinstance(stock_ids, str):
            stock_ids = [item.strip() for item in stock_ids.split(",") if item.strip()]
        if not isinstance(stock_ids, list):
            return []
        normalized: list[str] = []
        for item in stock_ids:
            text = str(item or "").strip()
            if text:
                normalized.append(text)
        return normalized

    @staticmethod
    def _collector_python(context: CollectionTaskContext) -> str:
        candidates = [
            str(context.env.get("TDX_AGENT_PYTHON") or "").strip(),
            str(os.getenv("TDX_AGENT_PYTHON") or "").strip(),
            str(PROJECT_ROOT / "tools" / "tdx_market_agent" / ".venv" / "bin" / "python"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return ""

    async def _resolve_stock_ids(self, context: CollectionTaskContext) -> tuple[list[str], list[str]]:
        logs: list[str] = []
        stock_ids = self._normalize_stock_ids(context.payload)
        if stock_ids:
            logs.append(f"stock_ids=payload:{len(stock_ids)}")
            return stock_ids, logs
        if context.container is None:
            return [], logs
        recap_job = getattr(context.container, "build_post_market_recap", None)
        read_port = getattr(recap_job, "_read_port", None)
        fetch_fn = getattr(read_port, "get_subject_stock_pool_by_trade_date", None) if read_port is not None else None
        if not callable(fetch_fn):
            return [], logs

        from datetime import date as _date

        rows = await fetch_fn(_date.fromisoformat(context.trade_date))
        resolved = []
        seen: set[str] = set()
        for row in rows:
            raw_stock_id = str((row or {}).get("stock_id") or (row or {}).get("stock_code") or (row or {}).get("symbol") or "").strip()
            if not raw_stock_id:
                continue
            normalized = raw_stock_id
            if "." in normalized:
                head, tail = normalized.rsplit(".", 1)
                if tail.upper() in {"SZ", "SH", "BJ"}:
                    normalized = head
            digits = "".join(ch for ch in normalized if ch.isdigit())
            normalized = digits if len(digits) == 6 else normalized
            if normalized and normalized not in seen:
                seen.add(normalized)
                resolved.append(normalized)
        if resolved:
            logs.append(f"stock_ids=subject_pool:{len(resolved)}")
        return resolved, logs

    async def _run_collect_script(
        self,
        *,
        python_bin: str,
        trade_date: str,
        stock_ids: list[str],
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        script_path = PROJECT_ROOT / "tools" / "tdx_market_agent" / "f10_capital_collect.py"
        if not script_path.exists():
            raise RuntimeError(f"collector script missing: {script_path}")
        cmd = [
            python_bin,
            "-u",
            str(script_path),
            "--trade-date",
            trade_date,
            "--symbols",
            ",".join(stock_ids),
            "--section",
            "资金动向",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self._collection_env_vars(), "PYTHONUNBUFFERED": "1"},
        )
        stderr_lines: list[str] = []

        async def _drain_stderr() -> None:
            assert proc.stderr is not None
            while True:
                raw = await proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                stderr_lines.append(line)
                if progress_callback is not None:
                    try:
                        progress_callback(line[:300])
                    except Exception:
                        pass

        stderr_task = asyncio.create_task(_drain_stderr())
        stdout_bytes = await proc.stdout.read() if proc.stdout is not None else b""
        await proc.wait()
        await stderr_task

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = "\n".join(stderr_lines).strip()
        if proc.returncode != 0:
            raise RuntimeError(stderr_text or stdout_text or f"collector exit={proc.returncode}")
        if not stdout_text:
            raise RuntimeError("collector returned empty stdout")
        try:
            payload = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"collector produced invalid json: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("collector output must be a JSON object")
        return payload

    @staticmethod
    def _collection_env_vars() -> dict[str, str]:
        env: dict[str, str] = {}
        value = str(os.getenv("TDX_AGENT_PYTHON") or "").strip()
        if value:
            env["TDX_AGENT_PYTHON"] = value
        return env

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")

        stock_ids, resolve_logs = await self._resolve_stock_ids(context)
        if not stock_ids:
            return CollectionTaskResult(
                status="failed",
                current_label="F10资金动向快照采集失败",
                logs=resolve_logs,
                error_message="subject pool is empty; please run stock_snapshot/jyhf first",
            )

        try:
            write_port = getattr(getattr(context.container, "build_post_market_recap", None), "_write_port", None)
            if write_port is None:
                return CollectionTaskResult(
                    status="failed",
                    current_label="F10资金动向快照采集失败",
                    error_message="container missing build_post_market_recap._write_port",
                )

            python_bin = self._collector_python(context)
            if not python_bin:
                return CollectionTaskResult(
                    status="failed",
                    current_label="F10资金动向快照采集失败",
                    logs=resolve_logs,
                    error_message="collector python not found; install tools/tdx_market_agent/.venv and mootdx[all]",
                )

            collector_payload = await self._run_collect_script(
                python_bin=python_bin,
                trade_date=context.trade_date,
                stock_ids=stock_ids,
                progress_callback=context.progress_callback,
            )
            records = collector_payload.get("records") or []
            if not isinstance(records, list):
                return CollectionTaskResult(
                    status="failed",
                    current_label="F10资金动向快照采集失败",
                    logs=resolve_logs,
                    error_message="collector output missing records",
                )

            rows: list[dict[str, Any]] = []
            success_samples: list[str] = []
            error_samples: list[str] = []
            logs: list[str] = resolve_logs + [f"collector={Path(python_bin).name}", f"stock_count={len(stock_ids)}"]

            record_map: dict[str, dict[str, Any]] = {}
            for item in records:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("stock_id") or item.get("system_stock_id") or "").strip()
                if not key:
                    continue
                normalized = key.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")
                record_map[key] = item
                record_map[normalized] = item

            success_count = 0
            fail_count = 0
            trade_date_val = date.fromisoformat(context.trade_date)
            for stock_id in stock_ids:
                record = record_map.get(stock_id) or record_map.get(stock_id.split(".", 1)[0])
                if not record:
                    fail_count += 1
                    if len(error_samples) < self.MAX_SUCCESS_LOG_SAMPLES:
                        error_samples.append(f"{stock_id}: missing collector record")
                    continue
                raw_text = str(record.get("raw_text") or "").strip()
                if not raw_text:
                    fail_count += 1
                    if len(error_samples) < self.MAX_SUCCESS_LOG_SAMPLES:
                        error_samples.append(f"{stock_id}: empty raw_text")
                    continue
                snapshot = self._evidence_service.build_snapshot_row(
                    trade_date=trade_date_val,
                    stock_id=str(record.get("system_stock_id") or record.get("stock_id") or stock_id),
                    stock_name=record.get("stock_name"),
                    source_updated_date=record.get("source_updated_date"),
                    raw_text=raw_text,
                )
                rows.append(snapshot)
                success_count += 1
                if len(success_samples) < self.MAX_SUCCESS_LOG_SAMPLES:
                    success_samples.append(f"{stock_id}: parse_status={snapshot.get('parse_status')}")

            logs.extend(
                [
                    f"success_count={success_count}",
                    f"fail_count={fail_count}",
                ]
            )
            logs.extend(success_samples)
            logs.extend(error_samples)

            if not rows:
                return CollectionTaskResult(
                    status="failed",
                    current_label="F10资金动向快照采集失败",
                    logs=logs,
                    error_message="no F10 snapshots collected",
                )

            written = await write_port.upsert_stock_f10_capital_snapshot_rows(rows)
            status = "success" if written > 0 else "failed"
            return CollectionTaskResult(
                status=status,
                current_label=f"F10资金动向快照采集完成 ({written} rows)",
                progress_percent=100,
                logs=logs + [f"written={written}"],
                error_message="" if written > 0 else "failed to write stock_f10_capital_snapshot rows",
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="F10资金动向快照采集异常", error_message=str(e))


class TushareKlineRunner:
    """Tushare K线采集 Runner -- 直接拉取 API → Gateway 写入，不经过本地 JSONL"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(
                status="failed", current_label="容器未注入",
                error_message="container is None",
            )
        try:
            from datetime import date

            token = context.env.get("TUSHARE_TOKEN", "")
            if not token:
                return CollectionTaskResult(
                    status="failed", current_label="缺少 Tushare token",
                    error_message="TUSHARE_TOKEN not set",
                )
            pause = float(context.payload.get("tushare_pause_seconds", 0.1))
            trade_date_val = date.fromisoformat(context.trade_date)

            job = context.container.build_tushare_daily_bar
            result = await job.execute(trade_date=trade_date_val, token=token, pause_seconds=pause)
            ok = result.status == "ok"
            error_message = "" if ok else f"tushare daily bar returned {result.status} rows={result.affected_rows}"

            return CollectionTaskResult(
                status="success" if ok else "failed",
                current_label=f"Tushare日线采集完成 ({result.status})",
                logs=[f"tushare_kline status={result.status} rows={result.affected_rows}"] + list(result.warnings or []),
                error_message=error_message,
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed", current_label="Tushare日线采集异常", error_message=str(e),
            )


class BuildLeaderLLMQueueRunner:
    """龙头候选 LLM 审查队列 Runner -- 进程内调用旧链服务（semi-service 模式）"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys
            _orig = _sys.argv[:]
            _sys.argv = ["build_theme_leader_llm_queue.py", "--trade-date", context.trade_date]
            try:
                from database_service.scripts.build_theme_leader_llm_queue import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig
            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"龙头候选 LLM 审查队列构建完成 (exit={exit_code})",
                logs=[f"leader_llm_queue exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="龙头候选 LLM 审查队列异常", error_message=str(e))


class BuildLeaderLLMJudgementRunner:
    """龙头候选 LLM 研判 Runner -- 进程内调用旧链服务（semi-service 模式）"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys
            max_themes = str(context.payload.get("leader_llm_max_themes", 5))
            _orig = _sys.argv[:]
            _sys.argv = ["build_theme_leader_llm_judgement.py", "--trade-date", context.trade_date,
                         "--only-queued", "--limit-themes", max_themes]
            try:
                from database_service.scripts.build_theme_leader_llm_judgement import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig
            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"龙头候选 LLM 研判完成 (exit={exit_code})",
                logs=[f"leader_llm_judgement exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="龙头候选 LLM 研判异常", error_message=str(e))


class CallLeaderLLMRunner:
    """龙头候选 LLM 调用 Runner -- 进程内调用旧链服务（semi-service 模式）"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys
            max_themes = str(context.payload.get("leader_llm_max_themes", 5))
            _orig = _sys.argv[:]
            _sys.argv = ["call_theme_leader_llm.py", "--trade-date", context.trade_date,
                         "--limit", max_themes, "--limit-themes", max_themes,
                         "--only-queued", "--only-pending"]
            try:
                from database_service.scripts.call_theme_leader_llm import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig
            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"龙头候选 LLM 调用完成 (exit={exit_code})",
                logs=[f"call_leader_llm exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="龙头候选 LLM 调用异常", error_message=str(e))


class BuildLeaderCandidateRunner:
    """龙头候选构建 Runner -- 进程内调用旧链服务（semi-service 模式）"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import sys as _sys
            _orig = _sys.argv[:]
            _sys.argv = ["build_theme_leader_candidate.py", "--trade-date", context.trade_date]
            try:
                from database_service.scripts.build_theme_leader_candidate import main_async
                exit_code = await main_async()
            finally:
                _sys.argv = _orig
            return CollectionTaskResult(
                status="success" if (exit_code or 0) == 0 else "failed",
                current_label=f"龙头候选构建完成 (exit={exit_code})",
                logs=[f"leader_candidate exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="龙头候选构建异常", error_message=str(e))


class PostMarketRecapRunner:
    """服务化盘后复盘 Runner

    直接调用 BuildPostMarketRecapJob.execute()，不再启动脚本子进程
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(
                status="failed",
                current_label="容器未注入",
                error_message="container is None: api_app 需要注入 container 到 CollectionJobManager",
            )

        job = context.container.build_post_market_recap
        trade_date_val = date.fromisoformat(context.trade_date)

        force_truth = bool((context.payload or {}).get("options", {}).get("force_rebuild_truth_source", False))
        result = await job.execute(
            trade_date=trade_date_val,
            snapshot_version="collection.post_market_recap.v1",
            batch_id=uuid4().hex[:12],
            trace_id=uuid4().hex[:12],
            lookback_days=7,
            skip_prereqs=not force_truth,
            skip_layer_c=not force_truth,
        )

        logs = [
            f"recap status={result.status}",
            f"recap affected_rows={result.affected_rows}",
        ]

        ok = result.status in {"ok", "skipped_idempotent"}
        return CollectionTaskResult(
            status="success" if ok else "failed",
            current_label=f"盘后复盘快照生成完成 ({result.status})",
            logs=logs,
            error_message="" if ok else f"recap status={result.status}",
        )


# ── P1: 股票快照可插拔数据源 Runner ──

class StockSnapshotBuildRunner:
    """股票快照统一入口 Runner -- 通过 Orchestrator 自动选择 Producer.

    provider=jyhf          → JyhfSubjectStockDailySnapshotProducer (API→DB)
    provider=tushare_join  → TushareJoinSubjectStockDailySnapshotProducer (SQL JOIN)
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        from datetime import date as _date
        from database_service.managers.postgres_manager import PostgresDatabaseManager
        from database_service.scripts.import_jyhf_stock_daily_incremental import get_postgres_config
        from stock_processing_service.application.jobs.subject_stock_snapshot.jyhf_producer import (
            JyhfSubjectStockDailySnapshotProducer,
        )
        from stock_processing_service.application.jobs.subject_stock_snapshot.tushare_join_producer import (
            TushareJoinSubjectStockDailySnapshotProducer,
        )
        from stock_processing_service.application.jobs.subject_stock_snapshot.factory import (
            SubjectStockSnapshotProducerFactory,
        )
        from stock_processing_service.application.jobs.subject_stock_snapshot.orchestrator import (
            SubjectStockDailySnapshotOrchestrator,
        )

        options = context.payload.get("options") or {}
        snapshot_opts = options.get("stock_snapshot") or {}
        provider = str(snapshot_opts.get("provider", "jyhf")).strip().lower()
        on_existing = str(snapshot_opts.get("on_existing", "skip")).strip().lower()
        force = bool(snapshot_opts.get("force", False))

        if provider not in ("jyhf", "tushare_join"):
            return CollectionTaskResult(
                status="failed",
                current_label=f"不支持的 provider: {provider}",
                error_message=f"unsupported stock_snapshot provider: {provider}",
            )
        if on_existing not in ("skip", "upsert", "replace"):
            return CollectionTaskResult(
                status="failed",
                current_label=f"不支持的 on_existing: {on_existing}",
                error_message=f"unsupported on_existing: {on_existing}",
            )

        jyhf_token = (
            context.env.get("JYHF_AUTH_TOKEN")
            or context.env.get("AUTHORIZATION")
            or ""
        ).strip()

        manager = PostgresDatabaseManager(get_postgres_config())
        await manager.connect()
        try:
            jyhf_producer = JyhfSubjectStockDailySnapshotProducer(
                db_pool=manager.pool, jyhf_token=jyhf_token,
            )
            tushare_join_producer = TushareJoinSubjectStockDailySnapshotProducer(
                db_pool=manager.pool,
            )
            factory = SubjectStockSnapshotProducerFactory(
                jyhf_producer=jyhf_producer,
                tushare_join_producer=tushare_join_producer,
            )
            orchestrator = SubjectStockDailySnapshotOrchestrator(
                factory=factory,
                db_pool=manager.pool,
            )

            trade_date_val = _date.fromisoformat(context.trade_date)
            result = await orchestrator.execute(
                trade_date=trade_date_val,
                provider=provider,
                force=force,
                on_existing=on_existing,
            )
        finally:
            await manager.disconnect()

        logs = _format_snapshot_result(result)
        ok = result.status in ("ok", "ok_existing", "ok_no_data")
        return CollectionTaskResult(
            status="success" if ok else "failed",
            current_label=f"股票快照完成 ({result.provider}, {result.affected_rows} rows)",
            logs=logs,
            error_message="" if ok else "; ".join(result.warnings),
        )


def _format_snapshot_result(result) -> list[str]:
    """将 SubjectStockSnapshotBuildResult 格式化为前端可读日志."""
    metrics = result.metrics or {}
    lines: list[str] = [
        f"数据源: {result.provider}",
        f"写入行数: {result.affected_rows}",
        f"状态: {result.status}",
        f"batch_id: {metrics.get('batch_id', '--')}",
    ]
    if result.provider == "tushare_join":
        lines += [
            f"Tushare 当日股票数: {metrics.get('stock_daily_count', '--')}",
            f"映射股票数: {metrics.get('mapped_distinct_stocks', metrics.get('mapped_stock_count', '--'))}",
            f"成功匹配: {metrics.get('matched_stock_count', '--')}",
            f"缺失股票: {metrics.get('real_missing_count', metrics.get('missing_stock_count', '--'))}",
            f"匹配率: {metrics.get('match_rate', '--')}",
        ]
    elif result.provider == "jyhf":
        lines += [
            f"题材总数: {metrics.get('subjects_total', '--')}",
            f"已采集题材: {metrics.get('subjects_collected', '--')}",
            f"触及题材: {metrics.get('subjects_touched', '--')}",
        ]
    if result.warnings:
        lines.append(f"警告: {'; '.join(result.warnings)}")
    return lines


# ── P1: 题材热度排名可插拔数据源 Runner ──

class SubjectRankBuildRunner:
    """题材热度排名统一入口 Runner -- 通过 Orchestrator 自动选择 Producer.

    provider=jyhf          → JyhfSubjectRankProducer (JSONL→DB)
    provider=snapshot_agg  → SnapshotAggSubjectRankProducer (SQL 聚合)
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        from datetime import date as _date
        from database_service.managers.postgres_manager import PostgresDatabaseManager
        from database_service.scripts.import_jyhf_history_incremental import get_postgres_config
        from stock_processing_service.application.jobs.subject_rank.jyhf_producer import (
            JyhfSubjectRankProducer,
        )
        from stock_processing_service.application.jobs.subject_rank.snapshot_agg_producer import (
            SnapshotAggSubjectRankProducer,
        )
        from stock_processing_service.application.jobs.subject_rank.factory import (
            SubjectRankProducerFactory,
        )
        from stock_processing_service.application.jobs.subject_rank.orchestrator import (
            SubjectRankOrchestrator,
        )

        options = context.payload.get("options") or {}
        rank_opts = options.get("subject_rank") or {}
        provider = str(rank_opts.get("provider", "jyhf")).strip().lower()
        on_existing = str(rank_opts.get("on_existing", "skip")).strip().lower()
        force = bool(rank_opts.get("force", False))

        if provider not in ("jyhf", "snapshot_agg"):
            return CollectionTaskResult(
                status="failed",
                current_label=f"不支持的 provider: {provider}",
                error_message=f"unsupported subject_rank provider: {provider}",
            )
        if on_existing not in ("skip", "upsert", "replace"):
            return CollectionTaskResult(
                status="failed",
                current_label=f"不支持的 on_existing: {on_existing}",
                error_message=f"unsupported on_existing: {on_existing}",
            )

        manager = PostgresDatabaseManager(get_postgres_config())
        await manager.connect()
        try:
            jyhf_producer = JyhfSubjectRankProducer(db_pool=manager.pool)
            snapshot_agg_producer = SnapshotAggSubjectRankProducer(db_pool=manager.pool)
            factory = SubjectRankProducerFactory(
                jyhf_producer=jyhf_producer,
                snapshot_agg_producer=snapshot_agg_producer,
            )
            orchestrator = SubjectRankOrchestrator(
                factory=factory,
                db_pool=manager.pool,
            )

            trade_date_val = _date.fromisoformat(context.trade_date)
            result = await orchestrator.execute(
                trade_date=trade_date_val,
                provider=provider,
                force=force,
                on_existing=on_existing,
            )
        finally:
            await manager.disconnect()

        logs = _format_rank_result(result)
        ok = result.status in ("ok", "ok_existing", "ok_no_data")
        return CollectionTaskResult(
            status="success" if ok else "failed",
            current_label=f"题材热度排名完成 ({result.provider}, {result.affected_rows} rows)",
            logs=logs,
            error_message="" if ok else "; ".join(result.warnings),
        )


def _format_rank_result(result) -> list[str]:
    """将 SubjectRankBuildResult 格式化为前端可读日志."""
    metrics = result.metrics or {}
    lines: list[str] = [
        f"数据源: {result.provider}",
        f"写入行数: {result.affected_rows}",
        f"状态: {result.status}",
        f"batch_id: {metrics.get('batch_id', '--')}",
    ]
    if result.provider == "snapshot_agg":
        lines += [
            f"快照题材数: {metrics.get('snapshot_subject_count', '--')}",
            f"上榜题材数: {metrics.get('ranked_subject_count', '--')}",
            f"Top100: {metrics.get('top100_count', '--')}",
            f"缺失名称: {metrics.get('missing_name_count', '--')}",
            f"平均heat: {metrics.get('avg_heat', '--')}",
            f"heat范围: {metrics.get('min_heat', '--')} ~ {metrics.get('max_heat', '--')}",
        ]
    elif result.provider == "jyhf":
        lines += [
            f"history文件数: {metrics.get('history_files', '--')}",
            f"日期rank行数: {metrics.get('date_rank_rows', '--')}",
            f"题材数: {metrics.get('subject_count', '--')}",
        ]
    if result.warnings:
        lines.append(f"警告: {'; '.join(result.warnings)}")
    return lines


# ── P2: 子进程隔离 Runner ──

class ProcessIsolatedRunner:
    """P2: 将重任务 runner 隔离到独立子进程，不阻塞 SPS 主进程

    子进程执行真实 runner_key，主进程只做 stdout 读取和超时管理
    """

    def __init__(
        self,
        runner_key: str,
        timeout_env: str = "",
        default_timeout_sec: int = 900,
    ) -> None:
        self.runner_key = runner_key
        self.timeout_env = timeout_env
        self.default_timeout_sec = default_timeout_sec

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        timeout_sec = int(
            context.env.get(self.timeout_env)
            or os.getenv(self.timeout_env, str(self.default_timeout_sec))
        )

        python_bin = context.python_bin or PYTHON_BIN
        project_root = context.project_root or os.getenv("AI_THEME_PROJECT_ROOT", str(PROJECT_ROOT))
        worker_path = str(Path(project_root) / "stock_processing_service" / "workers" / "run_collection_runner.py")

        cmd = [
            python_bin, worker_path,
            "--runner-key", self.runner_key,
            "--trade-date", context.trade_date,
            "--payload-json",
            json.dumps(context.payload or {}, ensure_ascii=False),
        ]

        logger.info("ProcessIsolated: spawning %s", " ".join(cmd[:4]))

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # P2: 合并防 pipe 死锁
                env={
                    **os.environ,
                    **(context.env or {}),
                    "PYTHONUNBUFFERED": "1",
                    "SPS_WORKER_CHILD": "1",
                },
                start_new_session=True,
            )

            logs: list[str] = []
            result_payload: dict[str, Any] | None = None

            try:
                async with asyncio.timeout(timeout_sec):
                    assert proc.stdout is not None
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace").rstrip()
                        if text.startswith("__SPS_RESULT__"):
                            try:
                                result_payload = json.loads(text.removeprefix("__SPS_RESULT__"))
                            except json.JSONDecodeError:
                                logs.append(text[:500])
                        else:
                            logs.append(text[:2000])
                    await proc.wait()
            except TimeoutError:
                self._kill_process(proc, force=True)
                return CollectionTaskResult(
                    status="failed",
                    current_label=f"{self.runner_key} 子进程超时 ({timeout_sec}s)",
                    logs=logs,
                    error_message=f"{self.runner_key} timeout after {timeout_sec}s",
                )

            return_code = 0 if proc.returncode == 0 else int(proc.returncode or 1)

            if result_payload:
                return CollectionTaskResult(
                    status=result_payload.get("status", "failed"),
                    current_label=result_payload.get("current_label", f"{self.runner_key} 子进程完成"),
                    logs=logs + result_payload.get("logs", []),
                    error_message=result_payload.get("error_message", ""),
                    progress_percent=result_payload.get("progress_percent", 0),
                )

            ok = return_code == 0
            return CollectionTaskResult(
                status="success" if ok else "failed",
                current_label=f"{self.runner_key} 子进程{'完成' if ok else '失败'} (exit={return_code})",
                logs=logs,
                error_message="" if ok else f"worker exit_code={return_code}",
            )

        except asyncio.CancelledError:
            if proc is not None:
                self._kill_process(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except Exception:
                    self._kill_process(proc, force=True)
            raise
        except Exception as exc:
            return CollectionTaskResult(
                status="failed",
                current_label=f"{self.runner_key} 子进程异常",
                error_message=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _kill_process(proc, force: bool = False):
        if proc is None:
            return
        try:
            if proc.returncode is None:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass


# ── PR-13D: 指数采集 Runner ──
class IndexKlineCollectRunner:
    """在采集链路中执行指数K线采集 + 技术分析"""

    runner_key: str = "index_kline_collect"

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import asyncpg
            conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=10)
            try:
                from stock_processing_service.application.jobs.index_kline_collect_job import (
                    IndexKlineCollectJob,
                )
                from datetime import date as _date
                td = _date.fromisoformat(context.trade_date) if isinstance(context.trade_date, str) else context.trade_date
                job = IndexKlineCollectJob(pool=conn)
                result = await job.collect(trade_date=td)
                d = result.to_dict()
                if d.get("success"):
                    return CollectionTaskResult(
                        status="success",
                        current_label=f"指数采集完成 {d.get('collected_count',0)}/{d.get('total_count',0)}",
                        logs=[f"collected={d.get('collected_count')}/{d.get('total_count')} tech={d.get('technical_count')}"],
                    )
                else:
                    return CollectionTaskResult(
                        status="failed",
                        current_label=f"指数采集缺失: {d.get('missing_indices',[])}",
                        error_message=str(d.get('missing_indices', [])),
                    )
            finally:
                await conn.close()
        except Exception as exc:
            return CollectionTaskResult(
                status="failed",
                current_label=f"指数采集异常: {type(exc).__name__}",
                error_message=str(exc),
            )


# ── M4/M5: Evidence → Recap Generate Runner ──────────────────────


class M7bErrorComputeRunner:
    """M7b: Compute prediction vs reality errors after recap generation."""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        import json as _json
        from datetime import date as _date

        try:
            td = _date.fromisoformat(context.trade_date)
            import asyncpg

            conn = await asyncpg.connect(
                host="localhost", port=5432, database="stock_data_test",
                user="postgres", password="postgres", timeout=10,
            )
            try:
                from stock_processing_service.domain.services.market_feedback import (
                    PredictionVsRealityEngine,
                )
                from stock_processing_service.domain.services.theme_return import (
                    ThemeReturnAttributionEngine,
                )

                # Read M6 predictions from market_recap_snapshot
                recap_row = await conn.fetchrow(
                    "SELECT recap_json FROM market_recap_snapshot WHERE trade_date=$1", td)
                if not recap_row:
                    return CollectionTaskResult(
                        status="skipped",
                        current_label="无复盘快照，跳过误差计算",
                    )

                recap = recap_row["recap_json"] if isinstance(recap_row["recap_json"], dict) else _json.loads(recap_row["recap_json"])
                top_themes = recap.get("top_themes", [])

                # Build predicted map from recap
                predicted: dict[str, dict] = {}
                for t in top_themes:
                    predicted[t["theme_name"]] = {
                        "strength": float(t.get("strength_score", 0)),
                        "rank": int(t.get("rank", 0)),
                        "sources": t.get("evidence_sources", []),
                        "stability": 0.5,
                        "anchor": 0.5,
                    }

                # Build actual map from theme returns (leaders' pct_chg)
                actual: dict[str, dict] = {}
                theme_leaders: dict[str, list] = {}
                for t in top_themes:
                    for ld in t.get("leaders", []):
                        theme_leaders.setdefault(t["theme_name"], []).append(ld["stock_code"])

                # Use THS pct_chg as market truth baseline
                ths_rows = await conn.fetch(
                    "SELECT stock_code, pct_chg FROM ths_hot_reason_snapshot WHERE trade_date=$1", td)
                stock_pct: dict[str, float] = {}
                for r in ths_rows:
                    stock_pct[str(r["stock_code"] or "")] = float(r["pct_chg"] or 0)

                for theme, stock_codes in theme_leaders.items():
                    pcts = [stock_pct.get(c, 0) for c in stock_codes[:5] if stock_pct.get(c)]
                    if pcts:
                        avg_pct = sum(pcts) / len(pcts)
                        actual[theme] = {
                            "strength": round(max(0, min(1, (avg_pct + 5) / 15)), 4),
                            "rank": 0,
                        }

                if not actual:
                    return CollectionTaskResult(
                        status="skipped",
                        current_label="无市场真值数据，跳过误差计算",
                    )

                # Compute errors
                engine = PredictionVsRealityEngine()
                report = engine.compute(td, predicted, actual)

                # Persist to theme_prediction_snapshot
                count = 0
                for err in report.errors:
                    await conn.execute(
                        """INSERT INTO theme_prediction_snapshot (
                             trade_date, theme_name, predicted_strength, predicted_rank,
                             actual_strength, actual_rank, strength_error, rank_error,
                             abs_strength_error, error_bucket, stability_score, anchor_score,
                             source_trace_id
                           ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                           ON CONFLICT (trade_date, theme_name) DO UPDATE SET
                             predicted_strength=EXCLUDED.predicted_strength,
                             actual_strength=EXCLUDED.actual_strength,
                             strength_error=EXCLUDED.strength_error,
                             error_bucket=EXCLUDED.error_bucket""",
                        td, err.theme_name, err.predicted_strength, err.predicted_rank,
                        err.actual_strength, err.actual_rank, err.strength_error,
                        err.rank_error, err.abs_strength_error, err.error_bucket,
                        err.stability_score, err.anchor_score,
                        f"m7b:{td.isoformat()}:{err.theme_name}",
                    )
                    count += 1

                over = report.overestimated[:3]
                under = report.underestimated[:3]
                bias_msgs = [f"{s}={report.source_bias.get(s,0):.3f}" for s in report.source_bias]

                return CollectionTaskResult(
                    status="success",
                    current_label=f"M7b 误差计算完成: {count} themes, over={len(report.overestimated)} under={len(report.underestimated)}",
                    progress_percent=100,
                    logs=[
                        f"over={over} under={under}" if over or under else "all correct",
                        f"mean_abs_error={report.summary['mean_abs_error']}",
                        f"source_bias={bias_msgs}" if bias_msgs else "no bias detected",
                    ],
                )
            finally:
                await conn.close()
        except Exception as exc:
            return CollectionTaskResult(
                status="failed",
                current_label=f"M7b 误差计算失败: {type(exc).__name__}",
                error_message=str(exc)[:500],
            )

class EvidenceRecapGenerateRunner:
    """Generate market recap snapshot via full M4 evidence pipeline.

    Pipeline: THS+CDP evidence → FusionEngine → LeaderEngine → ThemeEngine → RecapAggregation.
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        import json as _json
        from datetime import date as _date

        try:
            td = _date.fromisoformat(context.trade_date)
            import asyncpg

            conn = await asyncpg.connect(
                host="localhost", port=5432, database="stock_data_test",
                user="postgres", password="postgres", timeout=10,
            )
            try:
                from stock_processing_service.domain.services.evidence_fusion import (
                    EvidenceFusionEngine, EvidenceItem,
                )
                from stock_processing_service.domain.services.leader_scoring import (
                    LeaderScoringEngine,
                )
                from stock_processing_service.domain.services.theme_strength import (
                    ThemeStrengthEngine,
                )
                from stock_processing_service.domain.services.recap_aggregation import (
                    RecapAggregationService,
                )

                # Load THS evidence — use resolved theme_name from evidence table
                ths_rows = await conn.fetch(
                    "SELECT t.stock_code, t.stock_name, e.theme_name, t.reason_raw, t.reason_tags, e.evidence_text "
                    "FROM ths_hot_reason_snapshot t "
                    "JOIN stock_theme_reason_evidence e ON e.stock_code=t.stock_code AND e.trade_date=t.trade_date AND e.source_name='ths' "
                    "WHERE t.trade_date=$1", td)

                # Fallback: raw THS if no resolved evidence
                if not ths_rows:
                    ths_rows = await conn.fetch(
                        "SELECT stock_code, stock_name, reason_raw, reason_tags "
                        "FROM ths_hot_reason_snapshot WHERE trade_date=$1", td)

                # Load CDP evidence
                cdp_rows = await conn.fetch(
                    "SELECT subject_key, subject_name, description "
                    "FROM subject_history_staging WHERE rank_date=$1 AND source_type='jyhf_cdp'", td)

                # Build EvidenceItems
                evidence_items: list[EvidenceItem] = []
                seen = set()
                for r in ths_rows:
                    code = str(r["stock_code"] or "")
                    name = str(r["stock_name"] or "")
                    tags = r["reason_tags"] or []
                    # theme_name column exists only in JOIN result
                    theme = str(r["theme_name"] or "") if "theme_name" in r.keys() else ""
                    reason = str(r["evidence_text"] or "") if "evidence_text" in r.keys() else str(r["reason_raw"] or "")
                    if not code:
                        continue
                    if not theme and tags:
                        theme = str(tags[0])
                    if not theme:
                        continue
                    key = (code, theme)
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence_items.append(EvidenceItem(
                        source_name="ths", theme_name=theme,
                        stock_code=code, stock_name=name,
                        evidence_date=td, reason=reason, tags=list(tags),
                    ))

                # Build EvidenceItems from CDP
                for r in cdp_rows:
                    theme = str(r["subject_name"] or r["subject_key"] or "")
                    key = f"cdp:{theme}"
                    if key in seen:
                        continue
                    seen.add(key)
                    desc = str(r["description"] or "")[:100]
                    evidence_items.append(EvidenceItem(
                        source_name="jyhf", theme_name=theme,
                        stock_code=r["subject_key"] or theme,
                        stock_name=theme, evidence_date=td, reason=desc,
                    ))

                is_degraded = len(ths_rows) == 0
                reasons = []
                if is_degraded:
                    reasons.append("ths_hot_reason not collected")

                if not evidence_items:
                    return CollectionTaskResult(
                        status="failed",
                        current_label="无证据数据可融合",
                        error_message="no evidence items from THS or CDP",
                    )

                # Build board signals from THS snapshot
                board_signals: dict[str, dict] = {}
                raw_ths = await conn.fetch(
                    "SELECT stock_code, pct_chg FROM ths_hot_reason_snapshot WHERE trade_date=$1", td)
                for r in raw_ths:
                    code = str(r["stock_code"] or "")
                    pct = float(r["pct_chg"] or 0)
                    if code:
                        board_signals[code] = {
                            "is_limit_up": pct >= 9.5,
                            "pct_chg": pct,
                        }

                # Full pipeline: Evidence → Fusion → Leader → Theme → Recap
                fusion = EvidenceFusionEngine()
                leader_engine = LeaderScoringEngine(fusion)
                theme_engine = ThemeStrengthEngine()
                recap_service = RecapAggregationService()

                leaders = leader_engine.score(td, evidence_items, board_signals)
                themes = theme_engine.compute(td, leaders)
                recap = recap_service.aggregate(td, themes, leaders,
                                                evidence_items_count=len(evidence_items))

                row = recap_service.to_snapshot_row(recap)
                # Override diagnostics with collection-level info
                recap_data = row["recap_json"]
                recap_data["diagnostics"]["ths_rows"] = len(ths_rows)
                recap_data["diagnostics"]["cdp_rows"] = len(cdp_rows)
                recap_data["diagnostics"]["degraded"] = is_degraded
                recap_data["diagnostics"]["degraded_reasons"] = reasons

                await conn.execute(
                    """INSERT INTO market_recap_snapshot (trade_date, recap_json, source_trace_id)
                       VALUES ($1, $2::jsonb, $3)
                       ON CONFLICT (trade_date) DO UPDATE SET
                         recap_json=EXCLUDED.recap_json, source_trace_id=EXCLUDED.source_trace_id""",
                    td, _json.dumps(recap_data, ensure_ascii=False, default=str),
                    recap.source_trace_id,
                )

                return CollectionTaskResult(
                    status="success",
                    current_label=f"复盘生成完成: {len(recap.top_themes)} themes, {len(leaders)} leaders{' (降级)' if is_degraded else ''}",
                    progress_percent=100,
                    logs=[
                        f"ths={len(ths_rows)} cdp={len(cdp_rows)} evidence={len(evidence_items)}",
                        f"leaders={len(leaders)} themes={len(themes)} degraded={is_degraded}",
                    ],
                )
            finally:
                await conn.close()
        except Exception as exc:
            import traceback
            return CollectionTaskResult(
                status="failed",
                current_label=f"复盘生成失败: {type(exc).__name__}",
                error_message=str(exc)[:500],
            )
