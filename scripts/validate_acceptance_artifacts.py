#!/usr/bin/env python3
"""Lightweight validator for acceptance artifacts without external deps."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


RISK_LEVELS = {"P0", "P1", "P2"}
CHECK_SEVERITIES = {"info", "warn", "error"}
CHECK_NAMES = {
    "id_uniqueness",
    "traceability_complete",
    "fail_fast_defined",
    "command_assertion_ready",
    "schema_valid",
}
EXPECTED_VALUES = {"pass", "fail", "blocked"}
ACPT_RE = re.compile(r"^ACPT-[A-Za-z0-9.-]+-\d{3}$")
ACC_RE = re.compile(r"^ACC-[A-Za-z0-9.-]+-\d{2,3}$")


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json in {path}: {exc}") from None


def _require_keys(obj: dict[str, Any], required: set[str], label: str, errors: list[str]) -> None:
    missing = sorted(required - set(obj.keys()))
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
    _require_keys(data, required, "traceability", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("traceability: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"traceability: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["source_files"], list) or not data["source_files"]:
        errors.append("traceability: source_files must be a non-empty array")
    if not isinstance(data["gaps"], list):
        errors.append("traceability: gaps must be an array")
    if not isinstance(data["gate_ready"], bool):
        errors.append("traceability: gate_ready must be boolean")

    summary = data["summary"]
    if not isinstance(summary, dict):
        errors.append("traceability: summary must be object")
    else:
        _require_keys(
            summary,
            {"total_acceptance_targets", "mapped_acceptance_targets", "unmapped_acceptance_targets", "risk_level"},
            "traceability.summary",
            errors,
        )
        if "risk_level" in summary and summary["risk_level"] not in RISK_LEVELS:
            errors.append("traceability.summary.risk_level must be one of P0/P1/P2")

    trace = data["traceability"]
    if not isinstance(trace, list):
        errors.append("traceability: traceability must be array")
        return

    seen_acpt: set[str] = set()
    for i, item in enumerate(trace):
        label = f"traceability[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be object")
            continue
        _require_keys(item, {"acceptance_id", "case_ids", "commands", "expected"}, label, errors)
        acc_id = item.get("acceptance_id")
        if isinstance(acc_id, str):
            if not ACPT_RE.match(acc_id):
                errors.append(f"{label}.acceptance_id invalid format: {acc_id}")
            if acc_id in seen_acpt:
                errors.append(f"{label}.acceptance_id duplicate: {acc_id}")
            seen_acpt.add(acc_id)
        case_ids = item.get("case_ids")
        if not isinstance(case_ids, list) or not case_ids:
            errors.append(f"{label}.case_ids must be a non-empty array")
        else:
            for cid in case_ids:
                if not isinstance(cid, str) or not ACC_RE.match(cid):
                    errors.append(f"{label}.case_ids has invalid id: {cid}")
        commands = item.get("commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"{label}.commands must be a non-empty array")
        expected = item.get("expected")
        if expected not in EXPECTED_VALUES:
            errors.append(f"{label}.expected must be one of {sorted(EXPECTED_VALUES)}")


def _validate_report(data: dict[str, Any], phase: str | None, errors: list[str]) -> None:
    required = {"schema_version", "phase", "checked_at", "checks", "gate_ready"}
    _require_keys(data, required, "validation_report", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("validation_report: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"validation_report: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["gate_ready"], bool):
        errors.append("validation_report: gate_ready must be boolean")

    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        errors.append("validation_report: checks must be a non-empty array")
        return

    for i, chk in enumerate(checks):
        label = f"validation_report.checks[{i}]"
        if not isinstance(chk, dict):
            errors.append(f"{label}: must be object")
            continue
        _require_keys(chk, {"name", "passed", "severity"}, label, errors)
        name = chk.get("name")
        if name not in CHECK_NAMES:
            errors.append(f"{label}.name invalid: {name}")
        passed = chk.get("passed")
        if not isinstance(passed, bool):
            errors.append(f"{label}.passed must be boolean")
        sev = chk.get("severity")
        if sev not in CHECK_SEVERITIES:
            errors.append(f"{label}.severity must be one of {sorted(CHECK_SEVERITIES)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate acceptance artifacts.")
    parser.add_argument("--traceability", required=True, help="Path to acceptance_traceability.json")
    parser.add_argument("--report", required=True, help="Path to acceptance_validation_report.json")
    parser.add_argument("--phase", help="Expected phase id, e.g. P1.phase0")
    args = parser.parse_args()

    errors: list[str] = []
    try:
        traceability = _load_json(Path(args.traceability))
        report = _load_json(Path(args.report))
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2

    if not isinstance(traceability, dict):
        errors.append("traceability root must be object")
    else:
        _validate_traceability(traceability, args.phase, errors)
    if not isinstance(report, dict):
        errors.append("validation report root must be object")
    else:
        _validate_report(report, args.phase, errors)

    if errors:
        for err in errors:
            print(f"[ERROR] {err}")
        return 1

    print("[OK] acceptance artifacts are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
