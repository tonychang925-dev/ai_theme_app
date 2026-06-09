from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
PYTHON_BIN = str(PROJECT_ROOT / ".venv" / "bin" / "python")


@dataclass(frozen=True)
class CollectionCommand:
    cmd: list[str]
    initial_percent: int = 5
    success_percent: int = 100


@dataclass(frozen=True)
class CollectionTaskStep:
    """采集任务中的单步——可以是 Runner 或脚本命令。"""
    key: str = ""
    runner_key: str = ""
    commands: list[CollectionCommand] = field(default_factory=list)
    label: str = ""


@dataclass(frozen=True)
class CollectionTaskPlan:
    # 多步模式（推荐）：逐 step 执行，支持混合 Runner + 脚本
    steps: list[CollectionTaskStep] = field(default_factory=list)
    # 旧兼容模式
    commands: list[CollectionCommand] = field(default_factory=list)
    pre_logs: list[str] = field(default_factory=list)
    terminal_status: str | None = None
    terminal_label: str = ""
    runner_key: str = ""


class CollectionCommandPlanner:
    """Builds collection task command plans.

    This is the first service boundary for the old script-based collection
    flow. It intentionally preserves the existing commands while moving
    business command selection out of the job state manager.
    """

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        python_bin: str = PYTHON_BIN,
    ) -> None:
        self._project_root = project_root
        self._python_bin = python_bin

    def build_task_plan(
        self,
        *,
        task_key: str,
        trade_date: str,
        payload: dict[str, Any],
        env: dict[str, str],
    ) -> CollectionTaskPlan:
        options = payload.get("options") or {}
        abnormal_filters = payload.get("abnormal_filters") or {}
        tushare_pause = str(payload.get("tushare_pause_seconds", 0.1))
        min_turnover = str(payload.get("min_turnover_rate", 3.0))
        min_score = str(payload.get("min_composite_score", 40.0))

        if task_key == "stock_snapshot":
            snapshot_opts = options.get("stock_snapshot") or {}
            provider = snapshot_opts.get("provider", "jyhf")
            on_existing = snapshot_opts.get("on_existing", "skip")
            force = snapshot_opts.get("force", False)
            return CollectionTaskPlan(
                pre_logs=[
                    f"stock_snapshot: provider={provider} on_existing={on_existing} force={force}",
                    "stock_snapshot: 统一入口 → Orchestrator 自动选择 Producer",
                ],
                steps=[
                    CollectionTaskStep(
                        key="stock_snapshot_build",
                        runner_key="stock_snapshot.build",
                        label=f"股票快照采集 ({provider})",
                    ),
                ],
            )

        if task_key == "subject_rank":
            rank_opts = options.get("subject_rank") or {}
            provider = rank_opts.get("provider", "jyhf")
            on_existing = rank_opts.get("on_existing", "skip")
            force = rank_opts.get("force", False)
            return CollectionTaskPlan(
                pre_logs=[
                    f"subject_rank: provider={provider} on_existing={on_existing} force={force}",
                    "subject_rank: 从 subject_stock_daily_snapshot 聚合 / JYHF history JSONL 提取",
                ],
                steps=[
                    CollectionTaskStep(
                        key="subject_rank_build",
                        runner_key="subject_rank.build",
                        label=f"题材热度排名 ({provider})",
                    ),
                ],
            )

        if task_key == "jyhf":
            return CollectionTaskPlan(
                pre_logs=["jyhf: Step1 列表同步 + Step2 节点入库 + Step3 股票日快照采集入库（API→DB）"],
                steps=[
                    CollectionTaskStep(key="jyhf_lists", runner_key="jyhf.sync_lists", label="JYHF 题材列表同步"),
                    CollectionTaskStep(key="jyhf_staging", runner_key="jyhf.load_staging", label="JYHF 题材节点入库"),
                    CollectionTaskStep(key="jyhf_import", runner_key="jyhf.import_stock_daily", label="JYHF 股票日快照采集入库"),
                ],
            )

        if task_key == "jyhf_history":
            subject_keys = self._latest_jyhf_subject_keys()
            if not subject_keys:
                raise RuntimeError("缺少最新题材列表：请先执行股票快照日采集，或确认 theme_data_complete/lists/full_theme_list.sync.jsonl 已生成。")
            subjects_file = self._write_subject_keys_file(trade_date, subject_keys)
            return CollectionTaskPlan(
                pre_logs=["jyhf_history: Step1 历史同步 + Step2 历史导入（全部 in-process）"],
                steps=[
                    CollectionTaskStep(key="jyhf_hist_sync", runner_key="jyhf_history.sync", label="JYHF 历史事件同步"),
                    CollectionTaskStep(key="jyhf_hist_import", runner_key="jyhf_history.import", label="JYHF 历史事件导入"),
                ],
            )

        if task_key == "tushare_kline":
            tushare_token = str(env.get("TUSHARE_TOKEN", "")).strip().strip("\"'").strip()
            if not tushare_token:
                raise RuntimeError("缺少 Tushare token：请设置环境变量 TUSHARE_TOKEN，或在项目 .env/.env.local 中配置。")
            return CollectionTaskPlan(
                pre_logs=["Tushare K线已切换到 BuildTushareDailyBarJob (API→Gateway→DB)，不再经过本地JSONL中转"],
                steps=[
                    # Step 1: K线采集 — 完全服务化（Tushare API → Gateway → DB）
                    CollectionTaskStep(
                        key="kline",
                        runner_key="tushare.daily_bar",
                        label="Tushare日线采集 (API→DB)",
                    ),
                    # Step 2: 竞价观察池 — 已服务化
                    CollectionTaskStep(
                        key="auction_watch",
                        runner_key="auction.watch_universe",
                        label="竞价观察池构建 (服务化)",
                    ),
                    CollectionTaskStep(
                        key="auction_snapshot_all",
                        runner_key="auction.snapshot_all",
                        label="竞价快照(全量)",
                    ),
                    CollectionTaskStep(
                        key="auction_snapshot_w2s",
                        runner_key="auction.snapshot_w2s",
                        label="竞价快照(弱转强候选)",
                    ),
                    CollectionTaskStep(
                        key="auction_signal",
                        runner_key="auction.signal",
                        label="竞价信号生成",
                    ),
                ],
            )

        if task_key == "dragon_tiger":
            return CollectionTaskPlan(runner_key="dragon_tiger.object")

        if task_key == "index_kline":
            return CollectionTaskPlan(runner_key="index_kline.collect")

        if task_key == "abnormal_signal":
            return CollectionTaskPlan(
                runner_key="abnormal.signal",
                pre_logs=[self.format_abnormal_filter_summary(payload)],
            )

        if task_key == "strong_stock_watch":
            return CollectionTaskPlan(
                terminal_status="skipped",
                terminal_label="已废弃：强势股跟踪池由 recap_snapshot(force_rebuild) 统一生成",
                pre_logs=["strong_stock_watch 已禁用，请使用 recap_snapshot force_rebuild_truth_source=true 生成 Layer C"],
            )

        if task_key == "leader_llm":
            deepseek_api_key = env.get("DEEPSEEK_API_KEY", "").strip()
            if not deepseek_api_key:
                return CollectionTaskPlan(
                    terminal_status="skipped",
                    terminal_label="未配置 DEEPSEEK_API_KEY，已跳过",
                    pre_logs=["未配置 DEEPSEEK_API_KEY，跳过龙头候选 LLM 裁决"],
                )
            return CollectionTaskPlan(
                pre_logs=["leader_llm: Step1 队列 + Step2 研判 + Step3 LLM调用 + Step4 候选构建（全部 in-process）"],
                steps=[
                    CollectionTaskStep(
                        key="leader_llm_queue",
                        runner_key="leader_llm.queue",
                        label="龙头候选 LLM 审查队列构建",
                    ),
                    CollectionTaskStep(
                        key="leader_llm_judgement",
                        runner_key="leader_llm.judgement",
                        label="龙头候选 LLM 研判",
                    ),
                    CollectionTaskStep(
                        key="leader_llm_call",
                        runner_key="leader_llm.call",
                        label="龙头候选 LLM 调用",
                    ),
                    CollectionTaskStep(
                        key="leader_llm_candidate",
                        runner_key="leader_llm.candidate",
                        label="龙头候选构建",
                    ),
                ],
            )

        if task_key == "recap_snapshot":
            # P0: Report Layer — 默认只读已有对象生成 DailyReview。
            # Truth Source 生产步骤 (kline/prereqs/abnormal) 仅 force_rebuild_truth_source=true 时触发。
            force_truth = bool(options.get("force_rebuild_truth_source", False))
            steps: list[CollectionTaskStep] = []

            if force_truth:
                steps.append(CollectionTaskStep(
                    key="stock_kline_judgements",
                    runner_key="stock.kline_judgements",
                    label="个股K线位置与形态判断",
                ))
                steps.append(CollectionTaskStep(
                    key="recap_prerequisites",
                    runner_key="recap.prerequisites.isolated",
                    label="新链盘后前置构建",
                ))
                steps.extend([
                    CollectionTaskStep(
                        key="market_environment_daily",
                        runner_key="recap.market_environment_daily",
                        label="新链市场环境检查",
                    ),
                    CollectionTaskStep(
                        key="theme_capital_flow_daily",
                        runner_key="recap.theme_capital_flow_daily",
                        label="新链题材资金流检查",
                    ),
                    CollectionTaskStep(
                        key="money_flow_enhanced",
                        runner_key="script.default",
                        commands=[
                            CollectionCommand(cmd=[
                                self._python_bin,
                                str(self._project_root / "database_service/scripts/build_money_flow_enhanced.py"),
                                "--trade-date", trade_date,
                            ])
                        ],
                        label="资金行为增强",
                    ),
                ])
                steps.append(CollectionTaskStep(
                    key="abnormal_signal",
                    runner_key="abnormal.signal",
                    label="异动信号检测",
                ))
                pre_logs = [
                    "recap_snapshot is deprecated, use post_market_recap_generate",
                    "recap_snapshot: FORCE REBUILD truth source + report",
                ]
            else:
                pre_logs = [
                    "recap_snapshot is deprecated, use post_market_recap_generate",
                    "recap_snapshot: DailyReview read-model only",
                ]

            steps.append(CollectionTaskStep(
                key="recap_data",
                runner_key="recap.snapshot.isolated",
                label="盘后复盘最终快照生成",
            ))

            return CollectionTaskPlan(pre_logs=pre_logs, steps=steps)

        return CollectionTaskPlan(terminal_status="skipped", terminal_label="未知任务，已跳过")

    @staticmethod
    def format_abnormal_filter_summary(payload: dict[str, Any]) -> str:
        abnormal_filters = payload.get("abnormal_filters") or {}
        enabled: list[str] = []
        if abnormal_filters.get("turnover_rate"):
            enabled.append("换手率")
        if abnormal_filters.get("main_net_inflow"):
            enabled.append("资金流入")
        if abnormal_filters.get("hot_money_buy"):
            enabled.append("游资买入")
        if abnormal_filters.get("institution_buy"):
            enabled.append("机构买入")
        if abnormal_filters.get("tail_rush"):
            enabled.append("尾盘抢筹")
        if not enabled:
            enabled.append("默认资金聚焦口径")
        min_turnover = payload.get("min_turnover_rate", 3.0)
        min_score = payload.get("min_composite_score", 40.0)
        return (
            f"异动过滤策略：{' / '.join(enabled)}"
            f"｜最小换手率={min_turnover}"
            f"｜最小综合分={min_score}"
        )

    def _latest_jyhf_subject_keys(self) -> list[str]:
        candidate_files = [
            self._project_root / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl",
            self._project_root / "theme_data_complete" / "full_theme_list.sync.jsonl",
        ]
        list_file = next((path for path in candidate_files if path.exists()), None)
        if list_file is None:
            return []
        subject_keys: list[str] = []
        try:
            with list_file.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    subject_id = obj.get("subjectId") or obj.get("id") or obj.get("bizKey")
                    if subject_id in (None, ""):
                        continue
                    subject_keys.append(str(subject_id).strip())
        except Exception:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for key in subject_keys:
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

    def _write_subject_keys_file(self, trade_date: str, subject_keys: list[str]) -> Path:
        tmp_dir = self._project_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / f"collection_history_subject_keys_{trade_date.replace('-', '')}.txt"
        path.write_text("\n".join(subject_keys) + ("\n" if subject_keys else ""), encoding="utf-8")
        return path
