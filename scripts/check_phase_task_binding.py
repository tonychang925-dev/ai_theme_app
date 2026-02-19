#!/usr/bin/env python3
"""Check phase task binding completeness against milestone fetch results.

Usage:
  .venv/bin/python scripts/check_phase_task_binding.py \
    --phase-prefix P1.phase0 \
    --expected-task-ids-json tmp/feature_traceability_P1.phase0.json \
    --milestone-tasks-json tmp/runs/<run_id>/phase0_milestone_tasks.json \
    --all-tasks-json tmp/impl_run_phase0_tasks.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_phase_task_id(name: str, phase_prefix: str) -> str:
    m = re.search(rf"({re.escape(phase_prefix)}-T\d+)", name or "")
    return m.group(1) if m else ""


def task_name(task: dict[str, Any]) -> str:
    return str(task.get("name") or task.get("title") or task.get("task_name") or "")


def task_status(task: dict[str, Any]) -> str:
    return str(task.get("status") or task.get("Status") or task.get("task_status") or "")


def load_expected_ids(path: Path, phase_prefix: str) -> set[str]:
    data = load_json(path)
    ids: set[str] = set()
    rows = data.get("traceability", [])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                tid = row.get("task_id") or row.get("wbs_task_id")
                if isinstance(tid, str) and tid.startswith(f"{phase_prefix}-T"):
                    ids.add(tid)
    tasks = data.get("tasks", [])
    if isinstance(tasks, list):
        for row in tasks:
            if isinstance(row, dict):
                tid = row.get("id")
                if isinstance(tid, str) and tid.startswith(f"{phase_prefix}-T"):
                    ids.add(tid)
    task_ids = data.get("task_ids", [])
    if isinstance(task_ids, list):
        for tid in task_ids:
            if isinstance(tid, str) and tid.startswith(f"{phase_prefix}-T"):
                ids.add(tid)
    return ids


def map_tasks_by_id(tasks: list[dict[str, Any]], phase_prefix: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t in tasks:
        tid = extract_phase_task_id(task_name(t), phase_prefix)
        if tid:
            out[tid] = t
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-prefix", required=True)
    parser.add_argument("--expected-task-ids-json", required=True)
    parser.add_argument("--milestone-tasks-json", required=True)
    parser.add_argument("--all-tasks-json", help="Optional full task list for locating missing bindings")
    parser.add_argument("--output", help="Optional output json path")
    args = parser.parse_args()

    expected = load_expected_ids(Path(args.expected_task_ids_json), args.phase_prefix)
    milestone_tasks = load_json(Path(args.milestone_tasks_json)).get("tasks", [])
    if not isinstance(milestone_tasks, list):
        milestone_tasks = []
    milestone_map = map_tasks_by_id(milestone_tasks, args.phase_prefix)

    missing = sorted(expected - set(milestone_map.keys()))
    present = sorted(set(milestone_map.keys()) & expected)
    unexpected = sorted(set(milestone_map.keys()) - expected)

    missing_locations: list[dict[str, Any]] = []
    if args.all_tasks_json:
        all_tasks = load_json(Path(args.all_tasks_json)).get("tasks", [])
        if isinstance(all_tasks, list):
            all_map = map_tasks_by_id(all_tasks, args.phase_prefix)
            for tid in missing:
                t = all_map.get(tid)
                if t:
                    missing_locations.append(
                        {
                            "task_id": tid,
                            "status": task_status(t),
                            "milestone_id": t.get("milestone_id"),
                            "milestone_name": t.get("milestone_name"),
                        }
                    )
                else:
                    missing_locations.append(
                        {
                            "task_id": tid,
                            "status": None,
                            "milestone_id": None,
                            "milestone_name": None,
                        }
                    )

    report = {
        "phase_prefix": args.phase_prefix,
        "expected_count": len(expected),
        "milestone_phase_count": len(milestone_map),
        "present": present,
        "missing": missing,
        "unexpected": unexpected,
        "missing_locations": missing_locations,
        "ok": len(missing) == 0 and len(unexpected) == 0,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if report["ok"]:
        print("✅ phase task binding check passed")
    else:
        print("❌ phase task binding check failed")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
