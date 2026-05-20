from __future__ import annotations

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
