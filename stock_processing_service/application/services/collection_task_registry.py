"""采集任务 Runner 协议与注册表。

目标：将 CollectionJobManager 从"subprocess 执行旧脚本命令"升级为
       "通过 Runner 协议统一调度"，逐步把旧脚本替换为服务模块调用。

使用方式：
  1. Planner 产出 plan.steps（每个 step 含 runner_key）
  2. JobManager 通过 registry.get(runner_key) 获取 Runner
  3. Runner.run(context) 执行任务

短期兼容：
  ScriptCommandRunner 内部仍执行旧脚本命令，确保旧链路不受影响。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class CollectionTaskContext:
    """Runner 执行上下文。"""
    trade_date: str
    payload: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    container: Any | None = None  # build_container() 返回的依赖容器
    project_root: Path | None = None
    python_bin: str | None = None
    # 兼容旧脚本：命令列表（ScriptCommandRunner 使用）
    commands: list[list[str]] | None = None
    # 动态进度回调：Runner 可调用以实时推送进度到前端日志
    progress_callback: Any | None = None


@dataclass
class CollectionTaskResult:
    """Runner 执行结果。"""
    status: str = "success"  # success / failed / skipped
    current_label: str = "完成"
    progress_percent: int = 100
    logs: list[str] = field(default_factory=list)
    error_message: str = ""


class CollectionTaskRunner(Protocol):
    """采集任务 Runner 协议。

    每个 Runner 实现一个具体的采集/构建任务。
    短期 ScriptCommandRunner 兼容旧脚本，
    长期逐步替换为服务化 Runner。
    """

    async def run(self, context: CollectionTaskContext) -> CollectionTaskResult:
        ...


# ── Runner 注册表 ──

class CollectionTaskRegistry:
    """Runner 注册表 — 按 runner_key 查找 Runner。"""

    def __init__(self) -> None:
        self._runners: dict[str, CollectionTaskRunner] = {}

    def register(self, key: str, runner: CollectionTaskRunner) -> None:
        if key in self._runners:
            raise ValueError(f"Duplicate runner key: {key}")
        self._runners[key] = runner

    def get(self, key: str) -> CollectionTaskRunner | None:
        return self._runners.get(key)


# ── 全局默认注册表 ──

_default_registry: CollectionTaskRegistry | None = None


def get_default_registry() -> CollectionTaskRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = CollectionTaskRegistry()
        _register_default_runners(_default_registry)
    return _default_registry


def _register_default_runners(registry: CollectionTaskRegistry) -> None:
    """注册默认 Runner。

    短期 ScriptCommandRunner 兼容旧脚本，
    PostMarketRecapRunner 是第一个服务化 Runner。
    """
    from stock_processing_service.application.services.collection_task_runners import (
        AuctionSignalRunner,
        AuctionSnapshotRunner,
        AuctionWatchUniverseRunner,
        BuildDragonTigerObjectRunner,
        BuildLeaderCandidateRunner,
        BuildLeaderLLMJudgementRunner,
        BuildLeaderLLMQueueRunner,
        BuildStockKlineJudgementsRunner,
        BuildStockAbnormalSignalRunner,
        CallLeaderLLMRunner,
        JyhfImportHistoryRunner,
        JyhfImportStockDailyRunner,
        JyhfLoadSubjectNodeStagingRunner,
        PostMarketPrerequisitesRunner,
        PostMarketReportContextRunner,
        JyhfSyncDetailsRunner,
        JyhfSyncHistoryRunner,
        JyhfSyncListsRunner,
        IndexKlineCollectRunner,
        JyhfSyncStockDetailsRunner,
        PostMarketRecapRunner,
        ProcessIsolatedRunner,
        ScriptCommandRunner,
        StockSnapshotBuildRunner,
        TushareKlineRunner,
    )
    registry.register("script.default", ScriptCommandRunner())
    registry.register("stock_snapshot.build", StockSnapshotBuildRunner())
    registry.register("stock.kline_judgements", BuildStockKlineJudgementsRunner())
    registry.register("leader_llm.queue", BuildLeaderLLMQueueRunner())
    registry.register("leader_llm.judgement", BuildLeaderLLMJudgementRunner())
    registry.register("leader_llm.call", CallLeaderLLMRunner())
    registry.register("leader_llm.candidate", BuildLeaderCandidateRunner())
    registry.register("jyhf.sync_lists", JyhfSyncListsRunner())
    registry.register("jyhf.load_staging", JyhfLoadSubjectNodeStagingRunner())
    registry.register("jyhf.sync_details", JyhfSyncDetailsRunner())
    registry.register("jyhf.sync_stock_details", JyhfSyncStockDetailsRunner())
    registry.register("jyhf.import_stock_daily", JyhfImportStockDailyRunner())
    registry.register("jyhf_history.sync", JyhfSyncHistoryRunner())
    registry.register("jyhf_history.import", JyhfImportHistoryRunner())
    registry.register("recap.prerequisites", PostMarketPrerequisitesRunner())
    registry.register("recap.snapshot", PostMarketRecapRunner())
    registry.register(
        "recap.market_environment_daily",
        PostMarketReportContextRunner("market", "新链市场环境"),
    )
    registry.register(
        "recap.theme_capital_flow_daily",
        PostMarketReportContextRunner("theme_capital_flow", "新链题材资金流"),
    )
    registry.register("abnormal.signal", BuildStockAbnormalSignalRunner())
    registry.register("dragon_tiger.object", BuildDragonTigerObjectRunner())
    registry.register("index_kline.collect", IndexKlineCollectRunner())
    registry.register("tushare.daily_bar", TushareKlineRunner())
    registry.register("auction.watch_universe", AuctionWatchUniverseRunner())
    registry.register("auction.snapshot_all", AuctionSnapshotRunner(universe_source="auction_watch_universe"))
    registry.register("auction.snapshot_w2s", AuctionSnapshotRunner(universe_source="weak_to_strong_candidates", max_stocks=120))
    registry.register("auction.signal", AuctionSignalRunner())

    # ── P2: 子进程隔离 Runner ──
    registry.register(
        "recap.prerequisites.isolated",
        ProcessIsolatedRunner(
            runner_key="recap.prerequisites",
            timeout_env="RECAP_PREREQ_WORKER_TIMEOUT_SEC",
            default_timeout_sec=900,
        ),
    )
    registry.register(
        "recap.snapshot.isolated",
        ProcessIsolatedRunner(
            runner_key="recap.snapshot",
            timeout_env="RECAP_SNAPSHOT_WORKER_TIMEOUT_SEC",
            default_timeout_sec=1800,
        ),
    )


__all__ = [
    "CollectionTaskContext",
    "CollectionTaskResult",
    "CollectionTaskRunner",
    "CollectionTaskRegistry",
    "get_default_registry",
]
