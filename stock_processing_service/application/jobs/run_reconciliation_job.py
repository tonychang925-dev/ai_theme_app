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
                reason_category = self._classify_reason_category(diff_fields)
                changed.append(
                    {
                        "pk": pk,
                        "old_value": old_row,
                        "new_value": new_row,
                        "diff_fields": diff_fields,
                        "reason": "value_mismatch",
                        "reason_category": reason_category,
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
        explanation_path = out / "diff_explanation.md"

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
                            "reason_category": "input_missing",
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
                            "reason_category": "input_missing",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            for row in changed[:sample_limit]:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        explanation_path.write_text(
            self._build_diff_explanation_markdown(
                trade_date=trade_date,
                summary=summary,
                missing_in_new=missing_in_new,
                missing_in_old=missing_in_old,
                changed=changed,
                sample_limit=sample_limit,
            ),
            encoding="utf-8",
        )

        return BuildResult(
            name="run_reconciliation",
            trade_date=trade_date.isoformat(),
            affected_rows=len(missing_in_new) + len(missing_in_old) + len(changed),
            status="ok",
            warnings=[] if summary["gate_passed"] else ["reconciliation_diff_detected"],
            metrics={
                "old_count": summary["old_count"],
                "new_count": summary["new_count"],
                "missing_in_new": summary["missing_in_new"],
                "missing_in_old": summary["missing_in_old"],
                "changed": summary["changed"],
                "matched": summary["matched"],
                "gate_passed": summary["gate_passed"],
                "artifacts": {
                    "summary": str(summary_path),
                    "diff_samples": str(diff_path),
                    "diff_explanation": str(explanation_path),
                },
            },
        )

    def _pk(self, row: dict[str, Any]) -> str:
        if is_dataclass(row):
            row = asdict(row)
        if "stock_id" in row and "subject_key" in row and "trade_date" in row:
            return f"{row.get('trade_date')}|{row.get('subject_key')}|{row.get('stock_id')}"
        if "stock_id" in row and "trade_date" in row:
            return f"{row.get('trade_date')}|{row.get('stock_id')}"
        return json.dumps(row, sort_keys=True, ensure_ascii=False)

    def _build_diff_explanation_markdown(
        self,
        *,
        trade_date: date,
        summary: dict[str, Any],
        missing_in_new: list[str],
        missing_in_old: list[str],
        changed: list[dict[str, Any]],
        sample_limit: int,
    ) -> str:
        lines: list[str] = []
        lines.append("# Reconciliation Diff Explanation")
        lines.append("")
        lines.append(f"- trade_date: {trade_date.isoformat()}")
        lines.append(f"- gate_passed: {summary.get('gate_passed')}")
        lines.append(f"- old_count: {summary.get('old_count')}")
        lines.append(f"- new_count: {summary.get('new_count')}")
        lines.append(f"- missing_in_new: {summary.get('missing_in_new')}")
        lines.append(f"- missing_in_old: {summary.get('missing_in_old')}")
        lines.append(f"- changed: {summary.get('changed')}")
        lines.append("")
        category_counts = self._collect_category_counts(missing_in_new, missing_in_old, changed)
        lines.append("## Category Counts")
        lines.append("")
        for category, cnt in sorted(category_counts.items()):
            lines.append(f"- {category}: {cnt}")
        lines.append("")
        lines.append("## Top Diffs")
        lines.append("")
        has_diff = False

        for pk in missing_in_new[:sample_limit]:
            lines.append(f"- pk={pk} | reason=missing_in_new | reason_category=input_missing")
            has_diff = True
        for pk in missing_in_old[:sample_limit]:
            lines.append(f"- pk={pk} | reason=missing_in_old | reason_category=input_missing")
            has_diff = True
        for row in changed[:sample_limit]:
            lines.append(
                f"- pk={row.get('pk')} | reason=value_mismatch | reason_category={row.get('reason_category')} | diff_fields={','.join(row.get('diff_fields', []))}"
            )
            has_diff = True

        if not has_diff:
            lines.append("- no_diff")
        lines.append("")
        lines.append("## Action Suggestion")
        lines.append("")
        lines.append("- If gate_passed=false, classify each diff as input_missing/rule_diff/threshold_diff/order_diff/bug.")
        lines.append("- For bug or unintended rule_diff, fix new chain before enabling BFF rollout flag.")
        return "\n".join(lines) + "\n"

    def _classify_reason_category(self, diff_fields: list[str]) -> str:
        fields = {str(f).lower() for f in diff_fields}
        if any(f.startswith("evidence_") or "missing_flags" in f or "score_flags" in f for f in fields):
            return "input_missing"
        if any(
            ("threshold" in f)
            or ("score" in f)
            or ("price" in f)
            or ("pct" in f)
            or ("amount" in f)
            or ("volume" in f)
            for f in fields
        ):
            return "threshold_diff"
        if any("rank" in f or "order" in f for f in fields):
            return "order_diff"
        if any("state" in f or "decision" in f or "level" in f for f in fields):
            return "rule_diff"
        return "bug"

    def _collect_category_counts(
        self,
        missing_in_new: list[str],
        missing_in_old: list[str],
        changed: list[dict[str, Any]],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        if missing_in_new or missing_in_old:
            counts["input_missing"] = len(missing_in_new) + len(missing_in_old)
        for row in changed:
            category = str(row.get("reason_category") or "bug")
            counts[category] = counts.get(category, 0) + 1
        return counts
