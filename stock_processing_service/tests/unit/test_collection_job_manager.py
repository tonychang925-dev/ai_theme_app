from __future__ import annotations

from stock_processing_service.application.jobs.collection_job_manager import (
    CollectionJob,
    CollectionJobManager,
    CollectionTaskState,
    _redact_cmd,
)
from stock_processing_service.application.services.collection_orchestrator import (
    CollectionCommand,
    CollectionCommandPlanner,
    CollectionTaskPlan,
)
from stock_processing_service.application.services.collection_task_registry import (
    CollectionTaskRegistry,
    _register_default_runners,
)


def test_collection_env_normalizes_tushare_token_from_env_file(monkeypatch):
    manager = CollectionJobManager()
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(
        manager,
        "_load_env_file_values",
        lambda: {"TUSHARE_TOKEN": "  'abc123'  "},
    )

    env = manager._collection_env({})

    assert env["TUSHARE_TOKEN"] == "abc123"


def test_collection_command_redacts_token_argument():
    rendered = _redact_cmd(["python", "script.py", "--token", "abc123", "--trade-date", "2026-05-06"])

    assert "abc123" not in rendered
    assert "--token <redacted>" in rendered


def test_collection_availability_allows_historical_trade_date():
    manager = CollectionJobManager()

    payload = manager.availability("2000-01-01")

    assert payload["allowed"] is True
    assert payload["message"] == "历史交易日可直接启动采集"


def test_collection_planner_builds_tushare_commands_without_shell_quotes():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="tushare_kline",
        trade_date="2026-05-06",
        payload={"tushare_pause_seconds": 0.1},
        env={"TUSHARE_TOKEN": "  'abc123'  "},
    )

    # tushare_kline 已拆分为独立任务，仅含 1 个 step（K线采集）
    assert len(plan.steps) == 1
    assert plan.steps[0].runner_key == "tushare.daily_bar"


def test_collection_planner_builds_auction_commands():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="auction",
        trade_date="2026-05-06",
        payload={},
        env={},
    )

    # auction 含 4 个 step：观察池 → 快照(全量) → 快照(w2s) → 信号
    assert len(plan.steps) == 4
    assert plan.steps[0].runner_key == "auction.watch_universe"
    assert plan.steps[1].runner_key == "auction.snapshot_all"
    assert plan.steps[2].runner_key == "auction.snapshot_w2s"
    assert plan.steps[3].runner_key == "auction.signal"


def test_collection_planner_builds_f10_capital_runner():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="f10_capital",
        trade_date="2026-05-06",
        payload={"options": {"stock_ids": ["000001", "600000"]}},
        env={"TDX_AGENT_HOST": "127.0.0.1", "TDX_AGENT_PORT": "8766"},
    )

    assert plan.runner_key == "f10.capital.collect"
    assert len(plan.steps) == 0
    assert any("资金动向快照采集" in msg for msg in plan.pre_logs)


def test_collection_planner_builds_hot_money_activity_runner():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="hot_money_activity",
        trade_date="2026-05-06",
        payload={},
        env={"TUSHARE_TOKEN": "abc123"},
    )

    assert plan.runner_key == "hot_money_activity.build"
    assert len(plan.steps) == 0
    assert any("游资席位活动表" in msg for msg in plan.pre_logs)


def test_collection_job_manager_includes_hot_money_activity_by_default():
    manager = CollectionJobManager()

    tasks = manager._build_tasks({"options": {}})
    task_keys = [task.key for task in tasks]

    assert "hot_money_activity" in task_keys
    assert task_keys.index("dragon_tiger") < task_keys.index("hot_money_activity")


def test_collection_planner_keeps_strong_watch_as_service_owned_step():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="strong_stock_watch",
        trade_date="2026-05-06",
        payload={},
        env={},
    )

    assert plan.commands == []
    assert plan.terminal_status == "success"
    assert plan.terminal_label == "由 recap_snapshot 新链任务统一生成"


