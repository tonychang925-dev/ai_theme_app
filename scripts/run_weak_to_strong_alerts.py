#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

from stock_service.services.weak_to_strong_alert_service import WeakToStrongAlertService
from stock_service.services.weak_to_strong_auction_service import WeakToStrongAuctionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render weak-to-strong alert messages.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--signal-level", default="", help="Optional filter: A/B/C/X")
    parser.add_argument("--limit", type=int, default=100, help="Max rows")
    parser.add_argument("--output", default="", help="Optional output file path")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict:
    trade_date = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
    auction_service = WeakToStrongAuctionService()
    alert_service = WeakToStrongAlertService()
    try:
        rows = await auction_service.list_replay_by_trade_date(
            trade_date, signal_level=str(args.signal_level or ""), limit=max(int(args.limit), 1)
        )
        payload = alert_service.render_batch(trade_date, rows)
        return payload
    finally:
        await auction_service.close()


def main() -> int:
    args = parse_args()
    payload = asyncio.run(_run(args))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

