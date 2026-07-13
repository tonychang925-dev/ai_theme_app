#!/usr/bin/env python3
"""Probe Eastmoney stock fund-flow field capability.

PR4.2.31c-1 verification-only tool. It does not persist data and is not used by
ReviewDocument generation. The script answers whether a candidate Eastmoney
endpoint can return stock-level order-size fund-flow fields.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx


EM_BASE_URLS = (
    "https://push2.eastmoney.com/api/qt/clist/get",
    "http://push2.eastmoney.com/api/qt/clist/get",
)
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"
SOURCE_VERSION = "eastmoney_fund_flow_f62_mapping_v1"
ENDPOINT_KEY = "eastmoney_stock_fund_flow"
MARKET_SCOPE = "CN_A"
FREQUENCY = "DAILY"
WINDOW = "1D"

# Candidate Eastmoney all-A universe used by many quote-list endpoints.
CN_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

FUND_FLOW_FIELDS = "f12,f14,f62,f66,f72,f78,f84"
EASTMONEY_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "close",
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}
FIELD_MAPPING = {
    "f62": {"meaning": "net_inflow_yuan", "unit": "yuan"},
    "f66": {"meaning": "super_large_net_inflow_yuan", "unit": "yuan"},
    "f72": {"meaning": "large_net_inflow_yuan", "unit": "yuan"},
    "f78": {"meaning": "medium_net_inflow_yuan", "unit": "yuan"},
    "f84": {"meaning": "small_net_inflow_yuan", "unit": "yuan"},
}


def build_probe_params(page_size: int) -> dict[str, Any]:
    return {
        "fields": FUND_FLOW_FIELDS,
        "fltt": 2,
        "pn": 1,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": EM_UT,
        "fid": "f62",
        "fs": CN_A_FS,
    }


def extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("diff")
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def _is_number(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def field_hits(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in FIELD_MAPPING if _is_number(item.get(field))}


def summarize_capability(payload: dict[str, Any], request_url: str = EM_BASE_URLS[0]) -> dict[str, Any]:
    rows = extract_rows(payload)
    keys = sorted({key for row in rows for key in row.keys()})
    candidate_counts = {field: 0 for field in FIELD_MAPPING}
    examples = []

    for row in rows:
        hits = field_hits(row)
        if hits:
            examples.append(
                {
                    "code": row.get("f12") or row.get("code") or row.get("stock_code"),
                    "name": row.get("f14") or row.get("name") or row.get("stock_name"),
                    "fund_flow_fields": hits,
                }
            )
            for field in hits:
                candidate_counts[field] += 1

    required_supported = all(candidate_counts[field] > 0 for field in FIELD_MAPPING)
    return {
        "endpoint": ENDPOINT_KEY,
        "request_url": request_url,
        "requested_fields": FUND_FLOW_FIELDS,
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "source_version": SOURCE_VERSION,
        "field_mapping": FIELD_MAPPING,
        "row_count": len(rows),
        "response_keys": keys,
        "field_candidate_counts": {key: count for key, count in candidate_counts.items() if count > 0},
        "examples": examples[:5],
        "capability": "SUPPORTED" if required_supported else "UNAVAILABLE",
        "decision": (
            "Stock fund-flow fields can be normalized after collector mapping."
            if required_supported
            else "Stock fund-flow capability is not proven by this response; do not add collector."
        ),
        "production_write_allowed": False,
    }


def summarize_fetch_error(error: Exception) -> dict[str, Any]:
    return {
        "endpoint": ENDPOINT_KEY,
        "request_url": EM_BASE_URLS[0],
        "requested_fields": FUND_FLOW_FIELDS,
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "source_version": SOURCE_VERSION,
        "field_mapping": FIELD_MAPPING,
        "row_count": 0,
        "response_keys": [],
        "field_candidate_counts": {},
        "examples": [],
        "capability": "UNKNOWN",
        "error_type": type(error).__name__,
        "error": str(error),
        "decision": "Live endpoint capability was not verified; do not add collector.",
        "production_write_allowed": False,
    }


def summarize_all_fetch_errors(errors: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "endpoint": ENDPOINT_KEY,
        "request_url": EM_BASE_URLS[0],
        "candidate_urls": list(EM_BASE_URLS),
        "requested_fields": FUND_FLOW_FIELDS,
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "source_version": SOURCE_VERSION,
        "field_mapping": FIELD_MAPPING,
        "row_count": 0,
        "response_keys": [],
        "field_candidate_counts": {},
        "examples": [],
        "capability": "UNKNOWN",
        "errors": errors,
        "decision": "Live endpoint capability was not verified; do not add collector.",
        "production_write_allowed": False,
    }


async def fetch_payload(page_size: int, timeout: float) -> tuple[dict[str, Any], str]:
    params = build_probe_params(page_size)
    errors: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=timeout, headers=EASTMONEY_HEADERS, follow_redirects=True) as client:
        for url in EM_BASE_URLS:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json(), str(response.url)
            except Exception as exc:  # noqa: BLE001 - probe must continue to the next candidate.
                errors.append(
                    {
                        "request_url": url,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
    raise ProbeFetchError(errors)


class ProbeFetchError(Exception):
    """All candidate Eastmoney probe URLs failed."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("All Eastmoney fund-flow probe candidates failed.")
        self.errors = errors


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Eastmoney stock fund-flow fields.")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--fixture", type=Path, help="Read a saved raw response instead of calling Eastmoney.")
    args = parser.parse_args()

    if args.fixture:
        payload = load_fixture(args.fixture)
        result = summarize_capability(payload, request_url=f"fixture://{args.fixture}")
    else:
        try:
            payload, request_url = await fetch_payload(args.page_size, args.timeout)
            result = summarize_capability(payload, request_url=request_url)
        except ProbeFetchError as exc:
            result = summarize_all_fetch_errors(exc.errors)
        except Exception as exc:  # noqa: BLE001 - probe must report endpoint failures as data.
            result = summarize_fetch_error(exc)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
