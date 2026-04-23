#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "stock_processing_service"
DEFAULT_OUTPUT = ROOT / "tmp" / "p3_boundary_check_report.json"

# P3.phase1-T05: boundary gate for stock_processing_service
FORBIDDEN_PATTERNS: dict[str, re.Pattern[str]] = {
    "asyncpg_import": re.compile(r"\bimport\s+asyncpg\b|\bfrom\s+asyncpg\s+import\b"),
    "psycopg_import": re.compile(r"\bimport\s+psycopg\b|\bimport\s+psycopg2\b"),
    "sqlalchemy_import": re.compile(r"\bimport\s+sqlalchemy\b|\bfrom\s+sqlalchemy\s+import\b"),
    "raw_sql_literal": re.compile(r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b'),
    "client_pointer": re.compile(r"\b_client\b"),
    "db_pointer": re.compile(r"\b_db\b"),
}

# adapters may hold db-gateway refs by design.
ALLOW_PATH_PARTS = ("infrastructure/gateways/",)


def _is_allowed_path(path: Path) -> bool:
    path_s = path.as_posix()
    return any(part in path_s for part in ALLOW_PATH_PARTS)


def run_scan() -> dict:
    violations: list[dict] = []
    scanned_files = 0
    for file_path in TARGET_DIR.rglob("*.py"):
        scanned_files += 1
        text = file_path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN_PATTERNS.items():
            if _is_allowed_path(file_path) and name in {"client_pointer", "db_pointer"}:
                continue
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                violations.append(
                    {
                        "rule": name,
                        "path": str(file_path.relative_to(ROOT)),
                        "line": line_no,
                        "match": match.group(0)[:120],
                    }
                )
    return {
        "task": "P3.phase1-T05",
        "scanned_files": scanned_files,
        "violation_count": len(violations),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 boundary gate for stock_processing_service")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="json report path")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any violation")
    args = parser.parse_args()

    report = run_scan()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[boundary] scanned={report['scanned_files']} violations={report['violation_count']}")
    print(f"[boundary] report={output}")
    if args.strict and report["violation_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

