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
import os
from pathlib import Path
from typing import Any

import httpx
import requests


EM_BASE_URLS = (
    "https://push2.eastmoney.com/api/qt/clist/get",
    "http://push2.eastmoney.com/api/qt/clist/get",
)
EM_STOCK_FFLOW_DAYKLINE_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
    "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
)
EM_STOCK_FFLOW_KLINE_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get",
    "http://push2his.eastmoney.com/api/qt/stock/fflow/kline/get",
)
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"
QUOTE_LIST_SOURCE_VERSION = "eastmoney_fund_flow_f62_mapping_v1"
KLINE_SOURCE_VERSION = "eastmoney_fflow_daykline_f52_v1"
ENDPOINT_KEY = "eastmoney_stock_fund_flow"
MARKET_SCOPE = "CN_A"
FREQUENCY = "DAILY"
WINDOW = "1D"
KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"

# Candidate Eastmoney all-A universe used by many quote-list endpoints.
CN_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

FUND_FLOW_FIELDS = "f12,f14,f62,f66,f72,f78,f84"
EASTMONEY_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://quote.eastmoney.com",
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
KLINE_FIELD_MAPPING = {
    "f51": {"meaning": "timestamp_or_date", "unit": "text"},
    "f52": {"meaning": "net_inflow_yuan", "unit": "yuan"},
    "f53": {"meaning": "small_net_inflow_yuan", "unit": "yuan"},
    "f54": {"meaning": "medium_net_inflow_yuan", "unit": "yuan"},
    "f55": {"meaning": "large_net_inflow_yuan", "unit": "yuan"},
    "f56": {"meaning": "super_large_net_inflow_yuan", "unit": "yuan"},
}
PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


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


def secid_from_stock_code(stock_code: str) -> str:
    code = stock_code.strip().upper().split(".")[0]
    market = "1" if code.startswith("6") else "0"
    return f"{market}.{code}"


def build_stock_fflow_daykline_params(stock_code: str, limit: int) -> dict[str, Any]:
    return {
        "secid": secid_from_stock_code(stock_code),
        "lmt": str(limit),
        "fields1": "f1,f2,f3,f7",
        "fields2": KLINE_FIELDS2,
    }


def build_stock_fflow_kline_params(stock_code: str, limit: int) -> dict[str, Any]:
    return {
        "ut": EM_UT,
        "secid": secid_from_stock_code(stock_code),
        "lmt": limit,
        "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": KLINE_FIELDS2,
    }


def extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("diff")
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def extract_klines(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    klines = data.get("klines")
    if not isinstance(klines, list):
        return []
    return [item for item in klines if isinstance(item, str)]


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
        "source_version": QUOTE_LIST_SOURCE_VERSION,
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


def summarize_kline_capability(
    payload: dict[str, Any],
    *,
    endpoint: str,
    request_url: str,
    frequency: str,
    window: str,
) -> dict[str, Any]:
    klines = extract_klines(payload)
    examples = []
    candidate_counts = {field: 0 for field in ("f52", "f53", "f54", "f55", "f56")}

    for raw in klines:
        parts = raw.split(",")
        if len(parts) < 6:
            continue
        values = {
            "f51": parts[0],
            "f52": parts[1],
            "f53": parts[2],
            "f54": parts[3],
            "f55": parts[4],
            "f56": parts[5],
        }
        hits = {field: values[field] for field in candidate_counts if _is_number(values[field])}
        if hits:
            for field in hits:
                candidate_counts[field] += 1
            examples.append({"raw": raw, "fund_flow_fields": hits})

    required_supported = all(candidate_counts[field] > 0 for field in candidate_counts)
    return {
        "endpoint": endpoint,
        "request_url": request_url,
        "requested_fields": KLINE_FIELDS2,
        "frequency": frequency,
        "window": window,
        "market_scope": MARKET_SCOPE,
        "source_version": KLINE_SOURCE_VERSION,
        "field_mapping": KLINE_FIELD_MAPPING,
        "row_count": len(klines),
        "response_keys": sorted(payload.get("data", {}).keys()) if isinstance(payload.get("data"), dict) else [],
        "field_candidate_counts": {key: count for key, count in candidate_counts.items() if count > 0},
        "examples": examples[:5],
        "capability": "SUPPORTED" if required_supported else "UNAVAILABLE",
        "decision": (
            "Stock fflow kline fields can be normalized after collector mapping."
            if required_supported
            else "Stock fflow kline capability is not proven by this response; do not add collector."
        ),
        "production_write_allowed": False,
    }


def summarize_endpoint_error(endpoint: str, url: str, error: Exception, *, transport: str = "") -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "request_url": url,
        **({"transport": transport} if transport else {}),
        "capability": "UNKNOWN",
        "error_type": type(error).__name__,
        "error": str(error),
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
        "source_version": QUOTE_LIST_SOURCE_VERSION,
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
        "source_version": QUOTE_LIST_SOURCE_VERSION,
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


def proxy_env_diagnostics() -> dict[str, bool]:
    return {key: bool(os.environ.get(key)) for key in PROXY_ENV_KEYS}


async def fetch_endpoint_result(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    url: str,
    params: dict[str, Any],
    frequency: str,
    window: str,
) -> dict[str, Any]:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - probe must report endpoint failures as data.
        return summarize_endpoint_error(endpoint, url, exc, transport="httpx")

    if endpoint == "eastmoney_stock_fund_flow_quote_list":
        result = summarize_capability(payload, request_url=str(response.url))
        result["endpoint"] = endpoint
        result["transport"] = "httpx"
        return result
    result = summarize_kline_capability(
        payload,
        endpoint=endpoint,
        request_url=str(response.url),
        frequency=frequency,
        window=window,
    )
    result["transport"] = "httpx"
    return result


def fetch_endpoint_result_requests(
    session: requests.Session,
    *,
    endpoint: str,
    url: str,
    params: dict[str, Any],
    frequency: str,
    window: str,
    timeout: float,
) -> dict[str, Any]:
    try:
        response = session.get(url, params=params, headers=EASTMONEY_HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - probe must report endpoint failures as data.
        return summarize_endpoint_error(endpoint, url, exc, transport="requests_session")

    if endpoint == "eastmoney_stock_fund_flow_quote_list":
        result = summarize_capability(payload, request_url=response.url)
        result["endpoint"] = endpoint
        result["transport"] = "requests_session"
        return result
    result = summarize_kline_capability(
        payload,
        endpoint=endpoint,
        request_url=response.url,
        frequency=frequency,
        window=window,
    )
    result["transport"] = "requests_session"
    return result


def _candidate_specs(page_size: int, stock_code: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for url in EM_BASE_URLS:
        specs.append(
            {
                "endpoint": "eastmoney_stock_fund_flow_quote_list",
                "url": url,
                "params": build_probe_params(page_size),
                "frequency": "DAILY",
                "window": "1D",
            }
        )
    for url in EM_STOCK_FFLOW_DAYKLINE_URLS:
        specs.append(
            {
                "endpoint": "eastmoney_stock_fflow_daykline",
                "url": url,
                "params": build_stock_fflow_daykline_params(stock_code, page_size),
                "frequency": "DAILY",
                "window": "1D",
            }
        )
    for url in EM_STOCK_FFLOW_KLINE_URLS:
        specs.append(
            {
                "endpoint": "eastmoney_stock_fflow_kline",
                "url": url,
                "params": build_stock_fflow_kline_params(stock_code, page_size),
                "frequency": "INTRADAY",
                "window": "1MIN",
            }
        )
    return specs


async def discover_endpoint_capabilities(
    page_size: int,
    timeout: float,
    trust_env: bool,
    stock_code: str,
    transport: str = "both",
) -> dict[str, Any]:
    endpoint_results: list[dict[str, Any]] = []
    specs = _candidate_specs(page_size, stock_code)
    if transport in ("both", "httpx"):
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=EASTMONEY_HEADERS,
            follow_redirects=True,
            trust_env=trust_env,
        ) as client:
            for spec in specs:
                endpoint_results.append(
                    await fetch_endpoint_result(
                        client,
                        endpoint=spec["endpoint"],
                        url=spec["url"],
                        params=spec["params"],
                        frequency=spec["frequency"],
                        window=spec["window"],
                    )
                )
    if transport in ("both", "requests"):
        session = requests.Session()
        session.headers.update({"User-Agent": EASTMONEY_HEADERS["User-Agent"]})
        try:
            for spec in specs:
                endpoint_results.append(
                    fetch_endpoint_result_requests(
                        session,
                        endpoint=spec["endpoint"],
                        url=spec["url"],
                        params=spec["params"],
                        frequency=spec["frequency"],
                        window=spec["window"],
                        timeout=timeout,
                    )
                )
        finally:
            session.close()

    supported = [item for item in endpoint_results if item.get("capability") == "SUPPORTED"]
    return {
        "endpoint": ENDPOINT_KEY,
        "sample_stock_code": stock_code,
        "sample_secid": secid_from_stock_code(stock_code),
        "candidate_urls": [*EM_BASE_URLS, *EM_STOCK_FFLOW_DAYKLINE_URLS, *EM_STOCK_FFLOW_KLINE_URLS],
        "transport": transport,
        "endpoint_results": endpoint_results,
        "capability": "SUPPORTED" if supported else "UNKNOWN",
        "decision": (
            "At least one endpoint returned candidate fund-flow fields; review endpoint_results before collector."
            if supported
            else "Live endpoint capability was not verified; do not add collector."
        ),
        "production_write_allowed": False,
    }


async def fetch_payload(page_size: int, timeout: float, trust_env: bool) -> tuple[dict[str, Any], str]:
    params = build_probe_params(page_size)
    errors: list[dict[str, str]] = []
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=EASTMONEY_HEADERS,
        follow_redirects=True,
        trust_env=trust_env,
    ) as client:
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
    parser.add_argument("--stock-code", default="300223", help="Sample A-share stock code for single-stock endpoints.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="Allow httpx to use HTTP_PROXY/HTTPS_PROXY/ALL_PROXY from the environment.",
    )
    parser.add_argument(
        "--transport",
        choices=("both", "httpx", "requests"),
        default="both",
        help="HTTP transport to probe. Default compares httpx with requests.Session.",
    )
    parser.add_argument("--fixture", type=Path, help="Read a saved raw response instead of calling Eastmoney.")
    args = parser.parse_args()

    if args.fixture:
        payload = load_fixture(args.fixture)
        result = summarize_capability(payload, request_url=f"fixture://{args.fixture}")
    else:
        result = await discover_endpoint_capabilities(
            args.page_size,
            args.timeout,
            trust_env=args.trust_env,
            stock_code=args.stock_code,
            transport=args.transport,
        )

    result["trust_env"] = bool(args.trust_env)
    result["proxy_env_present"] = proxy_env_diagnostics()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
