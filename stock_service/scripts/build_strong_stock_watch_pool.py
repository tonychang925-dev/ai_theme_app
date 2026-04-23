#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.strong_stock_tracking_service import StrongStockTrackingService


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"invalid --trade-date: {value}") from exc


async def _run(
    trade_date: date,
    skip_seed: bool,
    skip_refresh: bool,
    skip_promote: bool,
    skip_prune: bool,
    skip_snapshot: bool,
) -> int:
    service = StrongStockTrackingService()
    try:
        seed_count = 0
        refresh_count = 0
        promote_count = 0
        prune_count = 0
        snapshot_count = 0

        if not skip_seed:
            seed_count = await service.seed_watch_pool(trade_date)
            print(f"[OK] strong_watch.seed count={seed_count}")
        else:
            print("[SKIP] strong_watch.seed")

        if not skip_refresh:
            refresh_count = await service.refresh_watch_pool(trade_date)
            print(f"[OK] strong_watch.refresh count={refresh_count}")
        else:
            print("[SKIP] strong_watch.refresh")

        if not skip_prune:
            prune_count = await service.prune_watch_pool(trade_date)
            print(f"[OK] strong_watch.prune count={prune_count}")
        else:
            print("[SKIP] strong_watch.prune")

        if not skip_promote:
            promote_count = await service.promote_watch_candidates(trade_date)
            print(f"[OK] strong_watch.promote count={promote_count}")
        else:
            print("[SKIP] strong_watch.promote")

        if not skip_snapshot:
            snapshot_count = await service.snapshot_watch_pool(trade_date)
            print(f"[OK] strong_watch.snapshot count={snapshot_count}")
        else:
            print("[SKIP] strong_watch.snapshot")

        print(
            "[SUMMARY] strong_watch "
            "trade_date={trade_date} "
            "seed={seed_count} refresh={refresh_count} promote={promote_count} "
            "prune={prune_count} snapshot={snapshot_count}".format(
                trade_date=trade_date.isoformat(),
                seed_count=seed_count,
                refresh_count=refresh_count,
                promote_count=promote_count,
                prune_count=prune_count,
                snapshot_count=snapshot_count,
            )
        )
        return 0
    finally:
        await service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build strong stock watch pool and history snapshot.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--skip-seed", action="store_true", help="Skip seed stage")
    parser.add_argument("--skip-refresh", action="store_true", help="Skip refresh stage")
    parser.add_argument("--skip-promote", action="store_true", help="Skip promote stage")
    parser.add_argument("--skip-prune", action="store_true", help="Skip prune stage")
    parser.add_argument("--skip-snapshot", action="store_true", help="Skip snapshot stage")
    args = parser.parse_args()

    trade_date = _parse_date(args.trade_date)
    return asyncio.run(
        _run(
            trade_date=trade_date,
            skip_seed=args.skip_seed,
            skip_refresh=args.skip_refresh,
            skip_promote=args.skip_promote,
            skip_prune=args.skip_prune,
            skip_snapshot=args.skip_snapshot,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
