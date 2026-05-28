"""采集任务 Runner 实现。

- ScriptCommandRunner：兼容旧脚本（subprocess 执行）
- PostMarketRecapRunner：服务化 recap（直接调 BuildPostMarketRecapJob）
- ProcessIsolatedRunner：子进程隔离执行重任务
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
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

# ── 注册表中已有的 Runner key ──
# "script.default"    → ScriptCommandRunner (兼容旧脚本)
# "recap.snapshot"    → PostMarketRecapRunner (服务化 recap)
# "abnormal.signal"   → BuildStockAbnormalSignalRunner (服务化异动检测)


class ScriptCommandRunner:
    """兼容旧脚本的 Runner。

    内部通过 subprocess 执行预定命令列表。
    后续逐个替换为服务化 Runner。
    """

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
    """异动信号检测 Runner — 委托到 BuildStockAbnormalSignalJob（新链 Job 架构）。"""

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
    """个股K线位置与形态判断 Runner — in-process 调用脚本入口。"""

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
    """新链盘后报告上下文 Runner。

    该 Runner 不写旧表；它只触发 stock_processing_service 新链上下文查询，
    用于在 recap.snapshot 前暴露市场环境/题材资金流的采集状态。
    最终 report 仍由 BuildPostMarketRecapJob 写入 post_market_recap_snapshot。
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
    """龙虎榜对象构建 Runner — 新链 Job 架构。"""

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
            if result.status == "skipped_no_data" and warnings:
                return CollectionTaskResult(
                    status="failed",
                    current_label=f"龙虎榜未生成 ({warnings[0]})",
                    logs=[
                        f"dragon_tiger status={result.status} rows={result.affected_rows}",
                        f"dragon_tiger metrics={metrics}",
                    ],
                    error_message=str(warnings[0]),
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


class AuctionSnapshotRunner:
    """竞价快照 Runner — 委托到 BuildAuctionSnapshotJob（新链 Job 架构）。"""

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
            return CollectionTaskResult(
                status="success" if result.status == "ok" else "failed",
                current_label=f"竞价快照完成 ({result.status})",
                logs=[f"auction_snapshot status={result.status}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价快照异常", error_message=str(e))


class JyhfSyncListsRunner:
    """JYHF 题材列表同步 Runner — in-process 调用 sync_jyhf_to_local（semi-service 模式）。"""

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
    """JYHF 题材节点入库 Runner — in-process 调用 load_subject_node_staging（semi-service 模式）。"""

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
    """JYHF 题材详情同步 Runner — in-process 调用 sync_jyhf_to_local（semi-service 模式）。"""

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
    """JYHF 股票详情同步 Runner — in-process 调用 sync_jyhf_to_local（semi-service 模式）。"""

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
    """JYHF 股票日快照导入 Runner — in-process 调用 import_jyhf_stock_daily_incremental（semi-service 模式）。"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            ns = argparse.Namespace()
            ns.subjects_file = None
            ns.batch_id = None
            ns.trade_date = context.trade_date
            ns.data_root = str(context.project_root / "theme_data_complete") if context.project_root else "/Users/admin/Desktop/ai_theme_app/theme_data_complete"
            from database_service.scripts.import_jyhf_stock_daily_incremental import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"JYHF 股票日快照导入完成 (exit={exit_code})",
                logs=[f"jyhf_import_stock_daily exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="JYHF 股票日快照导入异常", error_message=str(e))


class JyhfSyncHistoryRunner:
    """JYHF 历史事件同步 Runner — in-process 调用 sync_jyhf_to_local（semi-service 模式）。"""

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
    """JYHF 历史事件导入 Runner — in-process 调用 import_jyhf_history_incremental（semi-service 模式）。"""

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
    """竞价信号 Runner — 委托到 BuildAuctionSignalJob（新链 Job 架构）。"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        if context.container is None:
            return CollectionTaskResult(status="failed", current_label="容器未注入", error_message="container is None")
        try:
            from datetime import date as _date
            trade_date_val = _date.fromisoformat(context.trade_date)
            job = context.container.build_auction_signal
            result = await job.execute(trade_date=trade_date_val)
            return CollectionTaskResult(
                status="success" if result.status == "ok" else "failed",
                current_label=f"竞价信号生成完成 ({result.status})",
                logs=[f"auction_signal status={result.status}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价信号生成异常", error_message=str(e))


class AuctionWatchUniverseRunner:
    """竞价观察池构建 Runner — 新链 Job 架构。"""

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


class TushareKlineRunner:
    """Tushare K线采集 Runner — 直接拉取 API → Gateway 写入，不经过本地 JSONL。"""

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

            return CollectionTaskResult(
                status="success" if result.status.startswith("ok") else "failed",
                current_label=f"Tushare日线采集完成 ({result.status})",
                logs=[f"tushare_kline status={result.status} rows={result.affected_rows}"] + list(result.warnings or []),
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed", current_label="Tushare日线采集异常", error_message=str(e),
            )


class BuildLeaderLLMQueueRunner:
    """龙头候选 LLM 审查队列 Runner — 进程内调用旧链服务（semi-service 模式）。"""

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
    """龙头候选 LLM 研判 Runner — 进程内调用旧链服务（semi-service 模式）。"""

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
    """龙头候选 LLM 调用 Runner — 进程内调用旧链服务（semi-service 模式）。"""

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
    """龙头候选构建 Runner — 进程内调用旧链服务（semi-service 模式）。"""

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
    """服务化盘后复盘 Runner。

    直接调用 BuildPostMarketRecapJob.execute()，不再启动脚本子进程。
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


# ── P2: 子进程隔离 Runner ──

class ProcessIsolatedRunner:
    """P2: 将重任务 runner 隔离到独立子进程，不阻塞 SPS 主进程。

    子进程执行真实 runner_key，主进程只做 stdout 读取和超时管理。
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
