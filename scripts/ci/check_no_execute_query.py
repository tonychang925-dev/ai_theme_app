#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "tmp" / "p3_execute_query_gate_report.json"
PATTERN = re.compile(r"\bexecute_query\s*\(")

# P3.phase1-T07: infrastructure-only allowlist
ALLOWLIST = {
    "database_service/interface.py",
    "database_service/managers/postgres_manager.py",
}

ALLOW_PREFIXES = (
    "database_service/managers/",
    "database_service/interface.py",
)

SCAN_DIRS = [
    ROOT / "stock_processing_service",
    ROOT / "database_service",
]


def _is_ignored_path(rel: str) -> bool:
    name = Path(rel).name
    if " " in name:
        return True
    # 历史备份命名，如 theme_processor_0201.py
    if re.search(r"_\d{4}\.py$", name):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 execute_query gate (business path must be zero)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="json report path")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when non-allowlisted usage exists")
    args = parser.parse_args()

    violations: list[dict] = []
    allowlisted_hits: list[dict] = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for file_path in scan_dir.rglob("*.py"):
            rel = str(file_path.relative_to(ROOT))
            if any(part in rel for part in ("/tests/", "/scripts/", "/docs/")):
                continue
            if _is_ignored_path(rel):
                continue
            text = file_path.read_text(encoding="utf-8")
            for match in PATTERN.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                hit = {"path": rel, "line": line_no}
                if rel in ALLOWLIST or rel.startswith(ALLOW_PREFIXES):
                    allowlisted_hits.append(hit)
                else:
                    violations.append(hit)

    report = {
        "task": "P3.phase1-T07",
        "violations": violations,
        "violation_count": len(violations),
        "allowlisted_hits": allowlisted_hits,
        "allowlisted_count": len(allowlisted_hits),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[execute-query-gate] violations={report['violation_count']} "
        f"allowlisted={report['allowlisted_count']}"
    )
    print(f"[execute-query-gate] report={output}")
    if args.strict and report["violation_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
