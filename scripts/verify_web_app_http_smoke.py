#!/usr/bin/env python3
import json
from pathlib import Path

files = {
    "sps_healthz": Path('/tmp/sps_healthz.json'),
    "web_healthz": Path('/tmp/web_healthz.json'),
    "post_market": Path('/tmp/web_post_market_snapshot.json'),
    "strong_watch": Path('/tmp/web_strong_watch.json'),
    "w2s": Path('/tmp/web_w2s_candidates.json'),
}

for name, p in files.items():
    if not p.exists() or p.stat().st_size == 0:
        raise SystemExit(f"missing or empty: {name} -> {p}")

sps = json.loads(files['sps_healthz'].read_text())
web = json.loads(files['web_healthz'].read_text())
pm = json.loads(files['post_market'].read_text())
sw = json.loads(files['strong_watch'].read_text())
w2s = json.loads(files['w2s'].read_text())

assert sps.get('status') == 'ok', sps
assert web.get('status') == 'ok', web
assert 'trade_date' in pm and 'payload' in pm, pm
assert 'trade_date' in sw and 'stocks' in sw, sw
assert 'trade_date' in w2s and 'candidates' in w2s, w2s

print(json.dumps({
    'ok': True,
    'sps_db': sps.get('db'),
    'post_market_trade_date': pm.get('trade_date'),
    'strong_watch_count': len(sw.get('stocks') or []),
    'w2s_count': len(w2s.get('candidates') or []),
}, ensure_ascii=False))
