#!/usr/bin/env python3
"""PR4.2.34c — Direction Coverage Expansion Audit.

For each direction, identifies:
  1. How many stocks are in the subject_stock_map (universe)
  2. How many we have fund flow data for (covered)
  3. Coverage gap — stocks to collect

Outputs: coverage report + Tushare collection command list.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import asyncpg
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "direction_bootstrap.yaml"
)


async def main() -> int:
    trade_date_str = "2026-07-09"
    trade_date = date.fromisoformat(trade_date_str)

    # Load direction bootstrap
    with open(YAML_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    conn = await asyncpg.connect(
        "postgresql://localhost:5432/stock_data_test",
        user="postgres", password="",
    )
    try:
        # Collect all subject_keys used across all directions
        all_keys: set[str] = set()
        dir_themes: dict[str, list[str]] = defaultdict(list)
        for dk, d in config["directions"].items():
            for t in d["themes"]:
                sk = t["subject_key"]
                all_keys.add(sk)
                dir_themes[dk].append(sk)

        # Fetch stock universe for all themes
        db_stocks: dict[str, list[dict]] = defaultdict(list)
        for sk in all_keys:
            rows = await conn.fetch(
                "SELECT DISTINCT stock_id, stock_name FROM subject_stock_daily_snapshot "
                "WHERE subject_key = $1 AND trade_date = $2::date "
                "ORDER BY stock_id",
                sk, trade_date,
            )
            for r in rows:
                db_stocks[sk].append({
                    "stock_id": r["stock_id"],
                    "stock_name": r["stock_name"],
                })

        # Fetch already-collected fund flow stocks for this date
        collected = set()
        try:
            flow_rows = await conn.fetch(
                "SELECT DISTINCT ts_code FROM stock_fund_flow_daily "
                "WHERE trade_date = $1::date",
                trade_date,
            )
            collected = {r["ts_code"] for r in flow_rows}
        except Exception:
            pass  # table may not exist yet

        # Build coverage report
        print("=" * 80)
        print(f"Direction Coverage Audit — {trade_date_str}")
        print("=" * 80)
        print()

        direction_reports = []
        total_stocks = 0
        total_covered = 0

        for dk, themes in sorted(dir_themes.items()):
            d = config["directions"][dk]
            all_stocks_for_dir: list[str] = []
            for sk in themes:
                for s in db_stocks.get(sk, []):
                    sid = s["stock_id"]
                    if sid not in all_stocks_for_dir:
                        all_stocks_for_dir.append(sid)

            n_total = len(all_stocks_for_dir)
            n_covered = len([s for s in all_stocks_for_dir if s in collected])
            coverage = round(n_covered / max(n_total, 1) * 100, 1)

            missing = [s for s in all_stocks_for_dir if s not in collected]

            total_stocks += n_total
            total_covered += n_covered

            status = "✅" if coverage >= 70 else "⚠️" if coverage >= 30 else "❌"
            print(f"  {status} {d['name']:<12s} ({dk})")
            print(f"     themes={len(themes)}  stocks={n_total}  covered={n_covered}  coverage={coverage}%")
            if missing:
                print(f"     missing top-5: {', '.join(missing[:5])}")
            print()

            direction_reports.append({
                "direction_key": dk,
                "direction_name": d["name"],
                "theme_count": len(themes),
                "stock_count": n_total,
                "covered_count": n_covered,
                "coverage_pct": coverage,
                "missing_stocks": missing[:20],
            })

        # Summary
        overall = round(total_covered / max(total_stocks, 1) * 100, 1)
        print(f"  OVERALL: {total_covered}/{total_stocks} stocks covered ({overall}%)")
        print()

        # Generate collection queue — top-50 missing stocks across all directions
        all_missing: dict[str, int] = defaultdict(int)
        for dr in direction_reports:
            for s in dr["missing_stocks"]:
                all_missing[s] += 1

        top_missing = sorted(all_missing.items(), key=lambda x: -x[1])[:50]
        collection_stocks = [s for s, _ in top_missing]

        print("Collection queue (top-50 missing stocks, prioritized by direction count):")
        print(f"  {', '.join(collection_stocks[:30])}")
        print()
        print("Tushare collection command:")
        print(f"  python stock_processing_service/scripts/collect_tushare_moneyflow.py \\")
        print(f"    --date {trade_date_str} \\")
        print(f"    --ts-code {','.join(collection_stocks[:20])} \\")
        print(f"    --token \\$TUSHARE_TOKEN --persist")
        print()

        # JSON output
        print(json.dumps({
            "trade_date": trade_date_str,
            "overall_coverage_pct": overall,
            "total_stocks": total_stocks,
            "total_covered": total_covered,
            "directions": direction_reports,
            "top_missing_stocks": collection_stocks[:50],
        }, ensure_ascii=False, indent=2))

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
