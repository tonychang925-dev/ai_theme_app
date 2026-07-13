#!/usr/bin/env python3
"""Probe Sina stock fund-flow backup endpoint capability.

PR4.2.31d verification-only tool. It does not persist data or participate in
report generation. The script answers whether a candidate Sina endpoint can
return stock-level vendor-defined order-size fund-flow evidence.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx


SOURCE_NAME = "sina_fund_flow"
SOURCE_VERSION = "sina_moneyflow_daily_probe_v1"
ENDPOINT_KEY = "sina_stock_fund_flow_daily"
MARKET_SCOPE = "CN_A"
FREQUENCY = "DAILY"
WINDOW = "1D"

SINA_DAILY_URLS = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs",
    "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs",
)

SINA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "close",
    "Referer": "https://finance.sina.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}

# Sina historical money-flow endpoints have changed labels over time. Keep this
# probe permissive: capability is confirmed only when all normalized facts can
# be mapped from actual response keys.
FIELD_ALIASES = {
    "net_inflow_yuan": (
        "netamount",
        "net_amount",
        "net_mf_amount",
        "main_net_amount",
        "zljlr",
        "主力净流入",
        "净流入",
    ),
    "super_large_net_inflow_yuan": (
        "r0_net",
        "r0_netamount",
        "r0_net_amount",
        "super_large_net",
        "super_large_net_amount",
        "超大单净流入",
    ),
    "large_net_inflow_yuan": (
        "r1_net",
        "r1_netamount",
        "r1_net_amount",
        "large_net",
        "large_net_amount",
        "大单净流入",
    ),
    "medium_net_inflow_yuan": (
        "r2_net",
        "r2_netamount",
        "r2_net_amount",
        "medium_net",
        "medium_net_amount",
        "中单净流入",
    ),
    "small_net_inflow_yuan": (
        "r3_net",
        "r3_netamount",
        "r3_net_amount",
        "small_net",
        "small_net_amount",
        "小单净流入",
    ),
}

DATE_ALIASES = ("opendate", "date", "trade_date", "日期")
PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def sina_symbol(stock_code: str) -> str:
    code = stock_code.strip().upper().split(".")[0]
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def build_sina_daily_params(stock_code: str, page_size: int) -> dict[str, Any]:
    return {
        "daima": sina_symbol(stock_code),
        "page": 1,
        "num": page_size,
        "sort": "opendate",
        "asc": 0,
    }


def _strip_jsonp(text: str) -> str:
    raw = text.strip()
    match = re.match(r"^[^(]+\((.*)\)\s*;?$", raw, flags=re.S)
    return match.group(1).strip() if match else raw


def parse_sina_payload(text: str) -> Any:
    raw = _strip_jsonp(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return raw


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _is_number(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _find_alias(row: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str, Any] | None:
    lowered = {str(key).lower(): key for key in row}
    for alias in aliases:
        key = lowered.get(alias.lower())
        if key is not None and _is_number(row.get(key)):
            return str(key), row.get(key)
    return None


def summarize_sina_capability(
    payload: Any,
    *,
    request_url: str = SINA_DAILY_URLS[0],
    stock_code: str = "300223",
) -> dict[str, Any]:
    rows = extract_rows(payload)
    response_keys = sorted({str(key) for row in rows for key in row})
    field_candidate_counts = {field: 0 for field in FIELD_ALIASES}
    resolved_mapping: dict[str, dict[str, str]] = {}
    examples: list[dict[str, Any]] = []

    for row in rows:
        normalized: dict[str, Any] = {}
        raw_keys: dict[str, str] = {}
        for field, aliases in FIELD_ALIASES.items():
            hit = _find_alias(row, aliases)
            if hit is None:
                continue
            key, value = hit
            normalized[field] = value
            raw_keys[field] = key
            field_candidate_counts[field] += 1
            resolved_mapping.setdefault(field, {"raw_key": key, "unit": "yuan"})
        if normalized:
            date_hit = next((row.get(key) for key in DATE_ALIASES if key in row), None)
            examples.append(
                {
                    "stock_code": stock_code,
                    "date": date_hit,
                    "fund_flow_fields": normalized,
                    "raw_keys": raw_keys,
                }
            )

    required_supported = all(field_candidate_counts[field] > 0 for field in FIELD_ALIASES)
    return {
        "source_name": SOURCE_NAME,
        "endpoint": ENDPOINT_KEY,
        "request_url": request_url,
        "source_version": SOURCE_VERSION,
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "semantics": "vendor_defined_order_size_proxy",
        "field_aliases": FIELD_ALIASES,
        "resolved_field_mapping": resolved_mapping,
        "row_count": len(rows),
        "response_keys": response_keys,
        "field_candidate_counts": {
            field: count for field, count in field_candidate_counts.items() if count > 0
        },
        "examples": examples[:5],
        "capability": "SUPPORTED" if required_supported else "UNKNOWN",
        "decision": (
            "Sina daily fund-flow fields can be normalized after collector mapping."
            if required_supported
            else "Sina fund-flow capability is not proven by this response; do not add collector."
        ),
        "production_write_allowed": False,
    }


def summarize_endpoint_error(endpoint: str, url: str, error: Exception) -> dict[str, Any]:
    return {
        "source_name": SOURCE_NAME,
        "endpoint": endpoint,
        "request_url": url,
        "capability": "UNKNOWN",
        "error_type": type(error).__name__,
        "error": str(error),
        "production_write_allowed": False,
    }


async def fetch_candidate(
    url: str,
    *,
    stock_code: str,
    page_size: int,
    timeout: float,
    trust_env: bool,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=SINA_HEADERS,
        follow_redirects=True,
        trust_env=trust_env,
    ) as client:
        response = await client.get(url, params=build_sina_daily_params(stock_code, page_size))
        response.raise_for_status()
        payload = parse_sina_payload(response.text)
        return summarize_sina_capability(
            payload,
            request_url=str(response.url),
            stock_code=stock_code,
        )


async def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    if args.fixture:
        payload = parse_sina_payload(Path(args.fixture).read_text(encoding="utf-8"))
        return summarize_sina_capability(payload, request_url=f"fixture://{args.fixture}", stock_code=args.stock_code)

    endpoint_results: list[dict[str, Any]] = []
    for url in SINA_DAILY_URLS:
        try:
            endpoint_results.append(
                await fetch_candidate(
                    url,
                    stock_code=args.stock_code,
                    page_size=args.page_size,
                    timeout=args.timeout,
                    trust_env=args.trust_env,
                )
            )
        except Exception as exc:
            endpoint_results.append(summarize_endpoint_error(ENDPOINT_KEY, url, exc))

    supported = [item for item in endpoint_results if item.get("capability") == "SUPPORTED"]
    result = supported[0] if supported else endpoint_results[0]
    return {
        **result,
        "candidate_urls": list(SINA_DAILY_URLS),
        "endpoint_results": endpoint_results,
        "sample_stock_code": args.stock_code,
        "sample_sina_symbol": sina_symbol(args.stock_code),
        "trust_env": args.trust_env,
        "proxy_env_present": {key: bool(os.environ.get(key)) for key in PROXY_ENV_KEYS},
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Sina fund-flow backup endpoint fields.")
    parser.add_argument("--stock-code", default="300223")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--trust-env", action="store_true")
    parser.add_argument("--fixture", default="")
    args = parser.parse_args()

    result = await run_probe(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    asyncio.run(main())
