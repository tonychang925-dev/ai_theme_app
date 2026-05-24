#!/usr/bin/env python3
"""验证 stream:news:raw 唯一生产者。

检查最近 N 条 raw stream：
  - 每条 collector_name == "RealTimeNewsCollector"
  - 不存在 collector_name == "AkShareRealtimeNewsCollector"
  - 不存在 source 包含 "akshare_legacy"

用法:
  python scripts/verify_raw_stream_producer.py --limit 20
  python scripts/verify_raw_stream_producer.py --redis-url redis://localhost:6379/0 --limit 20

退出码: 0=PASS, 1=FAIL
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from datetime import datetime, timezone

CN_TZ = timezone(__import__("datetime").timedelta(hours=8))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verify stream:news:raw unique producer")
    p.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    p.add_argument("--stream", default="stream:news:raw")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", help="Output JSON instead of text")
    return p


def check_entry(entry: dict, idx: int, limit: int) -> list[str]:
    """检查单条 entry。返回错误消息列表。"""
    errors: list[str] = []
    collector = str(entry.get("collector_name", "") or entry.get("source", ""))
    source = str(entry.get("source", ""))

    # 期望的 collector_name
    if collector and collector != "RealTimeNewsCollector":
        errors.append(
            f"[{idx + 1}/{limit}] collector_name={collector!r} (expected RealTimeNewsCollector)"
        )

    # 禁止 AkShare legacy
    if collector == "AkShareRealtimeNewsCollector":
        errors.append(
            f"[{idx + 1}/{limit}] BANNED: collector_name=AkShareRealtimeNewsCollector"
        )
    if "akshare_legacy" in source.lower():
        errors.append(
            f"[{idx + 1}/{limit}] BANNED: source contains akshare_legacy"
        )

    # 检查 collector_version
    version = str(entry.get("collector_version", ""))
    if version and version != "phase4e":
        errors.append(
            f"[{idx + 1}/{limit}] collector_version={version!r} (expected phase4e)"
        )

    return errors


def main() -> int:
    args = build_parser().parse_args()

    try:
        import redis
    except ImportError:
        print("FAIL: redis-py not installed. pip install redis", file=sys.stderr)
        return 1

    try:
        r = redis.from_url(args.redis_url, decode_responses=True)
    except Exception as exc:
        print(f"FAIL: cannot connect to Redis: {exc}", file=sys.stderr)
        return 1

    try:
        raw_entries = r.xrevrange(args.stream, "+", "-", count=args.limit)
    except Exception as exc:
        print(f"FAIL: cannot read stream {args.stream}: {exc}", file=sys.stderr)
        return 1

    if not raw_entries:
        print(f"PASS: {args.stream} is empty (no entries to check)")
        return 0

    all_errors: list[str] = []
    valid_entries = 0
    entry_details: list[dict] = []

    for i, (msg_id, fields) in enumerate(raw_entries):
        # fields from redis are flat key-value pairs, convert to dict
        entry = dict(fields) if isinstance(fields, dict) else {}
        errors = check_entry(entry, i, len(raw_entries))

        if errors:
            all_errors.extend(errors)
        else:
            valid_entries += 1

        entry_details.append({
            "msg_id": str(msg_id),
            "collector_name": entry.get("collector_name", ""),
            "collector_version": entry.get("collector_version", ""),
            "source": entry.get("source", ""),
            "title": str(entry.get("title", ""))[:80],
            "ok": len(errors) == 0,
        })

    # 结果
    if all_errors:
        if args.json:
            result = {
                "status": "FAIL",
                "stream": args.stream,
                "total_checked": len(raw_entries),
                "valid": valid_entries,
                "invalid": len(raw_entries) - valid_entries,
                "errors": all_errors,
                "checked_at": datetime.now(CN_TZ).isoformat(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL: {len(all_errors)} violation(s) found in {args.stream} (checked {len(raw_entries)} entries)")
            for err in all_errors:
                print(f"  - {err}")
        return 1
    else:
        if args.json:
            result = {
                "status": "PASS",
                "stream": args.stream,
                "total_checked": len(raw_entries),
                "all_collector_name": "RealTimeNewsCollector",
                "checked_at": datetime.now(CN_TZ).isoformat(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"PASS: all {valid_entries} entries have collector_name=RealTimeNewsCollector")
        return 0


if __name__ == "__main__":
    sys.exit(main())
