#!/usr/bin/env python3
"""Probe Tushare fund-flow capability.

PR4.2.31e audit-only tool. It does not persist data and is not used by
ReviewDocument generation. Returned values are vendor-defined fund-flow
evidence only; they are not institution or hot-money identities.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any


SOURCE_NAME = "tushare"
SOURCE_VERSION = "tushare_fund_flow_probe_v1"
MARKET_SCOPE = "CN_A"
FREQUENCY = "DAILY"
WINDOW = "1D"
PRODUCTION_WRITE_ALLOWED = False
SEMANTICS = "vendor_defined_order_size_or_cross_border_flow"

INTERFACE_FIELD_CONTRACTS: dict[str, dict[str, Any]] = {
    "moneyflow": {
        "source_endpoint": "tushare.moneyflow",
        "role": "stock_order_size_flow_native",
        "required_any": ("ts_code", "trade_date"),
        "expected_fields": (
            "ts_code",
            "trade_date",
            "buy_sm_vol",
            "sell_sm_vol",
            "buy_md_vol",
            "sell_md_vol",
            "buy_lg_vol",
            "sell_lg_vol",
            "buy_elg_vol",
            "sell_elg_vol",
            "net_mf_amount",
        ),
    },
    "moneyflow_ths": {
        "source_endpoint": "tushare.moneyflow_ths",
        "role": "stock_order_size_flow_ths",
        "required_any": ("ts_code", "trade_date"),
        "expected_fields": (
            "trade_date",
            "ts_code",
            "name",
            "net_amount",
            "net_d5_amount",
            "buy_lg_amount",
            "buy_lg_amount_rate",
            "buy_md_amount",
            "buy_md_amount_rate",
            "buy_sm_amount",
            "buy_sm_amount_rate",
        ),
    },
    "moneyflow_cnt_ths": {
        "source_endpoint": "tushare.moneyflow_cnt_ths",
        "role": "concept_fund_flow_ths",
        "required_any": ("trade_date",),
        "expected_fields": (
            "trade_date",
            "name",
            "lead_stock",
            "net_amount",
            "net_amount_rate",
            "buy_amount",
            "sell_amount",
            "pct_change",
            "company_num",
        ),
    },
    "moneyflow_hsgt": {
        "source_endpoint": "tushare.moneyflow_hsgt",
        "role": "cross_border_flow",
        "required_any": ("trade_date",),
        "expected_fields": (
            "trade_date",
            "ggt_ss",
            "ggt_sz",
            "hgt",
            "sgt",
            "north_money",
            "south_money",
        ),
    },
}

FORBIDDEN_INTERPRETATIONS = (
    "net_amount>0 -> institution_attention",
    "net_amount>0 -> hot_money_style",
    "moneyflow_ths -> ReviewDocument.capital.institution",
    "moneyflow_cnt_ths -> ReviewDocument.capital.hot_money",
)


def normalize_trade_date(value: str) -> str:
    return value.strip().replace("-", "")


def _records_from_result(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if hasattr(result, "to_dict"):
        try:
            records = result.to_dict(orient="records")
        except TypeError:
            records = result.to_dict("records")
        return [row for row in records if isinstance(row, dict)]
    return []


def summarize_records(interface: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    contract = INTERFACE_FIELD_CONTRACTS[interface]
    response_fields = sorted({str(key) for row in records for key in row})
    expected_fields = list(contract["expected_fields"])
    missing_expected_fields = [field for field in expected_fields if field not in response_fields]
    has_required = any(field in response_fields for field in contract["required_any"])
    capability = "SUPPORTED" if records and has_required else "UNKNOWN"
    if records and missing_expected_fields:
        capability = "PARTIAL_SUPPORTED"
    return {
        "interface": interface,
        "source_name": SOURCE_NAME,
        "source_endpoint": contract["source_endpoint"],
        "source_version": SOURCE_VERSION,
        "role": contract["role"],
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "semantics": SEMANTICS,
        "row_count": len(records),
        "response_fields": response_fields,
        "expected_fields": expected_fields,
        "missing_expected_fields": missing_expected_fields,
        "examples": records[:3],
        "capability": capability,
        "production_write_allowed": PRODUCTION_WRITE_ALLOWED,
    }


def summarize_interface_error(interface: str, error: Exception | str) -> dict[str, Any]:
    contract = INTERFACE_FIELD_CONTRACTS[interface]
    return {
        "interface": interface,
        "source_name": SOURCE_NAME,
        "source_endpoint": contract["source_endpoint"],
        "source_version": SOURCE_VERSION,
        "role": contract["role"],
        "frequency": FREQUENCY,
        "window": WINDOW,
        "market_scope": MARKET_SCOPE,
        "semantics": SEMANTICS,
        "row_count": 0,
        "response_fields": [],
        "expected_fields": list(contract["expected_fields"]),
        "missing_expected_fields": list(contract["expected_fields"]),
        "examples": [],
        "capability": "UNKNOWN",
        "error_type": type(error).__name__ if isinstance(error, Exception) else "ConfigurationError",
        "error": str(error),
        "production_write_allowed": PRODUCTION_WRITE_ALLOWED,
    }


def _call_interface(pro: Any, interface: str, *, trade_date: str, ts_code: str) -> Any:
    method = getattr(pro, interface)
    if interface in ("moneyflow", "moneyflow_ths"):
        return method(ts_code=ts_code, trade_date=trade_date)
    return method(trade_date=trade_date)


def probe_tushare_fund_flow(*, token: str, trade_date: str, ts_code: str) -> dict[str, Any]:
    normalized_date = normalize_trade_date(trade_date)
    if not token:
        results = {
            interface: summarize_interface_error(interface, "missing token: pass --token or export TUSHARE_TOKEN")
            for interface in INTERFACE_FIELD_CONTRACTS
        }
    else:
        try:
            import tushare as ts  # type: ignore[import-not-found]

            pro = ts.pro_api(token)
        except Exception as exc:  # noqa: BLE001 - probe must report setup failures as data.
            results = {interface: summarize_interface_error(interface, exc) for interface in INTERFACE_FIELD_CONTRACTS}
        else:
            results = {}
            for interface in INTERFACE_FIELD_CONTRACTS:
                try:
                    raw = _call_interface(pro, interface, trade_date=normalized_date, ts_code=ts_code)
                    results[interface] = summarize_records(interface, _records_from_result(raw))
                except Exception as exc:  # noqa: BLE001 - probe must continue across interfaces.
                    results[interface] = summarize_interface_error(interface, exc)

    supported = [name for name, result in results.items() if result.get("capability") in ("SUPPORTED", "PARTIAL_SUPPORTED")]
    return {
        "source_name": SOURCE_NAME,
        "source_version": SOURCE_VERSION,
        "trade_date": normalized_date,
        "ts_code": ts_code,
        "capability": "SUPPORTED" if supported else "UNKNOWN",
        "supported_interfaces": supported,
        "interfaces": results,
        "forbidden_interpretations": list(FORBIDDEN_INTERPRETATIONS),
        "decision": (
            "Tushare fund-flow evidence is available for audit; keep it in Evidence Layer only."
            if supported
            else "Tushare fund-flow capability was not verified; do not add collector."
        ),
        "production_write_allowed": PRODUCTION_WRITE_ALLOWED,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Tushare fund-flow capability.")
    parser.add_argument("--date", required=True, help="Trade date, YYYY-MM-DD or YYYYMMDD.")
    parser.add_argument("--ts-code", default="300223.SZ", help="Sample Tushare stock code.")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN", ""), help="Defaults to TUSHARE_TOKEN env var.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = probe_tushare_fund_flow(token=args.token, trade_date=args.date, ts_code=args.ts_code)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
