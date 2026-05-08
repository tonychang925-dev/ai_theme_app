"""采集任务 Runner 实现。

- ScriptCommandRunner：兼容旧脚本（subprocess 执行）
- PostMarketRecapRunner：服务化 recap（直接调 BuildPostMarketRecapJob）
"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from uuid import uuid4

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
    """异动信号检测 Runner — 直接调用旧链服务，消除子进程。

    后续可替换为完全 Gateway-based 的新链服务。
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            import sys
            from pathlib import Path as _Path

            trade_date = context.trade_date
            payload = context.payload
            abnormal_filters = payload.get("abnormal_filters") or {}
            options = payload.get("options") or {}
            proj_root = context.project_root or _Path("/Users/admin/Desktop/ai_theme_app")

            ns = argparse.Namespace()
            ns.trade_date = trade_date
            ns.min_turnover_rate = float(options.get("min_turnover_rate", 3.0))
            ns.min_composite_score = float(options.get("min_composite_score", 40.0))
            ns.max_main_net_rank = int(options.get("max_main_net_rank", 200))
            ns.limit = int(options.get("limit", 0))
            ns.require_turnover = bool(abnormal_filters.get("turnover_rate"))
            ns.require_main_net_inflow = bool(abnormal_filters.get("main_net_inflow"))
            ns.require_hot_money_buy = bool(abnormal_filters.get("hot_money_buy"))
            ns.require_institution_buy = bool(abnormal_filters.get("institution_buy"))
            ns.require_tail_rush = bool(abnormal_filters.get("tail_rush"))
            ns.token = context.env.get("TUSHARE_TOKEN", "")
            ns.force_refresh_tail_auction = False
            ns.details_root = str(proj_root / "theme_data_complete" / "stock_details")
            ns.kline_root = str(proj_root / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar")

            # 保存原始 sys.argv，注入脚本期望的参数
            saved_argv = sys.argv
            sys.argv = [
                "build_stock_abnormal_signal.py",
                "--trade-date", trade_date,
                "--min-turnover-rate", str(ns.min_turnover_rate),
                "--min-composite-score", str(ns.min_composite_score),
            ]
            try:
                from database_service.scripts.build_stock_abnormal_signal import main_async
                exit_code = await main_async()
            finally:
                sys.argv = saved_argv

            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"异动信号检测完成 (exit={exit_code})",
                logs=[f"abnormal_signal exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="异动信号检测异常",
                error_message=str(e),
            )


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

        result = await job.execute(
            trade_date=trade_date_val,
            snapshot_version="collection.post_market_recap.v1",
            batch_id=uuid4().hex[:12],
            trace_id=uuid4().hex[:12],
            lookback_days=7,
        )

        logs = [
            f"recap status={result.status}",
            f"recap affected_rows={result.affected_rows}",
        ]

        return CollectionTaskResult(
            status="success" if result.status == "ok" else "failed",
            current_label=f"盘后复盘快照生成完成 ({result.status})",
            logs=logs,
        )
