#!/usr/bin/env python3
"""Behavior-test quality gate for dev-orchestrator (TC-granularity hard gate)."""

from __future__ import annotations

import argparse
import ast
import glob
import json
import re
import sys
from pathlib import Path


BAD_CMD_TOKENS = ("rg ", "ripgrep", "grep ", "sed ", "awk ", "cat ")
MOCK_TOKENS = ("fakeredis", "asyncmock", "magicmock", "mocker.patch", "monkeypatch.setattr")
SCENARIO_SUCCESS_TOKENS = ("success", "ok", "pass", "works")
SCENARIO_FAILURE_TOKENS = ("fail", "error", "reject", "dead_letter", "deadletter", "invalid", "exception")
SCENARIO_EDGE_TOKENS = ("edge", "boundary", "empty", "none", "null", "max", "min", "limit", "overflow")
SEMANTIC_MAP = {
    "idempotency": ("idempot", "duplicate", "dedup", "skip"),
    "retry": ("retry", "requeue", "backoff"),
    "timeout": ("timeout", "deadline"),
    "concurrency": ("concurrent", "parallel", "race", "lock"),
}
CRITICAL_DEP_HINTS = ("redis", "postgres", "mysql", "database", "db", "sql", "llm", "openai", "api", "http")
STREAM_HINTS = ("stream", "themeprocessor", "decisionexecutor", "stream:events:")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_task_row(data: dict, task_id: str) -> dict:
    for row in data.get("traceability", []):
        if row.get("task_id") == task_id or row.get("wbs_task_id") == task_id:
            return row
    raise RuntimeError(f"task not found in traceability: {task_id}")


def _get_task_commands(row: dict) -> list[str]:
    cmds: list[str] = []
    if isinstance(row.get("test_commands"), list):
        cmds.extend(str(c) for c in row["test_commands"])
    for tc in row.get("test_cases", []):
        cmd = tc.get("command")
        if cmd:
            cmds.append(str(cmd))
    return cmds


def _get_task_tc_ids(row: dict) -> list[str]:
    ids: list[str] = []
    if isinstance(row.get("test_case_ids"), list):
        ids.extend(str(x) for x in row["test_case_ids"])
    for tc in row.get("test_cases", []):
        tc_id = tc.get("id")
        if tc_id:
            ids.append(str(tc_id))
    return sorted(set(ids))


