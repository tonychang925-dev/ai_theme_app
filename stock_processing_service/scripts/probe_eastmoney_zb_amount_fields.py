#!/usr/bin/env python3
"""Probe Eastmoney ZB endpoint amount-field capability.

PR4.2.28d verification-only tool. It does not persist data and is not used by
ReviewDocument generation. The script answers whether getTopicZBPool can return
an amount-like field when requested with f6/f62/f116.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx


EM_BASE = "https://push2ex.eastmoney.com"
EM_UT = "7eea3edcaed734bea9cbfc24409ed989"
ZB_AMOUNT_FIELD_CANDIDATES = ("amount", "f6", "F6", "成交额", "f62", "F62", "f116", "F116")
ZB_PROBE_FIELDS = "f12,f14,f2,f3,f4,f6,f7,f15,f16,f17,f62,f116,f184,f127"


def build_zb_probe_params(trade_date: date, page_size: int) -> dict[str, Any]:
    return {
        "ut": EM_UT,
        "dpt": "wz.ztzt",
        "sort": "fbt:asc",
        "date": trade_date.strftime("%Y%m%d"),
        "pageindex": 0,
        "pagesize": page_size,
        "fields": ZB_PROBE_FIELDS,
    }


def extract_pool(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    pool = data.get("pool")
    if not isinstance(pool, list):
        return []
    return [item for item in pool if isinstance(item, dict)]


def amount_field_hits(item: dict[str, Any]) -> dict[str, Any]:
    hits: dict[str, Any] = {}
    for key in ZB_AMOUNT_FIELD_CANDIDATES:
        value = item.get(key)
        if value not in (None, "", 0, 0.0, "0"):
            hits[key] = value
    return hits


def summarize_capability(payload: dict[str, Any]) -> dict[str, Any]:
    pool = extract_pool(payload)
    keys = sorted({key for item in pool for key in item.keys()})
    amount_rows = []
    candidate_counts = {key: 0 for key in ZB_AMOUNT_FIELD_CANDIDATES}

    for item in pool:
        hits = amount_field_hits(item)
        if hits:
            amount_rows.append(
                {
                    "code": item.get("c") or item.get("code") or item.get("f12"),
                    "name": item.get("n") or item.get("name") or item.get("f14"),
                    "amount_fields": hits,
                }
            )
            for key in hits:
                candidate_counts[key] += 1

    supported = bool(amount_rows)
    return {
        "endpoint": "getTopicZBPool",
        "requested_fields": ZB_PROBE_FIELDS,
        "row_count": len(pool),
        "response_keys": keys,
        "amount_candidate_counts": {key: count for key, count in candidate_counts.items() if count > 0},
        "examples": amount_rows[:5],
        "capability": "SUPPORTED" if supported else "UNAVAILABLE",
        "decision": (
            "ZB amount can be normalized from endpoint response after collector mapping."
            if supported
            else "ZB amount is not proven by this response; keep BoardPoolSnapshot.zb.amount_yi MISSING."
        ),
    }


def summarize_fetch_error(error: Exception) -> dict[str, Any]:
    return {
        "endpoint": "getTopicZBPool",
        "requested_fields": ZB_PROBE_FIELDS,
        "row_count": 0,
        "response_keys": [],
        "amount_candidate_counts": {},
        "examples": [],
        "capability": "UNKNOWN",
        "error_type": type(error).__name__,
        "error": str(error),
        "decision": "Live endpoint capability was not verified; keep BoardPoolSnapshot.zb.amount_yi MISSING.",
    }


async def fetch_payload(trade_date: date, page_size: int, timeout: float) -> dict[str, Any]:
    params = build_zb_probe_params(trade_date, page_size)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{EM_BASE}/getTopicZBPool", params=params)
        response.raise_for_status()
        return response.json()


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Eastmoney ZB amount fields.")
    parser.add_argument("--date", default="2026-07-09", help="Trade date YYYY-MM-DD.")
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--fixture", type=Path, help="Read a saved raw response instead of calling Eastmoney.")
    args = parser.parse_args()

    if args.fixture:
        payload = load_fixture(args.fixture)
        result = summarize_capability(payload)
    else:
        try:
            payload = await fetch_payload(date.fromisoformat(args.date), args.page_size, args.timeout)
            result = summarize_capability(payload)
        except Exception as exc:  # noqa: BLE001 - probe must report endpoint failures as data.
            result = summarize_fetch_error(exc)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
