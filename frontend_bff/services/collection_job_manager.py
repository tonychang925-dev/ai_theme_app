from __future__ import annotations

import asyncio
import os
import re
import signal
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo
import json


PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
PYTHON_BIN = str(PROJECT_ROOT / ".venv" / "bin" / "python")


def _read_cdp_token_file() -> str:
    """Read JYHF auth token from CDP-extracted token file (replaces mitmweb)."""
    try:
        with open("/tmp/jyhf_auth_token.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return str(data.get("token", "")).strip()
    except Exception:
        return ""


@dataclass
class CollectionTaskState:
    key: str
    title: str
    status: str = "pending"
    progress_percent: int = 0
    current_label: str = ""
    error_message: str = ""


@dataclass
class CollectionJob:
    job_id: str
    trade_date: str
    payload: dict[str, Any]
    status: str = "idle"
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    progress_percent: int = 0
    can_cancel: bool = False
    can_continue: bool = False
    logs: list[str] = field(default_factory=list)
    tasks: list[CollectionTaskState] = field(default_factory=list)
    last_error: Optional[dict[str, str]] = None
    cancel_requested: bool = False
    running_task: Optional[asyncio.Task] = None
    active_process: Optional[asyncio.subprocess.Process] = None
    next_step_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "trade_date": self.trade_date,
            "status": self.status,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "progress_percent": self.progress_percent,
            "can_cancel": self.can_cancel,
            "can_continue": self.can_continue,
            "logs": self.logs[-300:],
            "tasks": [asdict(task) for task in self.tasks],
            "last_error": self.last_error,
        }


class CollectionJobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, CollectionJob] = {}

    def availability(self, trade_date: str | None = None) -> dict[str, Any]:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        target_date: date | None = None
        if trade_date:
            try:
                target_date = datetime.fromisoformat(trade_date).date()
            except ValueError:
                target_date = None
        today = now.date()
        if target_date is not None and target_date < today:
            allowed = True
            message = "历史交易日可直接启动采集"
        elif target_date is not None and target_date > today:
            allowed = False
            message = "未来交易日不可启动采集"
        else:
            allowed = (now.hour > 16) or (now.hour == 16 and now.minute >= 30)
            message = "可启动日采集" if allowed else "仅当天数据需在16:30后采集"
        return {
            "server_time": now.isoformat(),
            "allowed": allowed,
            "message": message,
            "trade_date": trade_date,
        }

    def _build_tasks(self, payload: dict[str, Any]) -> list[CollectionTaskState]:
        options = payload.get("options") or {}
        tasks: list[CollectionTaskState] = []
        if options.get("jyhf", True):
            tasks.append(CollectionTaskState(key="jyhf", title="股票快照日采集"))
        if options.get("jyhf_history", False):
            tasks.append(CollectionTaskState(key="jyhf_history", title="题材事件集中采集"))
        if options.get("tushare_kline", True):
            tasks.append(CollectionTaskState(key="tushare_kline", title="Tushare日K线+盘前竞价采集"))
        if options.get("dragon_tiger", True):
            tasks.append(CollectionTaskState(key="dragon_tiger", title="龙虎榜构建"))
        if options.get("abnormal_signal", True):
            tasks.append(CollectionTaskState(key="abnormal_signal", title="异动股票构建"))
        if options.get("strong_stock_watch", True):
            tasks.append(CollectionTaskState(key="strong_stock_watch", title="强势股跟踪池更新"))
        if options.get("leader_llm", True):
            tasks.append(CollectionTaskState(key="leader_llm", title="龙头候选LLM裁决"))
        if options.get("recap_snapshot", True):
            tasks.append(CollectionTaskState(key="recap_snapshot", title="盘后复盘快照生成"))
        return tasks

    def _append_log(self, job: CollectionJob, message: str) -> None:
        stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%H:%M:%S")
        job.logs.append(f"[{stamp}] {message}")
        if len(job.logs) > 500:
            job.logs = job.logs[-500:]

    def _load_env_file_values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env.theme", PROJECT_ROOT / ".env"):
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
                    if key and value and key not in result:
                        result[key] = value
            except Exception:
                continue
        return result

    def create_job(self, trade_date: str, payload: dict[str, Any]) -> CollectionJob:
        job_id = f"pm_collect_{trade_date.replace('-', '')}_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H%M%S')}"
        tasks = self._build_tasks(payload)
        job = CollectionJob(
            job_id=job_id,
            trade_date=trade_date,
            payload=payload,
            status="running",
            total_steps=len(tasks),
            can_cancel=True,
            tasks=tasks,
        )
        self._append_log(job, "创建采集任务")
        options = payload.get("options") or {}
        if not options.get("leader_llm", True):
            self._append_log(job, "未勾选 龙头候选LLM裁决，本次采集将跳过该步骤")
        if not options.get("recap_snapshot", True):
            self._append_log(job, "未勾选 盘后复盘快照生成，本次采集将跳过该步骤")
        if options.get("recap_snapshot", True) and not options.get("auto_build_v2_if_missing", True):
            self._append_log(job, "已关闭 v2周期缺失自动补建：盘后复盘将严格依赖当日v2数据")
        self.jobs[job_id] = job
        job.running_task = asyncio.create_task(self._run_job(job))
        return job

    def get_job(self, job_id: str) -> Optional[CollectionJob]:
        return self.jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> Optional[CollectionJob]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        job.cancel_requested = True
        job.can_cancel = False
        self._append_log(job, "收到取消请求")
        process = job.active_process
        if process and process.returncode is None:
            process.send_signal(signal.SIGTERM)
        return job

    async def continue_job(self, job_id: str) -> Optional[CollectionJob]:
        job = self.jobs.get(job_id)
        if not job or not job.can_continue:
            return job
        job.status = "running"
        job.can_cancel = True
        job.can_continue = False
        job.last_error = None
        self._append_log(job, "从失败步骤继续执行")
        job.running_task = asyncio.create_task(self._run_job(job, start_index=job.next_step_index))
        return job

    def _update_overall_progress(self, job: CollectionJob) -> None:
        job.completed_steps = sum(1 for task in job.tasks if task.status in {"success", "skipped"})
        if not job.tasks:
            job.progress_percent = 0
            return
        job.progress_percent = round(sum(task.progress_percent for task in job.tasks) / len(job.tasks))

    def _task_title(self, key: str, job: CollectionJob) -> str:
        for task in job.tasks:
            if task.key == key:
                return task.title
        return key

    def _format_abnormal_filter_summary(self, payload: dict[str, Any]) -> str:
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
            PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl",
            PROJECT_ROOT / "theme_data_complete" / "full_theme_list.sync.jsonl",
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
        tmp_dir = PROJECT_ROOT / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / f"collection_history_subject_keys_{trade_date.replace('-', '')}.txt"
        path.write_text("\n".join(subject_keys) + ("\n" if subject_keys else ""), encoding="utf-8")
        return path

    async def _run_command(
        self,
        job: CollectionJob,
        task: CollectionTaskState,
        cmd: list[str],
        env: Optional[dict[str, str]] = None,
        *,
        initial_percent: int = 5,
        success_percent: int = 100,
    ) -> None:
        task.status = "running"
        task.progress_percent = max(task.progress_percent, initial_percent)
        task.current_label = "启动中"
        job.current_step = task.key
        self._update_overall_progress(job)
        self._append_log(job, f"开始 {task.title}")
        self._append_log(job, f"[DEBUG] cmd={' '.join(cmd)}")
        if cmd:
            self._append_log(job, f"[DEBUG] executable_exists={Path(cmd[0]).exists()} executable={cmd[0]}")

        async def _consume_stream(
            stream: asyncio.StreamReader | None,
            *,
            is_stderr: bool = False,
        ) -> int:
            if stream is None:
                return 0
            consumed = 0
            while True:
                if job.cancel_requested and process.returncode is None:
                    process.terminate()
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore").rstrip()
                if not text:
                    continue
                consumed += 1
                rendered = f"[stderr] {text}" if is_stderr else text
                self._append_log(job, rendered)
                task.current_label = text[:120]
                parsed_progress = self._parse_progress_percent(task.key, cmd, text)
                if parsed_progress is not None:
                    task.progress_percent = max(task.progress_percent, parsed_progress)
                else:
                    task.progress_percent = min(90, max(task.progress_percent, 10 + consumed * 3))
                self._update_overall_progress(job)
            return consumed

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(PROJECT_ROOT),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        job.active_process = process
        await asyncio.gather(
            _consume_stream(process.stdout, is_stderr=False),
            _consume_stream(process.stderr, is_stderr=True),
        )

        return_code = await process.wait()
        job.active_process = None
        if job.cancel_requested:
            task.status = "cancelled"
            task.current_label = "已取消"
            task.progress_percent = 0
            self._update_overall_progress(job)
            raise asyncio.CancelledError()
        if return_code != 0:
            raise RuntimeError(f"{task.title} 执行失败，退出码 {return_code}")

        task.status = "success"
        task.current_label = "完成"
        task.progress_percent = success_percent
        self._update_overall_progress(job)
        self._append_log(job, f"{task.title} 完成")

    def _collection_env(self, payload: dict[str, Any]) -> dict[str, str]:
        env = os.environ.copy()
        env_file_values = self._load_env_file_values()
        tushare_token = str(
            payload.get("tushare_token")
            or os.getenv("TUSHARE_TOKEN", "")
            or env_file_values.get("TUSHARE_TOKEN", "")
        ).strip()
        jyhf_token = str(
            payload.get("jyhf_token")
            or os.getenv("JYHF_AUTH_TOKEN", "")
            or env_file_values.get("JYHF_AUTH_TOKEN", "")
            or _read_cdp_token_file()
        ).strip()
        deepseek_api_key = str(
            payload.get("deepseek_api_key")
            or os.getenv("DEEPSEEK_API_KEY", "")
            or env_file_values.get("DEEPSEEK_API_KEY", "")
        ).strip()
        deepseek_model = str(
            payload.get("deepseek_model")
            or os.getenv("DEEPSEEK_MODEL", "")
            or env_file_values.get("DEEPSEEK_MODEL", "")
        ).strip()
        if tushare_token:
            env["TUSHARE_TOKEN"] = tushare_token
        if jyhf_token:
            env["JYHF_AUTH_TOKEN"] = jyhf_token
        if deepseek_api_key:
            env["DEEPSEEK_API_KEY"] = deepseek_api_key
        if deepseek_model:
            env["DEEPSEEK_MODEL"] = deepseek_model
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _parse_progress_percent(self, task_key: str, cmd: list[str], text: str) -> int | None:
        if task_key == "jyhf":
            if "sync_jyhf_to_local.py" in " ".join(cmd) and ("stock_details" in cmd or "details" in cmd):
                match = re.search(r"\[(\d+)/(\d+)\]\s+collecting subject=", text)
                if match:
                    current = int(match.group(1))
                    total = max(int(match.group(2)), 1)
                    return min(95, 15 + round(current / total * 80))
                match = re.search(r"\[OK\]\s+subject_count=(\d+)", text)
                if match:
                    return 95
            if "sync_jyhf_to_local.py" in " ".join(cmd) and "lists" in cmd and text.startswith("[OK]"):
                return 15

        if task_key == "jyhf_history":
            if "sync_jyhf_to_local.py" in " ".join(cmd):
                match = re.search(r"\[(\d+)/(\d+)\]\s+collecting subject=", text)
                if match:
                    current = int(match.group(1))
                    total = max(int(match.group(2)), 1)
                    return min(90, 15 + round(current / total * 75))
                if text.startswith("[history_global]"):
                    return 12
                if re.search(r"history_mode=backfill", text):
                    return 20
                if re.search(r"\[OK\]\s+subject_count=(\d+)", text):
                    return 55
            if "import_jyhf_history_incremental.py" in " ".join(cmd):
                if text.startswith("[OK]"):
                    return 95

        if task_key == "tushare_kline":
            match = re.search(r"\[SYNC\]\s+attempted=(\d+)/(\d+)\s+stock_id=", text)
            if match:
                current = int(match.group(1))
                total = max(int(match.group(2)), 1)
                return min(95, 10 + round(current / total * 85))
            match = re.search(r"\[SKIP\]\s+attempted=(\d+)/(\d+)\s+stock_id=.*reason=(resume_completed|existing_file)", text)
            if match:
                current = int(match.group(1))
                total = max(int(match.group(2)), 1)
                return min(95, 10 + round(current / total * 85))
            match = re.search(r"\[OK\]\s+processed=(\d+)", text)
            if match:
                return 95

        return None

    async def _run_job(self, job: CollectionJob, start_index: int = 0) -> None:
        payload = job.payload
        env = self._collection_env(payload)
        options = payload.get("options") or {}
        abnormal_filters = payload.get("abnormal_filters") or {}
        trade_date = job.trade_date
        tushare_pause = str(payload.get("tushare_pause_seconds", 0.1))
        min_turnover = str(payload.get("min_turnover_rate", 3.0))
        min_score = str(payload.get("min_composite_score", 40.0))

        try:
            for index in range(start_index, len(job.tasks)):
                task = job.tasks[index]
                job.next_step_index = index
                if task.key == "jyhf":
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
                        "--types",
                        "lists",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=5, success_percent=15)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "load_subject_node_staging.py"),
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=15, success_percent=25)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
                        "--use-latest-list-subjects",
                        "--types",
                        "details",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=25, success_percent=45)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
                        "--use-latest-list-subjects",
                        "--types",
                        "stock_details",
                        "--trade-date",
                        trade_date,
                        "--resume",
                        "--skip-existing",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=45, success_percent=85)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "import_jyhf_stock_daily_incremental.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=85, success_percent=100)
                elif task.key == "jyhf_history":
                    subject_keys = self._latest_jyhf_subject_keys()
                    if not subject_keys:
                        raise RuntimeError("缺少最新题材列表：请先执行股票快照日采集，或确认 theme_data_complete/lists/full_theme_list.sync.jsonl 已生成。")
                    subjects_file = self._write_subject_keys_file(trade_date, subject_keys)
                    batch_id = f"collection_jyhf_history_{trade_date.replace('-', '')}"
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
                        "--use-latest-list-subjects",
                        "--types",
                        "history",
                        "--history-mode",
                        "incremental",
                        "--history-backfill-date",
                        trade_date,
                        "--batch-id",
                        batch_id,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=10, success_percent=55)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "import_jyhf_history_incremental.py"),
                        "--subjects-file",
                        str(subjects_file),
                        "--batch-id",
                        batch_id,
                        "--mode",
                        "append",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=55, success_percent=100)
                elif task.key == "tushare_kline":
                    tushare_token = env.get("TUSHARE_TOKEN", "").strip()
                    if not tushare_token:
                        raise RuntimeError("缺少 Tushare token：请设置环境变量 TUSHARE_TOKEN，或在项目 .env/.env.local 中配置。")
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "scripts" / "sync_tushare_kline_local.py"),
                        "--from-jyhf-universe",
                        "--end-date",
                        trade_date,
                        "--months",
                        "6",
                        "--pause-seconds",
                        tushare_pause,
                        "--resume",
                        "--skip-existing",
                    ]
                    cmd.extend(["--token", tushare_token])
                    await self._run_command(job, task, cmd, env=env, initial_percent=5, success_percent=55)

                    # 将本地 daily_bar 导入数据库 stock_daily_snapshot，保证策略侧直接可用。
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "scripts" / "import_tushare_daily_bar_to_db.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=55, success_percent=65)

                    # 将盘前竞价链路并入 tushare_kline 任务：观察池 -> 竞价快照 -> 竞价信号
                    source_trade_date = (datetime.fromisoformat(trade_date).date() - timedelta(days=1)).isoformat()
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_auction_watch_universe.py"),
                        "--trade-date",
                        trade_date,
                        "--source-trade-date",
                        source_trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=65, success_percent=75)

                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_pre_market_auction_snapshot.py"),
                        "--trade-date",
                        trade_date,
                        "--token",
                        tushare_token,
                        "--force-refresh",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=75, success_percent=87)

                    # 弱转强候选池专用竞价快照：用于两阶段策略盘前确认
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_pre_market_auction_snapshot.py"),
                        "--trade-date",
                        trade_date,
                        "--universe-source",
                        "weak_to_strong_candidates",
                        "--max-stocks",
                        "120",
                        "--token",
                        tushare_token,
                        "--force-refresh",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=87, success_percent=94)

                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_pre_market_auction_signal.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=94, success_percent=100)
                elif task.key == "dragon_tiger":
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_dragon_tiger_object.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    if env.get("TUSHARE_TOKEN"):
                        cmd.extend(["--token", env["TUSHARE_TOKEN"]])
                    await self._run_command(job, task, cmd, env=env)
                elif task.key == "abnormal_signal":
                    self._append_log(job, self._format_abnormal_filter_summary(payload))
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_stock_abnormal_signal.py"),
                        "--trade-date",
                        trade_date,
                        "--min-turnover-rate",
                        min_turnover,
                        "--min-composite-score",
                        min_score,
                    ]
                    if abnormal_filters.get("turnover_rate"):
                        cmd.append("--require-turnover")
                    if abnormal_filters.get("main_net_inflow"):
                        cmd.append("--require-main-net-inflow")
                    if abnormal_filters.get("hot_money_buy"):
                        cmd.append("--require-hot-money-buy")
                    if abnormal_filters.get("institution_buy"):
                        cmd.append("--require-institution-buy")
                    if abnormal_filters.get("tail_rush"):
                        cmd.append("--require-tail-rush")
                    if env.get("TUSHARE_TOKEN"):
                        cmd.extend(["--token", env["TUSHARE_TOKEN"]])
                    await self._run_command(job, task, cmd, env=env)
                elif task.key == "strong_stock_watch":
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "stock_service" / "scripts" / "build_strong_stock_watch_pool.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env)
                elif task.key == "leader_llm":
                    deepseek_api_key = env.get("DEEPSEEK_API_KEY", "").strip()
                    leader_llm_max_themes = str(payload.get("leader_llm_max_themes", 5))
                    if not deepseek_api_key:
                        task.status = "skipped"
                        task.current_label = "未配置 DEEPSEEK_API_KEY，已跳过"
                        task.progress_percent = 100
                        self._update_overall_progress(job)
                        self._append_log(job, "未配置 DEEPSEEK_API_KEY，跳过龙头候选 LLM 裁决")
                        continue
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_theme_leader_llm_queue.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=10, success_percent=30)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "build_theme_leader_llm_judgement.py"),
                        "--trade-date",
                        trade_date,
                        "--only-queued",
                        "--limit-themes",
                        leader_llm_max_themes,
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=30, success_percent=55)
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "database_service" / "scripts" / "call_theme_leader_llm.py"),
                        "--trade-date",
                        trade_date,
                        "--limit",
                        leader_llm_max_themes,
                        "--limit-themes",
                        leader_llm_max_themes,
                        "--only-queued",
                        "--only-pending",
                    ]
                    await self._run_command(job, task, cmd, env=env, initial_percent=55, success_percent=100)
                elif task.key == "recap_snapshot":
                    cmd = [
                        PYTHON_BIN,
                        str(PROJECT_ROOT / "scripts" / "build_post_market_recap.py"),
                        "--trade-date",
                        trade_date,
                    ]
                    if not options.get("auto_build_v2_if_missing", True):
                        cmd.append("--disable-auto-build-v2-if-missing")
                    if not options.get("dragon_tiger", True):
                        cmd.append("--skip-dragon-tiger")
                    if not options.get("abnormal_signal", True):
                        cmd.append("--skip-abnormal-signal")
                    if env.get("TUSHARE_TOKEN"):
                        cmd.extend(["--token", env["TUSHARE_TOKEN"]])
                    await self._run_command(job, task, cmd, env=env)
                job.next_step_index = index + 1

            job.status = "success"
            job.can_cancel = False
            job.can_continue = False
            job.current_step = ""
            self._update_overall_progress(job)
            self._append_log(job, "全部采集与盘后复盘步骤完成")
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.can_cancel = False
            job.can_continue = False
            job.current_step = ""
            self._append_log(job, "任务已取消")
        except Exception as exc:
            current_title = self._task_title(job.current_step, job)
            for task in job.tasks:
                if task.key == job.current_step:
                    task.status = "failed"
                    task.error_message = str(exc)
                    break
            job.status = "failed"
            job.can_cancel = False
            job.can_continue = True
            job.last_error = {
                "step": current_title,
                "message": str(exc),
                "detail": "你可以选择取消任务，或点击继续从当前失败步骤重新执行。",
            }
            self._update_overall_progress(job)
            self._append_log(job, f"{current_title} 失败：{exc}")
