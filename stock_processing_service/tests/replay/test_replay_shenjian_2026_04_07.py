from __future__ import annotations

import os
from pathlib import Path
from datetime import date

import pytest

from stock_processing_service.tests.replay._replay_runner import run_real_replay


@pytest.mark.replay
def test_replay_shenjian_2026_04_07_diff_template_exists() -> None:
    """
    固化样本：神剑股份（2026-04-07）
    默认仅验证回放所需的差异说明模板存在；
    当 REPLAY_ENABLE_REAL=1 时，后续可在此接入真实新旧链路回放断言。
    """
    template = Path("tmp/replay/diff_explanation_template.md")
    assert template.exists(), "missing replay diff explanation template"

    if os.getenv("REPLAY_ENABLE_REAL", "0") != "1":
        pytest.skip("real replay disabled; set REPLAY_ENABLE_REAL=1 to enable full replay assertions")

    replay = run_real_replay("SHENJIAN", date(2026, 4, 7))
    summary = replay.summary
    assert summary["trade_date"] == "2026-04-07"
    assert int(summary["old_count"]) > 0
    assert int(summary["new_count"]) > 0
    assert (replay.output_dir / "diff_samples.jsonl").exists()
    assert (replay.output_dir / "diff_explanation.md").exists()
