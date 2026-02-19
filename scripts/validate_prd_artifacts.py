#!/usr/bin/env python3
"""Validate PRD machine-readable artifacts without external dependencies."""

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
    "requirement_verifiable",
    "traceability_complete",
    "conflict_resolution_recorded",
    "schema_valid",
}
REQ_RE = re.compile(r"^PRD-REQ-[A-Za-z0-9.-]+-\d{3}$")
UC_RE = re.compile(r"^PRD-UC-[A-Za-z0-9.-]+-\d{2,3}$")
ACPT_RE = re.compile(r"^ACPT-[A-Za-z0-9.-]+-\d{3}$")


def _load(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json in {path}: {exc}") from None


def _must_have(obj: dict[str, Any], keys: set[str], label: str, errors: list[str]) -> None:
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
    _must_have(data, required, "prd_traceability", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("prd_traceability: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"prd_traceability: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["source_files"], list) or not data["source_files"]:
        errors.append("prd_traceability: source_files must be non-empty array")
    if not isinstance(data["gaps"], list):
        errors.append("prd_traceability: gaps must be array")
    if not isinstance(data["gate_ready"], bool):
        errors.append("prd_traceability: gate_ready must be boolean")

    summary = data["summary"]
    if not isinstance(summary, dict):
        errors.append("prd_traceability.summary must be object")
    else:
        _must_have(
            summary,
            {"total_requirements", "mapped_requirements", "unmapped_requirements", "risk_level"},
            "prd_traceability.summary",
            errors,
        )
        if "risk_level" in summary and summary["risk_level"] not in RISK_LEVELS:
            errors.append("prd_traceability.summary.risk_level must be one of P0/P1/P2")

    trace = data["traceability"]
    if not isinstance(trace, list):
        errors.append("prd_traceability: traceability must be array")
        return

    seen_req: set[str] = set()
    for i, item in enumerate(trace):
        label = f"prd_traceability.traceability[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be object")
            continue
        _must_have(item, {"requirement_id", "use_case_ids", "acceptance_ids", "test_case_ids", "wbs_task_ids"}, label, errors)

        req_id = item.get("requirement_id")
        if not isinstance(req_id, str) or not REQ_RE.match(req_id):
            errors.append(f"{label}.requirement_id invalid: {req_id}")
        elif req_id in seen_req:
            errors.append(f"{label}.requirement_id duplicate: {req_id}")
        else:
            seen_req.add(req_id)

        for k, regex in [("use_case_ids", UC_RE), ("acceptance_ids", ACPT_RE)]:
            arr = item.get(k)
            if not isinstance(arr, list) or not arr:
                errors.append(f"{label}.{k} must be non-empty array")
            else:
                for v in arr:
                    if not isinstance(v, str) or not regex.match(v):
                        errors.append(f"{label}.{k} invalid id: {v}")

        for k in ["test_case_ids", "wbs_task_ids"]:
            arr = item.get(k)
            if not isinstance(arr, list) or not arr:
                errors.append(f"{label}.{k} must be non-empty array")


def _validate_report(data: dict[str, Any], phase: str | None, errors: list[str]) -> None:
    required = {"schema_version", "phase", "checked_at", "checks", "gate_ready"}
    _must_have(data, required, "prd_validation_report", errors)
    if errors:
        return

    if data["schema_version"] != "1.0":
        errors.append("prd_validation_report: schema_version must be '1.0'")
    if phase and data["phase"] != phase:
        errors.append(f"prd_validation_report: phase mismatch, expected '{phase}', got '{data['phase']}'")
    if not isinstance(data["gate_ready"], bool):
        errors.append("prd_validation_report: gate_ready must be boolean")

    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        errors.append("prd_validation_report: checks must be non-empty array")
        return

    for i, item in enumerate(checks):
        label = f"prd_validation_report.checks[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be object")
            continue
        _must_have(item, {"name", "passed", "severity"}, label, errors)
        if item.get("name") not in CHECK_NAMES:
            errors.append(f"{label}.name invalid: {item.get('name')}")
        if not isinstance(item.get("passed"), bool):
            errors.append(f"{label}.passed must be boolean")
        if item.get("severity") not in SEVERITIES:
            errors.append(f"{label}.severity must be one of {sorted(SEVERITIES)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PRD artifacts.")
    parser.add_argument("--traceability", required=True, help="Path to tmp/prd_traceability.json")
    parser.add_argument("--report", required=True, help="Path to tmp/prd_validation_report.json")
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
        errors.append("prd_traceability root must be object")
    else:
        _validate_traceability(traceability, args.phase, errors)

    if not isinstance(report, dict):
        errors.append("prd_validation_report root must be object")
    else:
        _validate_report(report, args.phase, errors)

    if errors:
        for err in errors:
            print(f"[ERROR] {err}")
        return 1

    print("[OK] prd artifacts are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
