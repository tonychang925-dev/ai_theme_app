from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


class RunQualityGateJob:
    def execute(
        self,
        trade_date: date,
        *,
        candidate_sources: list[str],
        required_snapshot_fields: list[str],
        snapshot_rows: list[dict[str, Any]],
        max_missing_ratio: float = 0.05,
        output_dir: str = "tmp/quality_gate",
    ) -> BuildResult:
        violations: list[str] = []

        if any(src != "strong_watch_pool" for src in candidate_sources):
            violations.append("candidate_source_not_from_strong_watch_pool")

        total_cells = max(1, len(snapshot_rows) * max(1, len(required_snapshot_fields)))
        missing_cells = 0
        for row in snapshot_rows:
            for field in required_snapshot_fields:
                if row.get(field) in (None, ""):
                    missing_cells += 1
        missing_ratio = missing_cells / total_cells
        if missing_ratio > max_missing_ratio:
            violations.append(f"missing_ratio_exceeded:{missing_ratio:.4f}")

        output = {
            "trade_date": trade_date.isoformat(),
            "gate_passed": len(violations) == 0,
            "violations": violations,
            "metrics": {
                "candidate_source_count": len(candidate_sources),
                "snapshot_row_count": len(snapshot_rows),
                "missing_ratio": missing_ratio,
                "max_missing_ratio": max_missing_ratio,
            },
        }

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "gate_report.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        return BuildResult(
            name="run_quality_gate",
            trade_date=trade_date.isoformat(),
            affected_rows=len(snapshot_rows),
            status="ok" if len(violations) == 0 else "blocked",
        )
