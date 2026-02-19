#!/usr/bin/env python3
"""Validate feature artifacts without external dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


RISK_LEVELS = {"P0", "P1", "P2"}
SEVERITIES = {"info", "warn", "error"}
CHECK_NAMES = {
    "id_uniqueness",
    "traceability_complete",
    "test_command_ready",
    "rollback_defined",
    "schema_valid",
}
REQ_RE = re.compile(r"^PRD-REQ-[A-Za-z0-9.-]+-\d{3}$")
ACCEPTANCE_RE = re.compile(r"^(ACPT-[A-Za-z0-9.-]+-\d{3}|ACC-[A-Za-z0-9.-]+-\d{2,3})$")


def _load(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json in {path}: {exc}") from None


def _need_keys(obj: dict[str, Any], keys: set[str], label: str, errors: list[str]) -> None:
    missing = sorted(keys - set(obj.keys()))
    if missing:
        errors.append(f"{label}: missing keys {missing}")


def _validate_traceability(data: dict[str, Any], phase: str | None, errors: list[str]) -> None:
    required = {
        "schema_version",
        "phase",
        "generated_at",
        "source_files",
        "summary",
        "traceability",
        "gaps",
        "gate_ready",
    }
    _need_keys(data, required, "feature_traceability", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("feature_traceability: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"feature_traceability: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["source_files"], list) or not data["source_files"]:
        errors.append("feature_traceability: source_files must be non-empty array")
    if not isinstance(data["gaps"], list):
        errors.append("feature_traceability: gaps must be array")
    if not isinstance(data["gate_ready"], bool):
        errors.append("feature_traceability: gate_ready must be boolean")

    summary = data["summary"]
    if not isinstance(summary, dict):
        errors.append("feature_traceability.summary must be object")
    else:
        _need_keys(summary, {"total_tasks", "mapped_tasks", "unmapped_tasks", "risk_level"}, "feature_traceability.summary", errors)
        if "risk_level" in summary and summary["risk_level"] not in RISK_LEVELS:
            errors.append("feature_traceability.summary.risk_level must be one of P0/P1/P2")

    trace = data["traceability"]
    if not isinstance(trace, list):
        errors.append("feature_traceability: traceability must be array")
        return

    seen_tasks: set[str] = set()
    for i, item in enumerate(trace):
        label = f"feature_traceability.traceability[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be object")
            continue
        _need_keys(item, {"task_id", "requirement_ids", "acceptance_ids", "test_case_ids", "test_commands"}, label, errors)

        task_id = item.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            errors.append(f"{label}.task_id invalid: {task_id}")
        elif task_id in seen_tasks:
            errors.append(f"{label}.task_id duplicate: {task_id}")
        else:
            seen_tasks.add(task_id)

        reqs = item.get("requirement_ids")
        if not isinstance(reqs, list) or not reqs:
            errors.append(f"{label}.requirement_ids must be non-empty array")
        else:
            for rid in reqs:
                if not isinstance(rid, str) or not REQ_RE.match(rid):
                    errors.append(f"{label}.requirement_ids invalid id: {rid}")

        acpts = item.get("acceptance_ids")
        if not isinstance(acpts, list) or not acpts:
            errors.append(f"{label}.acceptance_ids must be non-empty array")
        else:
            for aid in acpts:
                if not isinstance(aid, str) or not ACCEPTANCE_RE.match(aid):
                    errors.append(f"{label}.acceptance_ids invalid id: {aid}")

        for k in ("test_case_ids", "test_commands"):
            arr = item.get(k)
            if not isinstance(arr, list) or not arr:
                errors.append(f"{label}.{k} must be non-empty array")


def _validate_report(data: dict[str, Any], phase: str | None, errors: list[str]) -> None:
    required = {"schema_version", "phase", "checked_at", "checks", "gate_ready"}
    _need_keys(data, required, "feature_validation_report", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("feature_validation_report: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"feature_validation_report: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["gate_ready"], bool):
        errors.append("feature_validation_report: gate_ready must be boolean")

    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        errors.append("feature_validation_report: checks must be non-empty array")
        return

    for i, item in enumerate(checks):
        label = f"feature_validation_report.checks[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be object")
            continue
        _need_keys(item, {"name", "passed", "severity"}, label, errors)
        if item.get("name") not in CHECK_NAMES:
            errors.append(f"{label}.name invalid: {item.get('name')}")
        if not isinstance(item.get("passed"), bool):
            errors.append(f"{label}.passed must be boolean")
        if item.get("severity") not in SEVERITIES:
            errors.append(f"{label}.severity must be one of {sorted(SEVERITIES)}")


def _validate_feature_spec(path: Path, phase: str | None, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"feature_spec: file not found: {path}")
        return
    if not phase:
        return

    expected_name = f"FEATURE_SPEC_{phase}.md"
    if path.name != expected_name:
        errors.append(
            f"feature_spec: filename mismatch, expected '{expected_name}', got '{path.name}'"
        )

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"feature_spec: cannot read file {path}: {exc}")
        return

    title = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            title = line
            break

    if not title:
        errors.append("feature_spec: missing markdown title")
        return

    if phase not in title:
        errors.append(
            f"feature_spec: title phase mismatch, expected title containing '{phase}', got '{title}'"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate feature artifacts.")
    parser.add_argument("--traceability", required=True, help="Path to tmp/feature_traceability_<phase>.json")
    parser.add_argument("--report", required=True, help="Path to tmp/feature_validation_report_<phase>.json")
    parser.add_argument("--feature-spec", help="Path to docs/project_control/FEATURE_SPEC_<phase>.md")
    parser.add_argument("--phase", help="Expected phase id, e.g. P1.phase0")
    args = parser.parse_args()

    errors: list[str] = []
    try:
        traceability = _load(Path(args.traceability))
        report = _load(Path(args.report))
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2

    if not isinstance(traceability, dict):
        errors.append("feature_traceability root must be object")
    else:
        _validate_traceability(traceability, args.phase, errors)

    if not isinstance(report, dict):
        errors.append("feature_validation_report root must be object")
    else:
        _validate_report(report, args.phase, errors)

    if args.feature_spec:
        _validate_feature_spec(Path(args.feature_spec), args.phase, errors)

    if errors:
        for err in errors:
            print(f"[ERROR] {err}")
        return 1

    print("[OK] feature artifacts are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