def test_collection_planner_recap_command_preserves_skip_flags():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="recap_snapshot",
        trade_date="2026-05-06",
        payload={
            "options": {
                "auto_build_v2_if_missing": False,
                "dragon_tiger": False,
                "abnormal_signal": False,
            }
        },
        env={"TUSHARE_TOKEN": "abc123"},
    )

    # recap_snapshot owns report-source preparation and must not run recap.report.
    assert len(plan.commands) == 0
    assert plan.runner_key == ""
    assert [step.key for step in plan.steps] == [
        "stock_kline_judgements",
        "recap_prerequisites",
        "market_environment_daily",
        "theme_capital_flow_daily",
        "money_flow_enhanced",
        "abnormal_signal",
        "recap_data",
    ]
    assert "market_environment_judgement" not in [step.key for step in plan.steps]
    assert "theme_environment_judgement" not in [step.key for step in plan.steps]
    assert "theme_leader_candidate" not in [step.key for step in plan.steps]
    assert "recap.report" not in [step.runner_key for step in plan.steps]
    assert "stock.kline_judgements" in [step.runner_key for step in plan.steps]
    assert "recap.prerequisites" in [step.runner_key for step in plan.steps]
    assert "recap.market_environment_daily" in [step.runner_key for step in plan.steps]
    assert "recap.theme_capital_flow_daily" in [step.runner_key for step in plan.steps]
    assert plan.steps[-1].runner_key == "recap.snapshot"


def test_collection_registry_does_not_register_recap_report_overlay_runner():
    registry = CollectionTaskRegistry()

    _register_default_runners(registry)

    assert registry.get("recap.snapshot") is not None
    assert registry.get("recap.prerequisites") is not None
    assert registry.get("recap.market_environment_daily") is not None
    assert registry.get("recap.theme_capital_flow_daily") is not None
    assert registry.get("recap.report") is None
    assert registry.get("f10.capital.collect") is not None
    assert registry.get("hot_money_activity.build") is not None


def test_collection_planner_jyhf_commands_preserve_script_order():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="jyhf",
        trade_date="2026-05-06",
        payload={},
        env={},
    )

    scripts = [cmd.cmd[1] for cmd in plan.commands]
    assert scripts == [
        "/Users/admin/Desktop/ai_theme_app/sync_jyhf_to_local.py",
        "/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_node_staging.py",
        "/Users/admin/Desktop/ai_theme_app/sync_jyhf_to_local.py",
        "/Users/admin/Desktop/ai_theme_app/sync_jyhf_to_local.py",
        "/Users/admin/Desktop/ai_theme_app/database_service/scripts/import_jyhf_stock_daily_incremental.py",
    ]
    assert plan.commands[3].cmd[-3:] == ["2026-05-06", "--resume", "--skip-existing"]


def test_collection_planner_jyhf_history_requires_subject_list(tmp_path):
    planner = CollectionCommandPlanner(project_root=tmp_path, python_bin="python")

    try:
        planner.build_task_plan(
            task_key="jyhf_history",
            trade_date="2026-05-06",
            payload={},
            env={},
        )
    except RuntimeError as exc:
        assert "缺少最新题材列表" in str(exc)
    else:
        raise AssertionError("expected missing subject list to fail")


def test_collection_planner_jyhf_history_writes_subject_file(tmp_path):
    source_dir = tmp_path / "theme_data_complete" / "lists"
    source_dir.mkdir(parents=True)
    (source_dir / "full_theme_list.sync.jsonl").write_text(
        '{"subjectId":"1001"}\n{"id":"1002"}\n{"bizKey":"1001"}\n',
        encoding="utf-8",
    )
    planner = CollectionCommandPlanner(project_root=tmp_path, python_bin="python")

    plan = planner.build_task_plan(
        task_key="jyhf_history",
        trade_date="2026-05-06",
        payload={},
        env={},
    )

    assert len(plan.commands) == 2
    import_cmd = plan.commands[1].cmd
    subjects_file = import_cmd[import_cmd.index("--subjects-file") + 1]
    assert (tmp_path / "tmp" / "collection_history_subject_keys_20260506.txt").read_text(encoding="utf-8") == "1001\n1002\n"
    assert subjects_file.endswith("collection_history_subject_keys_20260506.txt")


def test_collection_planner_market_auxiliary_commands_preserve_tokens():
    planner = CollectionCommandPlanner()

    dragon = planner.build_task_plan(
        task_key="dragon_tiger",
        trade_date="2026-05-06",
        payload={},
        env={"TUSHARE_TOKEN": "abc123"},
    )
    abnormal = planner.build_task_plan(
        task_key="abnormal_signal",
        trade_date="2026-05-06",
        payload={
            "abnormal_filters": {
                "turnover_rate": True,
                "main_net_inflow": True,
                "hot_money_buy": True,
                "institution_buy": True,
                "tail_rush": True,
            },
            "min_turnover_rate": 4.5,
            "min_composite_score": 55,
        },
        env={"TUSHARE_TOKEN": "abc123"},
    )

    # dragon_tiger 已切换到服务化 Runner
    assert dragon.runner_key == "dragon_tiger.object"
    assert len(dragon.commands) == 0
    # abnormal_signal 已切换到服务化 Runner
    assert abnormal.runner_key == "abnormal.signal"
    assert len(abnormal.commands) == 0


