from __future__ import annotations

import json
import os

from stock_processing_service.application.services import realtime_stack_manager as mod


def test_realtime_stack_manager_root_points_to_repo_root():
    assert (mod.ROOT / "stock_processing_service").exists()
    assert (mod.ROOT / "evaluate_service").exists()


def test_realtime_stack_status_includes_source_and_rebuild_pids():
    manager = mod.RealtimeStackManager(python_cmd="python", redis_url="redis://127.0.0.1:6379/0")
    manager._state.akshare_pid = 11
    manager._state.raw_news_pid = 12
    manager._state.decision_pid = 13
    manager._state.rebuild_pid = 14

    status = manager.status_sync()

    assert status["akshare_pid"] == 11
    assert status["raw_news_pid"] == 12
    assert status["decision_pid"] == 13
    assert status["rebuild_pid"] == 14


def test_realtime_stack_restores_running_state_from_runtime_pidfiles(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    run_id = "realtime_20260529_123456"
    (runtime / "realtime_stack.json").write_text(json.dumps({
        "run_id": run_id,
        "manager_pid": 999,
        "parent_pid": 0,
        "watch_parent": False,
        "started_at": "2026-05-29T02:39:08+00:00",
        "db": "stock_data_test",
    }))
    (runtime / f"raw_news_{run_id}.pid").write_text(str(os.getpid()))
    (runtime / f"decision_{run_id}.pid").write_text(str(os.getpid()))
    (runtime / f"db_collector_{run_id}.pid").write_text(str(os.getpid()))

    manager = mod.RealtimeStackManager(
        python_cmd="python",
        redis_url="redis://127.0.0.1:6379/0",
        log_dir=str(tmp_path),
    )

    status = manager.status_sync()
    assert status["running"] is True
    assert status["run_id"] == run_id
    assert status["raw_news_pid"] == os.getpid()
    assert status["decision_pid"] == os.getpid()
    assert status["db_collector_pid"] == os.getpid()
    assert status["db_collector_enabled"] is True


def test_realtime_stack_children_are_started_detached_on_posix():
    kwargs = mod._detached_child_kwargs()
    if os.name == "posix":
        assert kwargs == {"start_new_session": True}
    else:
        assert kwargs == {}
