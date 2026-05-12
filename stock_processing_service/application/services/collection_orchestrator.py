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

        if task_key == "jyhf":
            return CollectionTaskPlan(
                commands=[
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "sync_jyhf_to_local.py"),
                            "--types",
                            "lists",
                        ],
                        initial_percent=5,
                        success_percent=15,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "load_subject_node_staging.py"),
                        ],
                        initial_percent=15,
                        success_percent=25,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "sync_jyhf_to_local.py"),
                            "--use-latest-list-subjects",
                            "--types",
                            "details",
                        ],
                        initial_percent=25,
                        success_percent=45,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "sync_jyhf_to_local.py"),
                            "--use-latest-list-subjects",
                            "--types",
                            "stock_details",
                            "--trade-date",
                            trade_date,
                            "--resume",
                            "--skip-existing",
                        ],
                        initial_percent=45,
                        success_percent=85,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "import_jyhf_stock_daily_incremental.py"),
                            "--trade-date",
                            trade_date,
                        ],
                        initial_percent=85,
                        success_percent=100,
                    ),
                ]
            )

        if task_key == "jyhf_history":
            subject_keys = self._latest_jyhf_subject_keys()
            if not subject_keys:
                raise RuntimeError("缺少最新题材列表：请先执行股票快照日采集，或确认 theme_data_complete/lists/full_theme_list.sync.jsonl 已生成。")
            subjects_file = self._write_subject_keys_file(trade_date, subject_keys)
            batch_id = f"collection_jyhf_history_{trade_date.replace('-', '')}"
            return CollectionTaskPlan(
                commands=[
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "sync_jyhf_to_local.py"),
                            "--use-latest-list-subjects",
                            "--types",
                            "history",
                            "--history-mode",
                            "incremental",
                            "--history-backfill-date",
                            trade_date,
                            "--batch-id",
                            batch_id,
                        ],
                        initial_percent=10,
                        success_percent=55,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "import_jyhf_history_incremental.py"),
                            "--subjects-file",
                            str(subjects_file),
                            "--batch-id",
                            batch_id,
                            "--mode",
                            "append",
                        ],
                        initial_percent=55,
                        success_percent=100,
                    ),
                ]
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

        if task_key == "abnormal_signal":
            return CollectionTaskPlan(
                runner_key="abnormal.signal",
                pre_logs=[self.format_abnormal_filter_summary(payload)],
            )

        if task_key == "strong_stock_watch":
            return CollectionTaskPlan(
                terminal_status="success",
                terminal_label="由 recap_snapshot 新链任务统一生成",
                pre_logs=["强势股池独立旧链脚本已禁用，改由 recap_snapshot 新链任务统一生成"],
            )

        if task_key == "leader_llm":
            deepseek_api_key = env.get("DEEPSEEK_API_KEY", "").strip()
            leader_llm_max_themes = str(payload.get("leader_llm_max_themes", 5))
            if not deepseek_api_key:
                return CollectionTaskPlan(
                    terminal_status="skipped",
                    terminal_label="未配置 DEEPSEEK_API_KEY，已跳过",
                    pre_logs=["未配置 DEEPSEEK_API_KEY，跳过龙头候选 LLM 裁决"],
                )
            return CollectionTaskPlan(
                commands=[
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "build_theme_leader_llm_queue.py"),
                            "--trade-date",
                            trade_date,
                        ],
                        initial_percent=10,
                        success_percent=30,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "build_theme_leader_llm_judgement.py"),
                            "--trade-date",
                            trade_date,
                            "--only-queued",
                            "--limit-themes",
                            leader_llm_max_themes,
                        ],
                        initial_percent=30,
                        success_percent=55,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "call_theme_leader_llm.py"),
                            "--trade-date",
                            trade_date,
                            "--limit",
                            leader_llm_max_themes,
                            "--limit-themes",
                            leader_llm_max_themes,
                            "--only-queued",
                            "--only-pending",
                        ],
                        initial_percent=55,
                        success_percent=80,
                    ),
                    CollectionCommand(
                        [
                            self._python_bin,
                            str(self._project_root / "database_service" / "scripts" / "build_theme_leader_candidate.py"),
                            "--trade-date",
                            trade_date,
                        ],
                        initial_percent=80,
                        success_percent=100,
                    ),
                ]
            )

        if task_key == "recap_snapshot":
            # 两步：
            #   Step 1: recap.snapshot — 新链 W2S 数据生成 (BuildPostMarketRecapJob)
            #   Step 2: recap.report   — 旧链 LLM 报告生成 (RecapService → upsert report 到快照)
            return CollectionTaskPlan(
                pre_logs=["recap_snapshot: Step1 新链数据生成 + Step2 LLM 报告"],
                steps=[
                    CollectionTaskStep(
                        key="recap_data",
                        runner_key="recap.snapshot",
                        label="盘后复盘数据生成",
                    ),
                    CollectionTaskStep(
                        key="recap_report",
                        runner_key="recap.report",
                        label="盘后复盘 LLM 报告生成",
                    ),
                ],
            )

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
