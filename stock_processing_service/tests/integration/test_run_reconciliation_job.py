from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stock_processing_service.application.jobs import RunReconciliationJob


def test_run_reconciliation_job_outputs(tmp_path: Path) -> None:
    job = RunReconciliationJob()

    old_records = [
        {"trade_date": "2026-04-23", "stock_id": "000001.SZ", "close_price": 10.1},
        {"trade_date": "2026-04-23", "stock_id": "000002.SZ", "close_price": 20.1},
    ]
    new_records = [
        {"trade_date": "2026-04-23", "stock_id": "000001.SZ", "close_price": 10.2},
        {"trade_date": "2026-04-23", "stock_id": "000003.SZ", "close_price": 30.1},
    ]

    result = job.execute(
        trade_date=date(2026, 4, 23),
        old_records=old_records,
        new_records=new_records,
        output_dir=str(tmp_path),
    )
    assert result.status == "ok"
    summary_path = tmp_path / "summary"
    diff_path = tmp_path / "diff_samples.jsonl"
    assert summary_path.exists()
    assert diff_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["missing_in_new"] == 1
    assert summary["missing_in_old"] == 1
    assert summary["changed"] == 1

    lines = [line for line in diff_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
