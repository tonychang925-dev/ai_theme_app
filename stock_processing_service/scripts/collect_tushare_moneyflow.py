#!/usr/bin/env python3
"""PR4.2.31f — Tushare Moneyflow Evidence Collector.

Collects vendor-defined order-size fund-flow facts from Tushare moneyflow API
and persists them to stock_fund_flow_daily. This is an Evidence Layer tool —
no institution/hot-money inference, no theme aggregation, no UI connection.

Usage:
    python stock_processing_service/scripts/collect_tushare_moneyflow.py \
        --date 2026-07-09 \
        --ts-code 300223.SZ \
        --token YOUR_TUSHARE_TOKEN

    python stock_processing_service/scripts/collect_tushare_moneyflow.py \
        --date 2026-07-09 \
        --ts-code 300223.SZ,002747.SZ,605178.SH \
        --token YOUR_TUSHARE_TOKEN \
        --persist
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call_moneyflow(pro: Any, ts_code: str, trade_date_str: str) -> list[dict[str, Any]]:
    """Call Tushare moneyflow API and return raw rows."""
    raw = pro.moneyflow(ts_code=ts_code, trade_date=trade_date_str)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if hasattr(raw, "to_dict"):
        try:
            records = raw.to_dict(orient="records")
        except TypeError:
            records = raw.to_dict("records")
        return [row for row in records if isinstance(row, dict)]
    return []


async def _persist_rows(
    rows: list[dict[str, Any]],
    *,
    trade_date: str,
    db_name: str = "stock_data_test",
) -> int:
    """Persist normalized rows to stock_fund_flow_daily. Returns affected row count."""
    import asyncpg

    conn = await asyncpg.connect(
        f"postgresql://localhost:5432/{db_name}",
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )
    try:
        count = 0
        for row in rows:
            trade_date_val = row.get("trade_date")
            if isinstance(trade_date_val, date):
                trade_date_val = trade_date_val.isoformat()

            await conn.execute(
                """
                INSERT INTO stock_fund_flow_daily (
                    trade_date, ts_code,
                    buy_elg_amount_yuan, sell_elg_amount_yuan,
                    buy_elg_vol_shou, sell_elg_vol_shou,
                    buy_lg_amount_yuan, sell_lg_amount_yuan,
                    buy_lg_vol_shou, sell_lg_vol_shou,
                    buy_md_amount_yuan, sell_md_amount_yuan,
                    buy_md_vol_shou, sell_md_vol_shou,
                    buy_sm_amount_yuan, sell_sm_amount_yuan,
                    buy_sm_vol_shou, sell_sm_vol_shou,
                    order_size_flow_amount_yuan, net_mf_vol_shou,
                    source_name, source_endpoint, source_version, collected_at,
                    semantic_type, not_owner_identity,
                    quality, diagnostics, raw_json
                ) VALUES (
                    $1::date, $2,
                    $3, $4, $5, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13, $14,
                    $15, $16, $17, $18,
                    $19, $20,
                    $21, $22, $23, $24,
                    $25, $26,
                    $27, $28::jsonb, $29::jsonb
                )
                ON CONFLICT (trade_date, ts_code, source_name, source_endpoint, source_version)
                DO UPDATE SET
                    buy_elg_amount_yuan = EXCLUDED.buy_elg_amount_yuan,
                    sell_elg_amount_yuan = EXCLUDED.sell_elg_amount_yuan,
                    buy_elg_vol_shou = EXCLUDED.buy_elg_vol_shou,
                    sell_elg_vol_shou = EXCLUDED.sell_elg_vol_shou,
                    buy_lg_amount_yuan = EXCLUDED.buy_lg_amount_yuan,
                    sell_lg_amount_yuan = EXCLUDED.sell_lg_amount_yuan,
                    buy_lg_vol_shou = EXCLUDED.buy_lg_vol_shou,
                    sell_lg_vol_shou = EXCLUDED.sell_lg_vol_shou,
                    buy_md_amount_yuan = EXCLUDED.buy_md_amount_yuan,
                    sell_md_amount_yuan = EXCLUDED.sell_md_amount_yuan,
                    buy_md_vol_shou = EXCLUDED.buy_md_vol_shou,
                    sell_md_vol_shou = EXCLUDED.sell_md_vol_shou,
                    buy_sm_amount_yuan = EXCLUDED.buy_sm_amount_yuan,
                    sell_sm_amount_yuan = EXCLUDED.sell_sm_amount_yuan,
                    buy_sm_vol_shou = EXCLUDED.buy_sm_vol_shou,
                    sell_sm_vol_shou = EXCLUDED.sell_sm_vol_shou,
                    order_size_flow_amount_yuan = EXCLUDED.order_size_flow_amount_yuan,
                    net_mf_vol_shou = EXCLUDED.net_mf_vol_shou,
                    collected_at = EXCLUDED.collected_at,
                    quality = EXCLUDED.quality,
                    diagnostics = EXCLUDED.diagnostics,
                    raw_json = EXCLUDED.raw_json
                """,
                trade_date_val,
                row["ts_code"],
                row.get("buy_elg_amount_yuan"), row.get("sell_elg_amount_yuan"),
                row.get("buy_elg_vol_shou"), row.get("sell_elg_vol_shou"),
                row.get("buy_lg_amount_yuan"), row.get("sell_lg_amount_yuan"),
                row.get("buy_lg_vol_shou"), row.get("sell_lg_vol_shou"),
                row.get("buy_md_amount_yuan"), row.get("sell_md_amount_yuan"),
                row.get("buy_md_vol_shou"), row.get("sell_md_vol_shou"),
                row.get("buy_sm_amount_yuan"), row.get("sell_sm_amount_yuan"),
                row.get("buy_sm_vol_shou"), row.get("sell_sm_vol_shou"),
                row.get("order_size_flow_amount_yuan"), row.get("net_mf_vol_shou"),
                row["source_name"], row["source_endpoint"], row["source_version"],
                row["collected_at"],
                row["semantic_type"], row["not_owner_identity"],
                row["quality"],
                json.dumps(row["diagnostics"], ensure_ascii=False),
                json.dumps(row["raw_json"], ensure_ascii=False),
            )
            count += 1
        return count
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PR4.2.31f Tushare Moneyflow Evidence Collector"
    )
    parser.add_argument("--date", required=True, help="Trade date YYYY-MM-DD")
    parser.add_argument("--ts-code", required=True, help="Stock code(s), comma-separated, e.g. 300223.SZ")
    parser.add_argument("--token", default="", help="Tushare Pro token (or env TUSHARE_TOKEN)")
    parser.add_argument("--persist", action="store_true", help="Write to DB (default: dry-run)")
    parser.add_argument("--db-name", default="stock_data_test", help="Target database")
    args = parser.parse_args()

    token = args.token or os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("ERROR: Tushare token required. Pass --token or set TUSHARE_TOKEN env.")
        return 1

    td = date.fromisoformat(args.date)
    trade_date_str = td.strftime("%Y%m%d")
    ts_codes = [s.strip() for s in args.ts_code.split(",") if s.strip()]

    # Import normalizer
    from stock_processing_service.application.services.capital_evidence.tushare_moneyflow import (
        TushareMoneyflowNormalizer,
    )

    normalizer = TushareMoneyflowNormalizer()
    collected_at = _now()

    # Connect to Tushare
    try:
        import tushare as ts
        pro = ts.pro_api(token)
    except Exception as exc:
        print(f"ERROR: Failed to connect to Tushare: {exc}")
        return 1

    all_rows: list[dict[str, Any]] = []
    results: dict[str, Any] = {
        "source_name": "tushare",
        "source_version": "tushare_moneyflow_v1",
        "collected_at": collected_at,
        "trade_date": args.date,
        "stocks": {},
    }

    for ts_code in ts_codes:
        print(f"[collect] {ts_code} ... ", end="", flush=True)
        try:
            raw_rows = _call_moneyflow(pro, ts_code, trade_date_str)
            if not raw_rows:
                print(f"no data")
                results["stocks"][ts_code] = {"status": "no_data", "rows": 0}
                continue
            evidence_rows = normalizer.normalize_rows(raw_rows, collected_at)
            rows = [e.to_row() for e in evidence_rows]
            all_rows.extend(rows)
            status = "dry_run" if not args.persist else "persisted"
            print(f"{len(rows)} row(s) [{status}]")
            results["stocks"][ts_code] = {"status": "ok", "rows": len(rows)}
        except Exception as exc:
            print(f"ERROR: {exc}")
            results["stocks"][ts_code] = {"status": "error", "error": str(exc)}

    results["total_rows"] = len(all_rows)

    if args.persist and all_rows:
        affected = asyncio.run(_persist_rows(all_rows, trade_date=args.date, db_name=args.db_name))
        results["persisted_rows"] = affected
        print(f"[persist] {affected} row(s) written to stock_fund_flow_daily")

    # Always output summary JSON
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0 if all(s["status"] == "ok" for s in results["stocks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