def _find_pre_impl_log(task_id: str, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    candidates = sorted(glob.glob(f"tmp/runs/*/tests_pre_impl_{task_id}.log"))
    return Path(candidates[-1]) if candidates else None


def _check_commands(commands: list[str], test_files: list[str], errors: list[str]) -> None:
    if not commands:
        errors.append("mapped test commands are empty")
        return
    if not any("pytest" in c for c in commands):
        errors.append("mapped test commands do not include pytest")
    for c in commands:
        low = c.lower()
        if any(tok in low for tok in BAD_CMD_TOKENS) and "pytest" not in low:
            errors.append(f"non-runtime command is not allowed as primary evidence: {c}")
    for tf in test_files:
        if not any(("pytest" in c and tf in c) for c in commands):
            errors.append(f"pytest command does not cover test file: {tf}")


def _is_tc_comment(line: str) -> list[str]:
    # Strict TC-ID pattern to avoid matching random uppercase fragments.
    return [x.upper() for x in re.findall(r"\bTC-[A-Za-z0-9-]+\b", line)]


def _parse_tc_to_tests(text: str, file_path: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Map TC-ID to test function names and source snippets."""
    tc_map: dict[str, list[str]] = {}
    fn_source: dict[str, str] = {}
    lines = text.splitlines()
    pending_tcs: list[str] = []
    fn_pattern = re.compile(r"^\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(")

    for i, line in enumerate(lines):
        tc_hits = _is_tc_comment(line)
        if tc_hits:
            pending_tcs = [tc.upper() for tc in tc_hits]
            continue
        m = fn_pattern.match(line)
        if m:
            fn_name = m.group(1)
            snippet = "\n".join(lines[max(i - 4, 0): i + 60])
            fn_source[fn_name] = snippet
            if pending_tcs:
                for tc in pending_tcs:
                    tc_map.setdefault(tc, []).append(fn_name)
                pending_tcs = []

    if pending_tcs:
        # orphan tc comment without following test function
        for tc in pending_tcs:
            tc_map.setdefault(tc, [])

    if not tc_map and "TC-" in text.upper():
        raise RuntimeError(f"TC markers found but no matching test function in {file_path}")
    return tc_map, fn_source


def _check_pre_impl_evidence(pre_impl_log: Path | None, task_id: str, errors: list[str]) -> None:
    if pre_impl_log is None:
        errors.append(f"missing pre-implementation evidence log: tmp/runs/*/tests_pre_impl_{task_id}.log")
        return
    text = pre_impl_log.read_text(encoding="utf-8", errors="ignore").lower()
    if not any(k in text for k in ("failed", "xfail", "exit code: 1", "non-zero")):
        errors.append(f"pre-implementation evidence does not show failing-first signal: {pre_impl_log}")


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t in low for t in tokens)


def _check_tc_granularity(
    tc_ids: list[str],
    tc_to_tests: dict[str, list[str]],
    fn_source: dict[str, str],
    row: dict,
    commands: list[str],
    errors: list[str],
) -> None:
    if not tc_ids:
        errors.append("traceability missing test_case_ids for task")
        return

    found_sources: list[str] = []
    for tc in tc_ids:
        key = tc.upper()
        tests = tc_to_tests.get(key, [])
        if not tests:
            errors.append(f"TC granularity gate: no test function bound to {tc}")
            continue
        for fn in tests:
            src = fn_source.get(fn, "")
            found_sources.append(src)
            if "assert " not in src:
                errors.append(f"TC granularity gate: test has no assert -> {tc}:{fn}")
            if _contains_any(src, MOCK_TOKENS):
                errors.append(f"TC granularity gate: mock/fake pattern detected -> {tc}:{fn}")
            if _contains_any(src, ("read_text(", "open(", "Path(")) and not _contains_any(
                src, ("xadd(", "xack(", "xrange(", "fetch(", "execute(", "connect(", "ping(")
            ):
                errors.append(f"TC granularity gate: pseudo static assertion test -> {tc}:{fn}")

    merged = "\n".join(found_sources)
    if found_sources:
        # Avoid false negatives: at least one clear scenario signal is required.
        if not (
            _contains_any(merged, SCENARIO_SUCCESS_TOKENS)
            or _contains_any(merged, SCENARIO_FAILURE_TOKENS)
            or _contains_any(merged, SCENARIO_EDGE_TOKENS)
        ):
            errors.append("scenario coverage missing: no success/failure/edge signal found")

        # semantic assertions required by row/commands context
        ctx = (json.dumps(row, ensure_ascii=False) + "\n" + "\n".join(commands)).lower()
        for semantic, hints in SEMANTIC_MAP.items():
            if any(h in ctx for h in hints):
                if not any(h in merged.lower() for h in hints):
                    errors.append(f"semantic assertion missing for {semantic} (TC-granularity)")


def _check_real_dependency_constraints(row: dict, all_text: str, errors: list[str]) -> None:
    execution_mode = str(row.get("execution_mode", "")).strip().lower()
    allow_mock = row.get("allow_mock", None)
    critical_dependencies = row.get("critical_dependencies", [])
    if execution_mode != "real":
        errors.append("critical dependency gate: execution_mode must be 'real'")
    if allow_mock is not False:
        errors.append("critical dependency gate: allow_mock must be false")
    if not isinstance(critical_dependencies, list) or not critical_dependencies:
        errors.append("critical dependency gate: critical_dependencies must be non-empty list")

    low = all_text.lower()
    if any(tok in low for tok in MOCK_TOKENS):
        errors.append("critical dependency gate: mock/fake patterns detected in test sources")


def _check_real_stream_architecture(row: dict, all_text: str, errors: list[str]) -> None:
    low = all_text.lower()
    ctx = json.dumps(row, ensure_ascii=False).lower()
    is_stream_task = any(h in ctx for h in STREAM_HINTS) or "tests/streams/" in low
    if not is_stream_task:
        return

    # real pipeline components
    if "themeprocessor" not in low:
        errors.append("stream architecture gate: missing ThemeProcessor in behavior tests")
    if "decisionexecutor" not in low:
        errors.append("stream architecture gate: missing DecisionExecutor in behavior tests")

    # mandatory stream channels in assertions/workflow
    if "stream:events:normal" not in low:
        errors.append("stream architecture gate: missing stream:events:normal path")
    if "stream:events:decision" not in low:
        errors.append("stream architecture gate: missing stream:events:decision path")

    # must publish into stream and validate downstream stream results
    if "xadd(" not in low:
        errors.append("stream architecture gate: missing xadd publish action")
    if not any(k in low for k in ("xlen(", "xrange(", "xreadgroup(")):
        errors.append("stream architecture gate: missing downstream stream result assertion")

    # don't allow only direct-internal executor invocation as the primary path
    if "_process_decision(" in low and "xadd(" not in low:
        errors.append("stream architecture gate: direct _process_decision path without stream publish is not allowed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--traceability", required=True)
    ap.add_argument("--test-files", required=True, help="comma-separated relative paths")
    ap.add_argument("--pre-impl-log", default="", help="optional explicit pre-impl failing-test log path")
    args = ap.parse_args()

    test_files = [x.strip() for x in args.test_files.split(",") if x.strip()]
    if not test_files:
        print("❌ --test-files is empty")
        return 2

    data = _load_json(Path(args.traceability))
    row = _get_task_row(data, args.task_id)
    commands = _get_task_commands(row)
    tc_ids = _get_task_tc_ids(row)

    errors: list[str] = []
    _check_commands(commands, test_files, errors)
    pre_impl_log = _find_pre_impl_log(args.task_id, args.pre_impl_log or None)
    _check_pre_impl_evidence(pre_impl_log, args.task_id, errors)

    file_stats: list[str] = []
    all_text_parts: list[str] = []
    merged_tc_to_tests: dict[str, list[str]] = {}
    merged_fn_source: dict[str, str] = {}

    for rel in test_files:
        p = Path(rel)
        if not p.exists():
            errors.append(f"missing test file: {rel}")
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        all_text_parts.append(text)

        test_count = len(re.findall(r"^\s*(?:async\s+)?def\s+test_[A-Za-z0-9_]+\s*\(", text, flags=re.MULTILINE))
        file_stats.append(f"{rel}: tests={test_count}")
        if test_count == 0:
            errors.append(f"no pytest test function found: {rel}")

        tc_map, fn_source = _parse_tc_to_tests(text, rel)
        for k, v in tc_map.items():
            merged_tc_to_tests.setdefault(k, []).extend(v)
        merged_fn_source.update(fn_source)

    _check_tc_granularity(tc_ids, merged_tc_to_tests, merged_fn_source, row, commands, errors)

    full_text = "\n".join(all_text_parts)
    context_blob = (json.dumps(row, ensure_ascii=False) + "\n" + "\n".join(commands)).lower()
    if any(h in context_blob for h in CRITICAL_DEP_HINTS):
        _check_real_dependency_constraints(row, full_text, errors)
    _check_real_stream_architecture(row, full_text, errors)

    if errors:
        print("❌ behavior test quality gate failed")
        for e in errors:
            print(f"- {e}")
        if file_stats:
            print("- file stats:")
            for s in file_stats:
                print(f"  - {s}")
        if pre_impl_log:
            print(f"- pre-impl-log: {pre_impl_log}")
        return 1

    print("✅ behavior test quality gate passed")
    print(f"- task_id: {args.task_id}")
    for s in file_stats:
        print(f"- {s}")
    if pre_impl_log:
        print(f"- pre-impl-log: {pre_impl_log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
