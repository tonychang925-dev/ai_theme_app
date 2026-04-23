from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from stock_processing_service.application.jobs import RunReconciliationJob


@dataclass(frozen=True)
class ReplayRunResult:
    summary: dict[str, Any]
    output_dir: Path


def run_real_replay(sample_id: str, trade_date: date) -> ReplayRunResult:
    sample_key = sample_id.upper()
    old_path = os.getenv(f"REPLAY_{sample_key}_OLD_JSON", "").strip()
    new_path = os.getenv(f"REPLAY_{sample_key}_NEW_JSON", "").strip()

    if not old_path or not new_path:
        raise RuntimeError(
            f"missing replay inputs for {sample_id}: set REPLAY_{sample_key}_OLD_JSON and REPLAY_{sample_key}_NEW_JSON"
        )

    old_records = json.loads(Path(old_path).read_text(encoding="utf-8"))
    new_records = json.loads(Path(new_path).read_text(encoding="utf-8"))
    if not isinstance(old_records, list) or not isinstance(new_records, list):
        raise RuntimeError("replay input json must be list[object]")
    if not old_records or not new_records:
        raise RuntimeError("replay input lists must be non-empty")

    output_dir = Path("tmp/replay") / sample_id
    output_dir.mkdir(parents=True, exist_ok=True)

    result = RunReconciliationJob().execute(
        trade_date=trade_date,
        old_records=old_records,
        new_records=new_records,
        output_dir=str(output_dir),
        sample_limit=200,
    )

    # BuildResult status for reconciliation is always ok; gate outcome is in summary.
    if result.status != "ok":
        raise RuntimeError(f"unexpected reconciliation status={result.status}")

    summary = json.loads((output_dir / "summary").read_text(encoding="utf-8"))
    return ReplayRunResult(summary=summary, output_dir=output_dir)
