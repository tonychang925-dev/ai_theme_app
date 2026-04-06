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
from stock_service.services.dragon_tiger_object_service import DragonTigerObjectService
from stock_service.services.tushare_dragon_tiger_snapshot_service import (
    TushareDragonTigerSnapshotService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P3.phase2 smoke test: Tushare 龙虎榜 -> raw snapshot/cache -> dragon_tiger_object",
    )
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD format")
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

    snapshot_service = TushareDragonTigerSnapshotService(config)
    top_list_result = snapshot_service.fetch_or_cache_top_list(
        args.trade_date,
        force_refresh=args.force_refresh,
    )
    top_inst_result = snapshot_service.fetch_or_cache_top_inst(
        args.trade_date,
        force_refresh=args.force_refresh,
    )

    object_service = DragonTigerObjectService()
    objects = object_service.build_objects(
        object_service.normalize_top_list(top_list_result.records),
        object_service.normalize_top_inst(top_inst_result.records),
    )

    summary = {
        "trade_date": args.trade_date,
        "top_list_cache_hit": top_list_result.cache_hit,
        "top_list_snapshot_path": top_list_result.snapshot_path,
        "top_list_row_count": top_list_result.row_count,
        "top_inst_cache_hit": top_inst_result.cache_hit,
        "top_inst_snapshot_path": top_inst_result.snapshot_path,
        "top_inst_row_count": top_inst_result.row_count,
        "dragon_tiger_object_count": len(objects),
        "dragon_tiger_object_sample": [asdict(row) for row in objects[:10]],
    }

    output_path = Path(args.output) if args.output else project_root / "tmp" / f"stock_service_smoke_dragon_tiger_{args.trade_date}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] trade_date={args.trade_date}")
    print(f"[OK] top_list_cache_hit={top_list_result.cache_hit}")
    print(f"[OK] top_list_snapshot_path={top_list_result.snapshot_path}")
    print(f"[OK] top_list_row_count={top_list_result.row_count}")
    print(f"[OK] top_inst_cache_hit={top_inst_result.cache_hit}")
    print(f"[OK] top_inst_snapshot_path={top_inst_result.snapshot_path}")
    print(f"[OK] top_inst_row_count={top_inst_result.row_count}")
    print(f"[OK] dragon_tiger_object_count={len(objects)}")
    print(f"[OK] output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
