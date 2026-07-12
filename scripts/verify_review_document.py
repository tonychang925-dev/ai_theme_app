#!/usr/bin/env python3
"""Verify a ReviewDocument against the Phase 4.5.7 golden UI baseline.

This script is intentionally read-only. It reports missing or mismatched
ReviewDocument fields and does not apply fallback, inference, or repairs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_DIR = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "tests"
    / "fixtures"
    / "review_document"
    / "golden"
)


@dataclass(frozen=True)
class CheckResult:
    group: str
    name: str
    status: str
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Trade date, e.g. 2026-07-09")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Golden UI baseline YAML. Defaults to tests/fixtures/review_document/golden/{date}_ui_baseline.yaml",
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=None,
        help="ReviewDocument JSON file. If omitted, tmp analyst workbench paths are probed.",
    )
    args = parser.parse_args()

    baseline_path = args.baseline or DEFAULT_BASELINE_DIR / f"{args.date}_ui_baseline.yaml"
    baseline = _load_yaml(baseline_path)
    document_path = args.document or _discover_document(args.date)

    if document_path is None:
        print(f"ReviewDocument not found for {args.date}")
        print("READY=False")
        return 2

    document = _load_json(document_path)
    results = verify(document, baseline)
    for line in _format_results(results):
        print(line)

    ready = all(item.status == "PASS" for item in results)
    print(f"READY={str(ready)}")
    return 0 if ready else 1


def verify(document: dict[str, Any], baseline: dict[str, Any]) -> list[CheckResult]:
    assertions = baseline.get("assertions")
    if not isinstance(assertions, dict):
        raise ValueError("baseline assertions must be a mapping")

    results: list[CheckResult] = []
    for group, group_spec in assertions.items():
        if not isinstance(group_spec, dict):
            continue
        for name, spec in group_spec.items():
            if not isinstance(spec, dict):
                continue
            results.append(_check_one(document, str(group), str(name), spec))
    return results


def _check_one(document: dict[str, Any], group: str, name: str, spec: dict[str, Any]) -> CheckResult:
    path = str(spec.get("path") or "")
    values = [_display_value(item) for item in _extract_path(document, path)]
    values = [item for item in values if item not in ("", None, [], {})]

    if spec.get("required") and not values:
        return CheckResult(group, name, "FAIL", f"{path} missing")

    if "equals" in spec:
        expected = spec["equals"]
        actual = values[0] if values else None
        if actual == expected:
            return CheckResult(group, name, "PASS", f"{path} == {expected!r}")
        return CheckResult(group, name, "FAIL", f"{path} expected {expected!r}, got {actual!r}")

    missing: list[str] = []
    for expected in spec.get("contains_all") or []:
        if expected not in values:
            missing.append(str(expected))

    forbidden_hits = [
        str(item)
        for item in spec.get("forbidden_values") or []
        if item in values
    ]

    if missing or forbidden_hits:
        parts: list[str] = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if forbidden_hits:
            parts.append("forbidden " + ", ".join(forbidden_hits))
        return CheckResult(group, name, "FAIL", f"{path}: {'; '.join(parts)}")

    if "contains_all" in spec or "forbidden_values" in spec:
        return CheckResult(group, name, "PASS", f"{path} values={values!r}")

    if values:
        return CheckResult(group, name, "PASS", f"{path} present")
    return CheckResult(group, name, "FAIL", f"{path} missing")


def _extract_path(payload: Any, path: str) -> list[Any]:
    if not path:
        return []
    current: list[Any] = [payload]
    for part in path.split("."):
        expand_list = part.endswith("[]")
        key = part[:-2] if expand_list else part
        next_items: list[Any] = []
        for item in current:
            value = item.get(key) if isinstance(item, dict) else None
            if expand_list:
                if isinstance(value, list):
                    next_items.extend(value)
            elif value is not None:
                next_items.append(value)
        current = next_items
    return current


def _display_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("final_value", "analyst_value", "ai_value", "name", "theme_name", "stock_name"):
            item = value.get(key)
            if item not in (None, "", [], {}):
                return _display_value(item)
        return ""
    return value


def _format_results(results: list[CheckResult]) -> list[str]:
    width = max((len(item.group) for item in results), default=6)
    return [
        f"{item.group.ljust(width)} {item.status} {item.name}: {item.message}"
        for item in results
    ]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "review_document" in data and isinstance(data["review_document"], dict):
        return data["review_document"]
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be a mapping: {path}")
    return data


def _discover_document(trade_date: str) -> Path | None:
    candidates = [
        PROJECT_ROOT / "tmp" / "analyst_workbench" / trade_date / "review_document.json",
        PROJECT_ROOT / "stock_processing_service" / "tmp" / "analyst_workbench" / trade_date / "review_document.json",
        PROJECT_ROOT / "tmp" / "analyst_workbench" / trade_date / "final_review_document.json",
        PROJECT_ROOT / "stock_processing_service" / "tmp" / "analyst_workbench" / trade_date / "final_review_document.json",
    ]
    return next((path for path in candidates if path.exists()), None)


if __name__ == "__main__":
    raise SystemExit(main())
