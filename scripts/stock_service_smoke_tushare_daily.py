from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig
from stock_service.adapters.jyhf_adapter import JyhfAdapter
from stock_service.services.daily_snapshot_service import DailySnapshotService
from stock_service.services.tushare_snapshot_service import TushareSnapshotService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P3.phase1 smoke test: Tushare -> raw snapshot cache -> T02 object layer",
    )
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD format")
    parser.add_argument(
        "--ts-codes",
        required=True,
        nargs="+",
        help="One or more Tushare stock codes, e.g. 601872.SH",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("TUSHARE_TOKEN", ""),
        help="Tushare token. Defaults to TUSHARE_TOKEN env var.",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root path",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore cached raw snapshot and call Tushare directly",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path for smoke summary",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("missing token: pass --token or export TUSHARE_TOKEN")

    project_root = Path(args.project_root).resolve()
    config = StockServiceConfig(
        project_root=project_root,
        raw_snapshot_root=project_root / "theme_data_complete" / "_raw_stock_sources",
        tushare_token=args.token,
    )

    snapshot_service = TushareSnapshotService(config)
    snapshot_result = snapshot_service.fetch_or_cache_daily_quotes(
        args.trade_date,
        args.ts_codes,
        force_refresh=args.force_refresh,
    )

    daily_service = DailySnapshotService()
    stock_snapshots = daily_service.normalize_tushare_daily_rows(snapshot_result.records, args.trade_date)

    jyhf_adapter = JyhfAdapter(project_root)
    wanted_codes = {row.stock_id for row in stock_snapshots}
    jyhf_rows = [
        row
        for row in jyhf_adapter.iter_stock_daily_rows(args.trade_date)
        if str(row.get("stock_id") or "").upper() in wanted_codes
    ]
    subject_rows = daily_service.build_subject_stock_daily_snapshots(
        args.trade_date,
        stock_snapshots,
        jyhf_rows,
    )

    summary = {
        "trade_date": args.trade_date,
        "requested_codes": list(args.ts_codes),
        "cache_hit": snapshot_result.cache_hit,
        "raw_snapshot_path": snapshot_result.snapshot_path,
        "tushare_row_count": snapshot_result.row_count,
        "stock_daily_snapshot_count": len(stock_snapshots),
        "subject_stock_daily_snapshot_count": len(subject_rows),
        "stock_daily_snapshot_sample": [asdict(row) for row in stock_snapshots[:10]],
        "subject_stock_daily_snapshot_sample": [asdict(row) for row in subject_rows[:10]],
    }

    output_path = Path(args.output) if args.output else project_root / "tmp" / f"stock_service_smoke_{args.trade_date}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] trade_date={args.trade_date}")
    print(f"[OK] cache_hit={snapshot_result.cache_hit}")
    print(f"[OK] raw_snapshot_path={snapshot_result.snapshot_path}")
    print(f"[OK] tushare_row_count={snapshot_result.row_count}")
    print(f"[OK] stock_daily_snapshot_count={len(stock_snapshots)}")
    print(f"[OK] subject_stock_daily_snapshot_count={len(subject_rows)}")
    print(f"[OK] output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
