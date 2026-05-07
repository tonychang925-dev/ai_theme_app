from __future__ import annotations

from stock_processing_service.application.jobs.collection_job_manager import (
    CollectionJobManager,
    _redact_cmd,
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
