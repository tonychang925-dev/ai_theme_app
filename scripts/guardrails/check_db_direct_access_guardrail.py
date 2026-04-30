#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

BASELINE = Path('.ci/db_direct_access_baseline.json')
SCAN = Path('scripts/guardrails/scan_db_direct_access.py')


def normalize(items):
    return {
        (i.get('file'), int(i.get('line')), i.get('rule'), i.get('snippet'))
        for i in items
    }


def main() -> int:
    if not BASELINE.exists():
        print(f"missing baseline: {BASELINE}")
        return 2
    if BASELINE.stat().st_size == 0:
        print(f"empty baseline: {BASELINE}")
        return 2

    proc = subprocess.run([sys.executable, str(SCAN)], capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return proc.returncode

    current = json.loads(proc.stdout or "[]")
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))

    curr_set = normalize(current)
    base_set = normalize(baseline)
    new_items = sorted(curr_set - base_set)

    if not new_items:
        print("DB direct-access guardrail passed: no new violations.")
        return 0

    print("DB direct-access guardrail failed: found new violations.")
    for file, line, rule, snippet in new_items:
        print(f"- {file}:{line} [{rule}] {snippet}")
    print("\nIf intentional, update .ci/db_direct_access_baseline.json in a dedicated review.")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
