#!/usr/bin/env python3
"""Enforce task-level test-first gate for P0/P1 tasks.

This script validates:
1) required test files are explicitly provided and exist;
2) test files are present in current git diff (added/modified/untracked);
3) test files contain TC-ID traceability marker;
4) task's test commands include pytest and reference provided test files.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to load json: {path}: {exc}") from exc


def _git_changed_paths() -> set[str]:
    cp = _run(["git", "status", "--porcelain"])
    if cp.returncode != 0:
        raise RuntimeError(f"git status failed: {cp.stderr.strip()}")
    changed: set[str] = set()
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        changed.add(path)
    return changed


def _validate_tc_marker(test_file: Path) -> bool:
    text = test_file.read_text(encoding="utf-8", errors="ignore")
    # Accept TC-P1P1-001 / TC_ID style / explicit marker comments.
    return bool(re.search(r"TC[-_A-Z0-9]{3,}", text, flags=re.IGNORECASE))


def _task_traceability(traceability_json: dict, task_id: str) -> dict:
    rows = traceability_json.get("traceability", [])
    for row in rows:
        if row.get("task_id") == task_id or row.get("wbs_task_id") == task_id:
            return row
    raise RuntimeError(f"task_id not found in traceability: {task_id}")


def _commands_from_row(row: dict) -> list[str]:
    if "test_commands" in row and isinstance(row["test_commands"], list):
        return [str(x) for x in row["test_commands"]]
    test_cases = row.get("test_cases", [])
    cmds: list[str] = []
    for tc in test_cases:
        cmd = tc.get("command")
        if cmd:
            cmds.append(str(cmd))
    return cmds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--traceability", required=True, help="feature/test traceability json")
    ap.add_argument("--test-files", required=True, help="comma separated test files")
    args = ap.parse_args()

    task_id = args.task_id.strip()
    traceability_path = Path(args.traceability)
    test_files = [Path(x.strip()) for x in args.test_files.split(",") if x.strip()]
    if not test_files:
        print("❌ --test-files is empty")
        return 2

    data = _load_json(traceability_path)
    row = _task_traceability(data, task_id)
    test_cmds = _commands_from_row(row)
    if not test_cmds:
        print(f"❌ no test commands mapped for {task_id}")
        return 2

    changed = _git_changed_paths()
    errors: list[str] = []

    for tf in test_files:
        if not tf.exists():
            errors.append(f"missing file: {tf}")
            continue
        rel = str(tf)
        if rel.startswith("./"):
            rel = rel[2:]
        if rel not in changed:
            errors.append(f"file not in git diff: {rel}")
        if not _validate_tc_marker(tf):
            errors.append(f"TC-ID marker missing in test file: {rel}")

    for tf in test_files:
        rel = str(tf).lstrip("./")
        matched = [c for c in test_cmds if "pytest" in c and rel in c]
        if not matched:
            errors.append(f"traceability test_commands missing pytest for file: {rel}")

    if not any("pytest" in c for c in test_cmds):
        errors.append("no pytest command found in mapped test_commands")

    if errors:
        print("❌ task test gate failed")
        for err in errors:
            print(f"- {err}")
        return 1

    print("✅ task test gate passed")
    print(f"- task_id: {task_id}")
    print(f"- traceability: {traceability_path}")
    print(f"- test_files: {', '.join(str(x) for x in test_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
