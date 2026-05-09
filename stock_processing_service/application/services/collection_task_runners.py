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

            from database_service.scripts.build_stock_abnormal_signal import main_async
            exit_code = await main_async(args=ns)

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
    """竞价快照 Runner — 进程内调用旧链服务（semi-service 模式）。"""

    def __init__(self, universe_source: str = "auction_watch_universe", max_stocks: int = 0) -> None:
        self._universe_source = universe_source
        self._max_stocks = max_stocks

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse

            token = context.env.get("TUSHARE_TOKEN", "")
            if not token:
                return CollectionTaskResult(status="failed", current_label="缺少 Tushare token", error_message="TUSHARE_TOKEN not set")

            ns = argparse.Namespace()
            ns.trade_date = context.trade_date
            ns.token = token
            ns.allow_online_fetch = True
            ns.force_refresh = True
            ns.universe_source = self._universe_source
            ns.max_stocks = self._max_stocks
            ns.timeline_json = str(context.payload.get("auction_timeline_json", "") or "")
            ns.source_trade_date = ""
            ns.top_k = int(context.payload.get("auction_top_k", 20))
            ns.proxy_ratio = float(context.payload.get("auction_proxy_ratio", 0.08))

            from database_service.scripts.build_pre_market_auction_snapshot import main_async
            exit_code = await main_async(args=ns)

            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"竞价快照完成 (source={self._universe_source}, exit={exit_code})",
                logs=[f"auction_snapshot source={self._universe_source} exit_code={exit_code}"],
            )
        except Exception as e:
            return CollectionTaskResult(status="failed", current_label="竞价快照异常", error_message=str(e))


class AuctionSignalRunner:
    """竞价信号 Runner — 进程内调用旧链服务（semi-service 模式）。"""

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            import argparse
            ns = argparse.Namespace()
            ns.trade_date = context.trade_date
            ns.top_k = 40
            ns.source_trade_date = ""
            from database_service.scripts.build_pre_market_auction_signal import main_async
            exit_code = await main_async(args=ns)
            return CollectionTaskResult(
                status="success" if exit_code == 0 else "failed",
                current_label=f"竞价信号生成完成 (exit={exit_code})",
                logs=[f"auction_signal exit_code={exit_code}"],
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


class PostMarketRecapReportRunner:
    """盘后复盘 LLM 报告生成 Runner。

    在新链 BuildPostMarketRecapJob 完成 W2S 数据生成后，
    调用旧链 RecapService 生成结构化 report 字段并 upsert 到现有快照中，
    确保 frontend 盘后复盘页面保持旧格式兼容。
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        try:
            from stock_service.repositories.report_repository import ReportRepository
            from stock_service.config import StockServiceConfig
            from stock_service.services.recap_service import RecapService
            import asyncpg
            import json
            from datetime import date as _date

            trade_date = context.trade_date
            cfg = StockServiceConfig(postgres_database="stock_data_test")
            repo = ReportRepository(cfg)
            await repo.initialize()
            try:
                service = RecapService(repo)
                report = await service.build_post_market_report(trade_date)

                conn = await asyncpg.connect(
                    host=cfg.postgres_host, port=cfg.postgres_port,
                    database=cfg.postgres_database, user=cfg.postgres_user,
                    password=cfg.postgres_password,
                )
                try:
                    trade_date_obj = _date.fromisoformat(trade_date)
                    existing = await conn.fetchrow(
                        "SELECT payload FROM post_market_recap_snapshot WHERE trade_date = $1",
                        trade_date_obj,
                    )
                    existing_payload = json.loads(existing["payload"]) if existing else {}

                    existing_payload["report"] = {
                        "report_type": report.report_type,
                        "trade_date": report.trade_date,
                        "title": report.title,
                        "summary": report.summary,
                        "highlights": list(report.highlights or []),
                        "sections": [
                            {"heading": heading, "items": list(items or [])}
                            for heading, items in list(report.sections or [])
                        ],
                        "metadata": dict(getattr(report, "metadata", {}) or {}),
                    }

                    await conn.execute(
                        """UPDATE post_market_recap_snapshot
                           SET payload = $1::jsonb, updated_at = NOW()
                           WHERE trade_date = $2""",
                        json.dumps(existing_payload, ensure_ascii=False, default=str),
                        trade_date_obj,
                    )
                finally:
                    await conn.close()
            finally:
                await repo.close()

            section_count = len(report.sections or [])
            highlight_count = len(report.highlights or [])
            return CollectionTaskResult(
                status="success",
                current_label=f"盘后复盘 LLM 报告生成完成 ({section_count} 章节, {highlight_count} 要点)",
                logs=[f"recap_report sections={section_count} highlights={highlight_count}"],
            )
        except Exception as e:
            return CollectionTaskResult(
                status="failed",
                current_label="盘后复盘报告生成异常",
                error_message=str(e),
            )
