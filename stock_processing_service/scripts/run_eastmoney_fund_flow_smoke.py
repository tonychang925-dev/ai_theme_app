#!/usr/bin/env python3
"""Run a small Eastmoney fund-flow collector smoke/replay.

PR4.2.31c-4 validation tool. It writes only stock_fund_flow_snapshot evidence
rows through the collector and reads them back for diagnostics. It does not
write ReviewDocument, UI artifacts, or Capital Intelligence outputs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.gateway import get_gateway
from stock_processing_service.integrations.a_stock_data.jobs.collect_eastmoney_fund_flow_job import (
    CollectEastmoneyFundFlowJob,
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    duplicates: set[tuple[Any, ...]] = set()
    seen: set[tuple[Any, ...]] = set()
    missing_required: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row.get("trade_date"),
            row.get("stock_code"),
            row.get("source_name"),
            row.get("source_endpoint"),
            row.get("source_version"),
            row.get("frequency"),
            row.get("window"),
            row.get("market_scope"),
        )
        if key in seen:
            duplicates.add(key)
        seen.add(key)
        missing = [
            field
            for field in (
                "net_inflow_yuan",
                "super_large_net_inflow_yuan",
                "large_net_inflow_yuan",
                "medium_net_inflow_yuan",
                "small_net_inflow_yuan",
                "source_version",
                "frequency",
                "window",
                "market_scope",
                "quality",
            )
            if row.get(field) in (None, "")
        ]
        if missing:
            missing_required.append({"key": key, "missing": missing})
    return {
        "row_count": len(rows),
        "duplicate_identity_count": len(duplicates),
        "missing_required": missing_required[:10],
        "quality_counts": {
            quality: sum(1 for row in rows if row.get("quality") == quality)
            for quality in sorted({str(row.get("quality")) for row in rows})
        },
    }


async def run_smoke(stock_codes: list[str], trade_date: date, limit: int, repeat: int) -> dict[str, Any]:
    gateway = await get_gateway()
    try:
        run_results = []
        for _ in range(max(repeat, 1)):
            job = CollectEastmoneyFundFlowJob(
                write_port=gateway,
                stock_codes=stock_codes,
                limit=limit,
            )
            run_results.append(await job.execute(trade_date))
        rows = await gateway.get_stock_fund_flow_snapshots(
            stock_codes=stock_codes,
            trade_date=trade_date.isoformat(),
        )
        return {
            "trade_date": trade_date.isoformat(),
            "stock_codes": stock_codes,
            "limit": limit,
            "repeat": repeat,
            "run_results": [
                {
                    "name": result.name,
                    "status": result.status,
                    "affected_rows": result.affected_rows,
                    "warnings": result.warnings,
                    "metrics": result.metrics,
                }
                for result in run_results
            ],
            "readback": rows,
            "summary": _summarize_rows(rows),
            "production_write_allowed": False,
        }
    finally:
        await gateway.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Eastmoney fund-flow smoke/replay.")
    parser.add_argument("--date", default="2026-07-09", help="Trade date YYYY-MM-DD.")
    parser.add_argument("--stock-code", action="append", default=[], help="Stock code; repeatable.")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--repeat", type=int, default=2, help="Run collector N times to validate idempotent upsert.")
    args = parser.parse_args()

    stock_codes = args.stock_code or ["300223", "002747"]
    result = await run_smoke(stock_codes, date.fromisoformat(args.date), args.limit, args.repeat)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default))


if __name__ == "__main__":
    asyncio.run(main())
