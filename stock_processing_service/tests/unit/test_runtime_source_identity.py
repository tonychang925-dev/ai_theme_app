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
    assert payload["git_dirty"] is False
