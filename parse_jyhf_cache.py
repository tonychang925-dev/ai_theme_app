#!/usr/bin/env python3
"""
JYHF Chromium Cache Parser

直接解析久赢恒丰 Electron 应用的 Chromium Simple Cache，
提取 subject/top-history 等 API 响应，输出 JSONL 文件。

用法:
  python parse_jyhf_cache.py --date 2026-05-06
  python parse_jyhf_cache.py --all  # 提取所有缓存数据
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import struct
import sys
import zlib
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

CACHE_DIR = Path.home() / "Library/Application Support/jyhf/Cache/Cache_Data"
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "theme_data_complete"
HISTORY_DIR = OUTPUT_DIR / "history"
MANIFEST_DIR = OUTPUT_DIR / "_manifests"

# Simple Cache magic number
SIMPLE_CACHE_MAGIC = 0xfcfb6d1ba7725c30


def decompress(data: bytes) -> Optional[bytes]:
    """Try multiple decompression methods on cached response body."""
    for wbits in [16 + zlib.MAX_WBITS, 15 + zlib.MAX_WBITS, -15]:
        try:
            return zlib.decompress(data, wbits)
        except Exception:
            continue
    try:
        return gzip.decompress(data)
    except Exception:
        return None


def extract_url_and_body(filepath: Path) -> tuple[Optional[str], Optional[bytes]]:
    """Extract URL and response body from a Simple Cache entry file."""
    try:
        data = filepath.read_bytes()
    except Exception:
        return None, None

    if len(data) < 24:
        return None, None

    magic = struct.unpack_from('<Q', data, 0)[0]
    if magic != SIMPLE_CACHE_MAGIC:
        return None, None

    # Find URL (starts with https://)
    url_match = re.search(rb'https://[^\x00\x1f\x08]+', data)
    if not url_match:
        return None, None

    url = url_match.group(0).decode('latin-1', errors='replace')

    # Find gzip body (starts with \x1f\x8b)
    gzip_idx = data.find(b'\x1f\x8b', url_match.end())
    if gzip_idx < 0:
        return None, None

    body = decompress(data[gzip_idx:])
    return url, body


def parse_top_history(body: bytes) -> list[dict]:
    """Parse a subject/top-history API response into structured rows."""
    try:
        raw = json.loads(body)
        # Response might be a hex string (encrypted) or a dict
        if isinstance(raw, str):
            # Try parsing again (double-encoded)
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, dict):
        return []

    rows = raw.get("data") or raw.get("rows") or []
    if not isinstance(rows, list):
        return []

    return rows


def scan_cache(target_endpoints: list[str] | None = None) -> dict[str, list[tuple[str, list[dict]]]]:
    """Scan all cache files and extract responses for specified endpoints.

    Returns dict mapping endpoint_pattern -> list of (url, rows)
    """
    if not CACHE_DIR.exists():
        print(f"[ERROR] Cache dir not found: {CACHE_DIR}")
        return {}

    results: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    files = sorted(CACHE_DIR.iterdir())
    total = len(files)
    print(f"[SCAN] {total} cache files...")

    for i, fpath in enumerate(files):
        if i % 1000 == 0:
            print(f"  {i}/{total}...")

        url, body = extract_url_and_body(fpath)
        if not url or not body:
            continue

        # Match against target endpoints
        for endpoint in (target_endpoints or ["subject/top-history"]):
            if endpoint in url:
                rows = parse_top_history(body)
                if rows:
                    results[endpoint].append((url, rows))
                break

    for endpoint, entries in results.items():
        total_rows = sum(len(r) for _, r in entries)
        print(f"[SCAN] {endpoint}: {len(entries)} responses, {total_rows} rows")

    return results


def extract_by_date(results: dict, target_date: str) -> list[dict]:
    """Extract rows for a specific date from cache results."""
    td = date.fromisoformat(target_date)
    td_str = td.strftime("%Y-%m-%d")

    all_rows = []
    seen = set()

    for endpoint, entries in results.items():
        for url, rows in entries:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                create_time = row.get("createTime", "")
                rank_date = row.get("rankDate", "")
                # Check if this row belongs to target date
                if td_str in str(create_time) or td_str in str(rank_date):
                    key = f"{row.get('subjectId')}_{row.get('createTime')}"
                    if key not in seen:
                        seen.add(key)
                        all_rows.append(row)

    print(f"[DATE] {target_date}: {len(all_rows)} rows")
    return all_rows


def main():
    parser = argparse.ArgumentParser(description="Parse JYHF Chromium cache")
    parser.add_argument("--date", help="Target trade date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Extract all cached data")
    parser.add_argument("--endpoints", default="subject/top-history",
                        help="Comma-separated endpoints to extract (default: subject/top-history)")
    args = parser.parse_args()

    endpoints = [e.strip() for e in args.endpoints.split(",")]

    # Scan cache
    results = scan_cache(endpoints)
    if not results:
        print("[DONE] No matching cache entries found")
        return 1

    # Extract by date
    if args.date:
        rows = extract_by_date(results, args.date)
        if not rows:
            print(f"[DONE] No rows found for {args.date}")
            return 0

        # Save to per-subject JSONL files
        by_subject: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            sid = str(row.get("subjectId", ""))
            if sid:
                by_subject[sid].append(row)

        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        saved = 0
        for sid, subject_rows in by_subject.items():
            fpath = HISTORY_DIR / f"{sid}_history.jsonl"
            # Merge with existing
            existing = []
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            existing.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
            # Deduplicate
            existing_keys = {(r.get("subjectRankId"), r.get("createTime")) for r in existing}
            new_rows = [r for r in subject_rows
                        if (r.get("subjectRankId"), r.get("createTime")) not in existing_keys]
            if new_rows:
                all_rows = existing + new_rows
                with open(fpath, "w", encoding="utf-8") as f:
                    for r in all_rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                saved += 1

        print(f"[SAVE] {len(rows)} rows across {saved} subject files")

        # Save manifest
        batch_id = f"cache_jyhf_{args.date.replace('-', '')}"
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        manifest = {
            "batch_id": batch_id,
            "timestamp": datetime.now().isoformat(),
            "date": args.date,
            "rows": len(rows),
            "subjects": saved,
            "source": "chromium_cache_parser",
        }
        (MANIFEST_DIR / f"{batch_id}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"[DONE] Complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
