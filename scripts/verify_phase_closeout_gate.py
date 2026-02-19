#!/usr/bin/env python3
"""Phase closeout hard gate.

Blocks entering STEP 5.2 if:
1) phase tasks are not all done;
2) report sync metadata is missing or invalid;
3) milestone fetched task set does not match expected phase task set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


VALID_REPORT_STATUS = {"Draft", "Submitted", "Reviewed", "Approved", "Rework"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def task_name(task: dict) -> str:
    return str(task.get("title") or task.get("name") or task.get("task_name") or "")


def task_status(task: dict) -> str:
    return str(task.get("status") or task.get("Status") or task.get("task_status") or "")


def extract_phase_task_id(name: str, phase_prefix: str) -> str:
    m = re.search(rf"({re.escape(phase_prefix)}-T\d+)", name)
    return m.group(1) if m else ""


def load_expected_task_ids(path: Path) -> set[str]:
    """Load expected task IDs from traceability json.

    Supported shapes:
    - {"traceability":[{"task_id":"P1.phase0-T01"}, ...]}
    - {"tasks":[{"id":"P1.phase0-T01"}, ...]}
    - {"task_ids":["P1.phase0-T01", ...]}
    """
    data = load_json(path)
    ids: set[str] = set()

    rows = data.get("traceability", [])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                task_id = row.get("task_id") or row.get("wbs_task_id")
                if task_id:
                    ids.add(str(task_id))

    tasks = data.get("tasks", [])
    if isinstance(tasks, list):
        for row in tasks:
            if isinstance(row, dict) and row.get("id"):
                ids.add(str(row["id"]))

    task_ids = data.get("task_ids", [])
    if isinstance(task_ids, list):
        for task_id in task_ids:
            if task_id:
                ids.add(str(task_id))

    return ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-prefix", required=True, help="e.g. P1.phase1")
    parser.add_argument("--tasks-json", required=True, help="milestone full fetch json path")
    parser.add_argument(
        "--expected-task-ids-json",
        required=True,
        help="phase expected task set json (traceability/wbs derived)",
    )
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--report-status", required=True, help="Draft|Submitted|Reviewed|Approved|Rework")
    args = parser.parse_args()

    errors: list[str] = []

    tasks_data = load_json(Path(args.tasks_json))
    tasks = tasks_data.get("tasks", [])
    phase_re = re.compile(rf"^{re.escape(args.phase_prefix)}-T\d+")
    phase_tasks = [t for t in tasks if extract_phase_task_id(task_name(t), args.phase_prefix)]
    fetched_task_ids = {
        extract_phase_task_id(task_name(t), args.phase_prefix) for t in phase_tasks
    }
    fetched_task_ids.discard("")
    expected_task_ids = load_expected_task_ids(Path(args.expected_task_ids_json))
    expected_phase_task_ids = {x for x in expected_task_ids if phase_re.search(x)}

    if not phase_tasks:
        errors.append(
            f"no phase tasks found for prefix '{args.phase_prefix}' in {args.tasks_json}; "
            "must use --milestone-id full fetch then local filter"
        )
    else:
        not_done = [task_name(t) for t in phase_tasks if task_status(t) != "done"]
        if not_done:
            errors.append(f"phase tasks not done: {', '.join(not_done)}")

    if not expected_phase_task_ids:
        errors.append(
            "expected phase task set is empty from --expected-task-ids-json; "
            "cannot verify closeout completeness"
        )
    else:
        missing_in_fetch = sorted(expected_phase_task_ids - fetched_task_ids)
        unexpected_in_fetch = sorted(fetched_task_ids - expected_phase_task_ids)
        if missing_in_fetch:
            errors.append(
                "milestone fetch missing expected phase tasks: "
                + ", ".join(missing_in_fetch)
            )
        if unexpected_in_fetch:
            errors.append(
                "milestone fetch contains unexpected phase tasks: "
                + ", ".join(unexpected_in_fetch)
            )

    if not args.report_id.strip():
        errors.append("report_id is empty")
    if args.report_status not in VALID_REPORT_STATUS:
        errors.append(
            f"invalid report_status '{args.report_status}', valid={sorted(VALID_REPORT_STATUS)}"
        )

    if errors:
        print("❌ phase closeout gate failed")
        for err in errors:
            print(f"- {err}")
        return 1

    print("✅ phase closeout gate passed")
    print(f"- phase_prefix: {args.phase_prefix}")
    print(f"- phase_task_count: {len(phase_tasks)}")
    print(f"- expected_phase_task_count: {len(expected_phase_task_ids)}")
    print(f"- report_id: {args.report_id}")
    print(f"- report_status: {args.report_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
