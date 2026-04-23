from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stock_processing_service.application.jobs import RunQualityGateJob


def test_run_quality_gate_job(tmp_path: Path) -> None:
    job = RunQualityGateJob()
    result = job.execute(
        trade_date=date(2026, 4, 23),
        candidate_sources=["strong_watch_pool", "strong_watch_pool"],
        required_snapshot_fields=["stock_id", "snapshot_version"],
        snapshot_rows=[
            {"stock_id": "000001.SZ", "snapshot_version": "v1"},
            {"stock_id": "000002.SZ", "snapshot_version": "v1"},
        ],
        output_dir=str(tmp_path),
    )
    assert result.status == "ok"

    report = json.loads((tmp_path / "gate_report.json").read_text(encoding="utf-8"))
    assert report["gate_passed"] is True


def test_run_quality_gate_job_blocked(tmp_path: Path) -> None:
    job = RunQualityGateJob()
    result = job.execute(
        trade_date=date(2026, 4, 23),
        candidate_sources=["legacy_table"],
        required_snapshot_fields=["stock_id", "snapshot_version"],
        snapshot_rows=[{"stock_id": "000001.SZ", "snapshot_version": ""}],
        output_dir=str(tmp_path),
        max_missing_ratio=0.0,
    )
    assert result.status == "blocked"
