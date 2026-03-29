#!/usr/bin/env python3
"""Phase-level test traceability gate.

Purpose:
- Prevent rg/grep-only pseudo validation from passing phase gates.
- Require runtime pytest evidence mapping for every phase task.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


NON_RUNTIME_TOKENS = ("rg ", "grep ", "sed ", "awk ", "cat ")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_task_rows(data: dict) -> list[dict]:
    rows = data.get("traceability", [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _commands_from_test_traceability(row: dict) -> list[str]:
    cmds: list[str] = []
    for tc in row.get("test_cases", []):
        if isinstance(tc, dict) and tc.get("command"):
            cmds.append(str(tc["command"]))
    return cmds


def _commands_from_feature_traceability(row: dict) -> list[str]:
    cmds = row.get("test_commands", [])
    if isinstance(cmds, list):
        return [str(c) for c in cmds]
    return []


def _task_id_from_row(row: dict) -> str:
    return str(row.get("task_id") or row.get("wbs_task_id") or "")


def _tc_ids_from_row(row: dict) -> list[str]:
    ids: list[str] = []
    if isinstance(row.get("test_case_ids"), list):
        ids.extend(str(x) for x in row["test_case_ids"])
    for tc in row.get("test_cases", []):
        if isinstance(tc, dict) and tc.get("id"):
            ids.append(str(tc["id"]))
    return sorted(set(ids))


def _has_pytest(cmds: list[str]) -> bool:
    return any("pytest" in c for c in cmds)


def _is_non_runtime_only(cmds: list[str]) -> bool:
    if not cmds:
        return True
    has_runtime = _has_pytest(cmds)
    has_non_runtime = any(any(tok in c.lower() for tok in NON_RUNTIME_TOKENS) for c in cmds)
    return has_non_runtime and not has_runtime


def _search_tc_markers(tc_ids: list[str], root: Path) -> dict[str, bool]:
    test_files = list(root.rglob("test_*.py"))
    content_cache: dict[Path, str] = {}
    found: dict[str, bool] = {}
    for tc in tc_ids:
        hit = False
        pattern = re.compile(re.escape(tc), re.IGNORECASE)
        for f in test_files:
            text = content_cache.get(f)
            if text is None:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
                content_cache[f] = text
            if pattern.search(text):
                hit = True
                break
        found[tc] = hit
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, help="e.g. P1.phase0")
    parser.add_argument("--test-traceability", required=True)
    parser.add_argument("--feature-traceability", required=True)
    parser.add_argument("--tests-root", default="database_service/tests")
    args = parser.parse_args()

    test_data = _load_json(Path(args.test_traceability))
    feat_data = _load_json(Path(args.feature_traceability))
    test_rows = _iter_task_rows(test_data)
    feat_rows = _iter_task_rows(feat_data)

    test_map = {_task_id_from_row(r): r for r in test_rows if _task_id_from_row(r)}
    feat_map = {_task_id_from_row(r): r for r in feat_rows if _task_id_from_row(r)}

    task_ids = sorted(set(test_map.keys()) | set(feat_map.keys()))
    errors: list[str] = []
    all_tc_ids: list[str] = []

    if not task_ids:
        errors.append("no task mappings found in traceability files")

    for task_id in task_ids:
        if task_id not in test_map:
            errors.append(f"missing in test_traceability: {task_id}")
            continue
        if task_id not in feat_map:
            errors.append(f"missing in feature_traceability: {task_id}")
            continue

        t_cmds = _commands_from_test_traceability(test_map[task_id])
        f_cmds = _commands_from_feature_traceability(feat_map[task_id])
        all_tc_ids.extend(_tc_ids_from_row(test_map[task_id]))

        if not t_cmds:
            errors.append(f"{task_id}: test_traceability has no test command")
        if not f_cmds:
            errors.append(f"{task_id}: feature_traceability has no test_commands")
        if _is_non_runtime_only(t_cmds):
            errors.append(f"{task_id}: test_traceability is non-runtime only (rg/grep/etc without pytest)")
        if _is_non_runtime_only(f_cmds):
            errors.append(f"{task_id}: feature_traceability is non-runtime only (rg/grep/etc without pytest)")
        if not _has_pytest(t_cmds):
            errors.append(f"{task_id}: test_traceability missing pytest command")
        if not _has_pytest(f_cmds):
            errors.append(f"{task_id}: feature_traceability missing pytest command")

    tc_ids = sorted(set(all_tc_ids))
    if not tc_ids:
        errors.append("no TC-ID found in traceability")
    else:
        hit_map = _search_tc_markers(tc_ids, Path(args.tests_root))
        missing = [tc for tc, ok in hit_map.items() if not ok]
        if missing:
            errors.append(f"TC-ID not found in test files: {', '.join(missing)}")

    if errors:
        print("❌ phase traceability gate failed")
        for err in errors:
            print(f"- {err}")
        return 1

    print("✅ phase traceability gate passed")
    print(f"- phase: {args.phase}")
    print(f"- mapped_tasks: {len(task_ids)}")
    print(f"- tc_ids: {len(tc_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
