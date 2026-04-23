#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]


FORBIDDEN_IMPORT_RE = re.compile(
    r"from\s+stock_service\.services\.theme_cycle_judgement_service\s+import\s+ThemeCycleJudgementService"
)
FORBIDDEN_CALL_RE = re.compile(r"\bThemeCycleJudgementService\s*\(")
ALLOW_LEGACY_RE = re.compile(r"\bThemeCycleJudgementService\s*\(\s*.*allow_legacy\s*=\s*True")


DEFAULT_SCAN_ROOTS = (
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "stock_service" / "scripts",
    PROJECT_ROOT / "database_service" / "scripts",
)


DEFAULT_IGNORE_PATTERNS = (
    "*/tests/*",
    "*/legacy/*",
    "*/.venv/*",
    "*/__pycache__/*",
    str(PROJECT_ROOT / "stock_service" / "services" / "theme_cycle_judgement_service.py"),
    str(PROJECT_ROOT / "stock_service" / "scripts" / "run_cycle_backfill_and_monitor.py"),
    str(PROJECT_ROOT / "stock_service" / "scripts" / "build_theme_cycle_judgement_v2.py"),
)


def _iter_py_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            yield path


def _is_ignored(path: Path, ignore_patterns: Iterable[str]) -> bool:
    p = str(path)
    for pattern in ignore_patterns:
        if "*" in pattern:
            if path.match(pattern):
                return True
        elif p == pattern:
            return True
    return False


def _check_file(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings: List[str] = []
    has_import = bool(FORBIDDEN_IMPORT_RE.search(text))
    has_call = bool(FORBIDDEN_CALL_RE.search(text))
    has_allow = bool(ALLOW_LEGACY_RE.search(text))

    if has_import or has_call:
        if has_allow:
            findings.append("legacy_service_used_with_allow_legacy_true")
        else:
            findings.append("legacy_service_used_without_allow_legacy")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect legacy ThemeCycleJudgementService entrypoints in production scripts."
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        default=[str(x) for x in DEFAULT_SCAN_ROOTS],
        help="Scan roots (default: scripts/, stock_service/scripts/, database_service/scripts/)",
    )
    parser.add_argument(
        "--allow-legacy-warn-only",
        action="store_true",
        help="仅告警 allow_legacy=True（默认严格阻断）。",
    )
    args = parser.parse_args()

    roots = [Path(x).resolve() for x in args.roots]
    bad = []
    allow_only = []
    for path in _iter_py_files(roots):
        if _is_ignored(path, DEFAULT_IGNORE_PATTERNS):
            continue
        findings = _check_file(path)
        if not findings:
            continue
        if "legacy_service_used_without_allow_legacy" in findings:
            bad.append(path)
        elif "legacy_service_used_with_allow_legacy_true" in findings:
            allow_only.append(path)

    if allow_only:
        for path in sorted(allow_only):
            print(f"[WARN] legacy_allowlisted_usage: {path}")
    if bad:
        for path in sorted(bad):
            print(f"[ERROR] legacy_entrypoint_detected: {path}")
        return 2
    if allow_only and not args.allow_legacy_warn_only:
        return 3

    print("[OK] no_legacy_cycle_entrypoints_detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
