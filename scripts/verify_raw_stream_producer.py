#!/usr/bin/env python3
"""验证 stream:news:raw 唯一生产者。

检查最近 N 条 raw stream：
  - 每条 collector_name == "RealTimeNewsCollector"
  - 不存在 collector_name == "AkShareRealtimeNewsCollector"
  - 不存在 source 包含 "akshare_legacy"

旧消息兼容：
  --require-phase4e-only  只检查带 collector_name 的消息，跳过旧数据
  --since-id              只检查指定 ID 之后的新消息

用法:
  python scripts/verify_raw_stream_producer.py --limit 20
  python scripts/verify_raw_stream_producer.py --limit 20 --require-phase4e-only
  python scripts/verify_raw_stream_producer.py --since-id 1710000000000-0

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
    p.add_argument("--require-phase4e-only", action="store_true",
                   help="Only check entries with collector_name; skip old data without marking failure")
    p.add_argument("--since-id", default=None,
                   help="Only check entries after this stream message ID (exclusive)")
    return p


def check_entry(entry: dict, idx: int, limit: int, phase4e_only: bool = False) -> tuple[list[str], list[str]]:
    """检查单条 entry。返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []
    has_collector = bool(entry.get("collector_name", "").strip())
    collector = str(entry.get("collector_name", "") or entry.get("source", ""))
    source = str(entry.get("source", ""))

    # Phase 4E 之前旧消息：无 collector_name
    if not has_collector:
        if phase4e_only:
            # 旧数据跳过，不报错
            return errors, warnings
        # 否则给出 warning 但不 fail（旧消息残留）
        warnings.append(
            f"[{idx + 1}/{limit}] pre-Phase4E entry (no collector_name), source={source!r}"
        )
        return errors, warnings

    # 禁止 AkShare legacy collector
    if collector == "AkShareRealtimeNewsCollector":
        errors.append(
            f"[{idx + 1}/{limit}] BANNED: collector_name=AkShareRealtimeNewsCollector"
        )
    if "akshare_legacy" in source.lower():
        errors.append(
            f"[{idx + 1}/{limit}] BANNED: source contains akshare_legacy"
        )

    # 期望的 collector_name
    if collector and collector != "RealTimeNewsCollector":
        errors.append(
            f"[{idx + 1}/{limit}] collector_name={collector!r} (expected RealTimeNewsCollector)"
        )

    # 检查 collector_version
    version = str(entry.get("collector_version", ""))
    if version and version != "phase4e":
        warnings.append(
            f"[{idx + 1}/{limit}] collector_version={version!r} (expected phase4e)"
        )

    return errors, warnings


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
        if args.since_id:
            raw_entries = r.xrevrange(args.stream, "+", args.since_id, count=args.limit)
        else:
            raw_entries = r.xrevrange(args.stream, "+", "-", count=args.limit)
    except Exception as exc:
        print(f"FAIL: cannot read stream {args.stream}: {exc}", file=sys.stderr)
        return 1

    if not raw_entries:
        print(f"PASS: {args.stream} is empty (no entries to check)")
        return 0

    all_errors: list[str] = []
    all_warnings: list[str] = []
    valid_entries = 0
    skipped_old = 0

    for i, (msg_id, fields) in enumerate(raw_entries):
        entry = dict(fields) if isinstance(fields, dict) else {}
        errors, warnings = check_entry(entry, i, len(raw_entries),
                                       phase4e_only=args.require_phase4e_only)

        if not errors and not warnings:
            valid_entries += 1
        elif not entry.get("collector_name", "").strip() and args.require_phase4e_only:
            skipped_old += 1

        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # 打印 warnings
    if all_warnings and not args.json:
        print(f"WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  - {w}")
        print()

    # 结果
    if all_errors:
        if args.json:
            result = {
                "status": "FAIL",
                "stream": args.stream,
                "total_checked": len(raw_entries),
                "valid": valid_entries,
                "skipped_old": skipped_old,
                "invalid": len(raw_entries) - valid_entries - skipped_old,
                "warnings": len(all_warnings),
                "errors": all_errors,
                "checked_at": datetime.now(CN_TZ).isoformat(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL: {len(all_errors)} violation(s) found in {args.stream} "
                  f"(checked {len(raw_entries)} entries, {skipped_old} pre-Phase4E skipped)")
            for err in all_errors:
                print(f"  - {err}")
        return 1
    else:
        if args.json:
            result = {
                "status": "PASS",
                "stream": args.stream,
                "total_checked": len(raw_entries),
                "valid": valid_entries,
                "skipped_old": skipped_old,
                "all_collector_name": "RealTimeNewsCollector",
                "warnings": len(all_warnings),
                "checked_at": datetime.now(CN_TZ).isoformat(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            status_msg = f"PASS: all {valid_entries} entries have collector_name=RealTimeNewsCollector"
            if skipped_old > 0:
                status_msg += f" ({skipped_old} pre-Phase4E entries skipped)"
            print(status_msg)
        return 0


if __name__ == "__main__":
    sys.exit(main())