def test_collection_planner_leader_llm_skip_and_commands():
    planner = CollectionCommandPlanner()

    skipped = planner.build_task_plan(
        task_key="leader_llm",
        trade_date="2026-05-06",
        payload={},
        env={},
    )
    planned = planner.build_task_plan(
        task_key="leader_llm",
        trade_date="2026-05-06",
        payload={"leader_llm_max_themes": 7},
        env={"DEEPSEEK_API_KEY": "key"},
    )

    assert skipped.terminal_status == "skipped"
    assert len(planned.commands) == 4
    assert "build_theme_leader_llm_queue.py" in planned.commands[0].cmd[1]
    assert "build_theme_leader_llm_judgement.py" in planned.commands[1].cmd[1]
    assert "call_theme_leader_llm.py" in planned.commands[2].cmd[1]
    assert "build_theme_leader_candidate.py" in planned.commands[3].cmd[1]
    assert planned.commands[1].cmd[-1] == "7"


def test_collection_planner_unknown_task_is_skipped():
    planner = CollectionCommandPlanner()

    plan = planner.build_task_plan(
        task_key="unknown_task",
        trade_date="2026-05-06",
        payload={},
        env={},
    )

    assert plan.commands == []
    assert plan.terminal_status == "skipped"
    assert plan.terminal_label == "未知任务，已跳过"


def test_collection_job_manager_executes_planned_commands_in_order():
    class FakePlanner:
        def build_task_plan(self, *, task_key, trade_date, payload, env):
            return CollectionTaskPlan(
                pre_logs=[f"prelog:{task_key}:{trade_date}"],
                commands=[
                    CollectionCommand(["python", f"{task_key}_1.py"], initial_percent=10, success_percent=50),
                    CollectionCommand(["python", f"{task_key}_2.py"], initial_percent=50, success_percent=100),
                ],
            )

    class RecordingManager(CollectionJobManager):
        def __init__(self):
            super().__init__(command_planner=FakePlanner())
            self.commands = []

        async def _run_command(self, job, task, cmd, env=None, *, initial_percent=5, success_percent=100):
            self.commands.append((task.key, cmd, initial_percent, success_percent))
            task.status = "success"
            task.progress_percent = success_percent
            self._update_overall_progress(job)

    manager = RecordingManager()
    job = CollectionJob(
        job_id="job1",
        trade_date="2026-05-06",
        payload={},
        status="running",
        total_steps=1,
        tasks=[CollectionTaskState(key="jyhf", title="股票快照日采集")],
    )

    import asyncio

    asyncio.run(manager._run_job(job))

    assert manager.commands == [
        ("jyhf", ["python", "jyhf_1.py"], 10, 50),
        ("jyhf", ["python", "jyhf_2.py"], 50, 100),
    ]
    assert any("prelog:jyhf:2026-05-06" in line for line in job.logs)
    assert job.status == "success"
    assert job.completed_steps == 1
    assert job.progress_percent == 100


def test_collection_job_manager_applies_terminal_plan_without_running_command():
    class FakePlanner:
        def build_task_plan(self, *, task_key, trade_date, payload, env):
            return CollectionTaskPlan(
                pre_logs=["terminal prelog"],
                terminal_status="skipped",
                terminal_label="terminal label",
            )

    class RecordingManager(CollectionJobManager):
        def __init__(self):
            super().__init__(command_planner=FakePlanner())
            self.commands = []

        async def _run_command(self, job, task, cmd, env=None, *, initial_percent=5, success_percent=100):
            self.commands.append(cmd)

    manager = RecordingManager()
    job = CollectionJob(
        job_id="job1",
        trade_date="2026-05-06",
        payload={},
        status="running",
        total_steps=1,
        tasks=[CollectionTaskState(key="leader_llm", title="龙头候选LLM裁决")],
    )

    import asyncio

    asyncio.run(manager._run_job(job))

    assert manager.commands == []
    assert job.tasks[0].status == "skipped"
    assert job.tasks[0].current_label == "terminal label"
    assert any("terminal prelog" in line for line in job.logs)
    assert job.status == "success"
