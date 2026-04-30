#!/usr/bin/env python3
"""Guardrail: frontend freeze.

Fail CI if frontend source introduces calls to new-chain endpoints or
backend internals that should only live in web_app_service.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path('frontend/src')
ALLOWED_FILE_SUFFIX = {'.ts', '.tsx', '.js', '.jsx'}

# Patterns that should not appear in frozen legacy frontend source.
FORBIDDEN = {
    'api_v2_route': re.compile(r"['\"]\s*/api/v2/", re.IGNORECASE),
    'sps_direct_ref': re.compile(r"stock_processing_service|DatabaseGateway|database_service", re.IGNORECASE),
}


def main() -> int:
    if not ROOT.exists():
        print('frontend freeze guard skipped: frontend/src not found')
        return 0

    violations: list[tuple[str, int, str, str]] = []

    for p in ROOT.rglob('*'):
        if p.is_dir() or p.suffix.lower() not in ALLOWED_FILE_SUFFIX:
            continue
        text = p.read_text(encoding='utf-8', errors='ignore')
        for i, line in enumerate(text.splitlines(), start=1):
            for rule, pat in FORBIDDEN.items():
                if pat.search(line):
                    violations.append((str(p), i, rule, line.strip()[:220]))

    if not violations:
        print('frontend freeze guard passed')
        return 0

    print('frontend freeze guard failed: forbidden patterns found')
    for file, line, rule, snippet in violations:
        print(f'- {file}:{line} [{rule}] {snippet}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
