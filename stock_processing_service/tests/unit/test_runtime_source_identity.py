from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import stock_processing_service.api_app as api_app


def test_sps_healthz_reports_exact_runtime_source_identity():
    payload = asyncio.run(api_app.healthz())
    root = Path.cwd().resolve()
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()

    assert payload["cwd"] == str(root)
    assert payload["repo_root"] == str(root)
    assert payload["git_sha"] == sha
    assert payload["git_dirty"] == payload["process_start_identity"]["git_dirty"]
    assert payload["process_start_identity"]["git_sha"] == sha
    assert payload["source_drift"] is False


def test_sps_healthz_does_not_follow_checkout_drift(monkeypatch):
    import asyncio

    root = Path.cwd().resolve()
    monkeypatch.setattr(
        api_app.app.state,
        "runtime_identity",
        {"repo_root": str(root), "git_sha": "process-start-sha", "git_dirty": False},
        raising=False,
    )
    monkeypatch.setattr(api_app, "_runtime_git_sha", lambda _root: "current-worktree-sha")
    payload = asyncio.run(api_app.healthz())

    assert payload["git_sha"] == "process-start-sha"
    assert payload["current_worktree_identity"]["git_sha"] == "current-worktree-sha"
    assert payload["source_drift"] is True
