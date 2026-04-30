#!/usr/bin/env python3
import json
import time
from collections import defaultdict
from pathlib import Path

BASELINE = Path('.ci/db_direct_access_baseline.json')
OUT = Path('tmp/frontend_bff_db_direct_access_inventory.json')


def classify(file_path: str, rule: str) -> str:
    p = file_path.replace('\\', '/')
    if not p.startswith('frontend_bff/'):
        return 'non_bff'
    if '/tests/' in p or p.endswith('_test.py') or '/test_' in p:
        return 'test_only'
    if p.endswith('.bak') or '.bak' in p or p.endswith('.before_fix') or p.endswith('.backup'):
        return 'backup_legacy'
    if p.startswith('frontend_bff/repositories/'):
        return 'prod_repository_direct_db'
    if p.startswith('frontend_bff/app.py'):
        return 'prod_app_sql'
    return 'prod_other'


def main() -> int:
    if not BASELINE.exists():
        print(f'missing {BASELINE}')
        return 2
    text = ""
    for _ in range(5):
        text = BASELINE.read_text(encoding='utf-8')
        if text.strip():
            break
        time.sleep(0.05)
    if not text.strip():
        print(f'empty baseline: {BASELINE}')
        return 2
    rows = json.loads(text)
    grouped = defaultdict(list)
    for row in rows:
        cat = classify(str(row.get('file', '')), str(row.get('rule', '')))
        grouped[cat].append(row)

    report = {
        'summary': {k: len(v) for k, v in sorted(grouped.items(), key=lambda kv: kv[0])},
        'items': grouped,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    print(f'written: {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
