from __future__ import annotations

from stock_processing_service.application.jobs.collection_job_manager import (
    CollectionJobManager,
    _redact_cmd,
)
from stock_processing_service.application.services.collection_orchestrator import (
    CollectionCommandPlanner,
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

    first_cmd = plan.commands[0].cmd
    token_index = first_cmd.index("--token") + 1
    assert first_cmd[token_index] == "abc123"
    assert len(plan.commands) == 6


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

    cmd = plan.commands[0].cmd
    assert "--disable-auto-build-v2-if-missing" in cmd
    assert "--skip-dragon-tiger" in cmd
    assert "--skip-abnormal-signal" in cmd
    assert cmd[cmd.index("--token") + 1] == "abc123"


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

    assert "build_dragon_tiger_object.py" in dragon.commands[0].cmd[1]
    assert dragon.commands[0].cmd[-2:] == ["--token", "abc123"]
    abnormal_cmd = abnormal.commands[0].cmd
    assert "build_stock_abnormal_signal.py" in abnormal_cmd[1]
    assert "--require-turnover" in abnormal_cmd
    assert "--require-main-net-inflow" in abnormal_cmd
    assert "--require-hot-money-buy" in abnormal_cmd
    assert "--require-institution-buy" in abnormal_cmd
    assert "--require-tail-rush" in abnormal_cmd
    assert abnormal_cmd[-2:] == ["--token", "abc123"]


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
    assert len(planned.commands) == 3
    assert "build_theme_leader_llm_queue.py" in planned.commands[0].cmd[1]
    assert "build_theme_leader_llm_judgement.py" in planned.commands[1].cmd[1]
    assert "call_theme_leader_llm.py" in planned.commands[2].cmd[1]
    assert planned.commands[1].cmd[-1] == "7"
