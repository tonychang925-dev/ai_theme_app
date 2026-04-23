from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


class RunReconciliationJob:
    def execute(
        self,
        trade_date: date,
        old_records: list[dict[str, Any]],
        new_records: list[dict[str, Any]],
        output_dir: str = "tmp/reconciliation",
        sample_limit: int = 200,
    ) -> BuildResult:
        old_map = {self._pk(row): row for row in old_records}
        new_map = {self._pk(row): row for row in new_records}

        missing_in_new = sorted(set(old_map) - set(new_map))
        missing_in_old = sorted(set(new_map) - set(old_map))

        changed: list[dict[str, Any]] = []
        for pk in sorted(set(old_map) & set(new_map)):
            old_row = old_map[pk]
            new_row = new_map[pk]
            diff_fields = sorted(
                key for key in set(old_row) | set(new_row) if old_row.get(key) != new_row.get(key)
            )
            if diff_fields:
                changed.append(
                    {
                        "pk": pk,
                        "old_value": old_row,
                        "new_value": new_row,
                        "diff_fields": diff_fields,
                        "reason": "value_mismatch",
                    }
                )

        summary = {
            "trade_date": trade_date.isoformat(),
            "old_count": len(old_records),
            "new_count": len(new_records),
            "missing_in_new": len(missing_in_new),
            "missing_in_old": len(missing_in_old),
            "changed": len(changed),
            "matched": len(set(old_map) & set(new_map)) - len(changed),
            "gate_passed": len(missing_in_new) == 0 and len(missing_in_old) == 0 and len(changed) == 0,
        }

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        summary_path = out / "summary"
        diff_path = out / "diff_samples.jsonl"

        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        with diff_path.open("w", encoding="utf-8") as fh:
            for pk in missing_in_new[:sample_limit]:
                fh.write(
                    json.dumps(
                        {
                            "pk": pk,
                            "old_value": old_map[pk],
                            "new_value": None,
                            "diff_fields": ["__missing_in_new__"],
                            "reason": "missing_in_new",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            for pk in missing_in_old[:sample_limit]:
                fh.write(
                    json.dumps(
                        {
                            "pk": pk,
                            "old_value": None,
                            "new_value": new_map[pk],
                            "diff_fields": ["__missing_in_old__"],
                            "reason": "missing_in_old",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            for row in changed[:sample_limit]:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        return BuildResult(
            name="run_reconciliation",
            trade_date=trade_date.isoformat(),
            affected_rows=len(missing_in_new) + len(missing_in_old) + len(changed),
            status="ok",
        )

    def _pk(self, row: dict[str, Any]) -> str:
        if is_dataclass(row):
            row = asdict(row)
        if "stock_id" in row and "subject_key" in row and "trade_date" in row:
            return f"{row.get('trade_date')}|{row.get('subject_key')}|{row.get('stock_id')}"
        if "stock_id" in row and "trade_date" in row:
            return f"{row.get('trade_date')}|{row.get('stock_id')}"
        return json.dumps(row, sort_keys=True, ensure_ascii=False)
