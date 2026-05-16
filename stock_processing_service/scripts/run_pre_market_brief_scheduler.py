from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_processing_service.application.services.pre_market_brief_auto_scheduler import (
    PreMarketBriefAutoScheduler,
    PreMarketBriefSpsClient,
)


CN_TZ = ZoneInfo("Asia/Shanghai")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pre-market brief rebuild/finalize scheduler via SPS API.")
    parser.add_argument("--sps-base-url", default=None)
    parser.add_argument("--trade-date", default=None, help="YYYY-MM-DD. Defaults to current Asia/Shanghai date.")
    parser.add_argument("--source", default="db_first")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--force-finalize", action="store_true")
    return parser.parse_args()


def _trade_date_from_arg(value: str | None, now: datetime | None = None) -> date:
    if value:
        return date.fromisoformat(value)
    return (now or datetime.now(CN_TZ)).date()


async def _main() -> None:
    args = _parse_args()
    client = PreMarketBriefSpsClient(base_url=args.sps_base_url)
    scheduler = PreMarketBriefAutoScheduler(
        client,
        source=args.source,
        limit=args.limit,
        force_rebuild=args.force_rebuild,
        force_finalize=args.force_finalize,
    )

    if args.once:
        result = await scheduler.run_once(trade_date=_trade_date_from_arg(args.trade_date))
        print(json.dumps(result, ensure_ascii=False, default=str))
        return

    def trade_date_provider(now: datetime) -> date:
        return _trade_date_from_arg(args.trade_date, now)

    await scheduler.run_forever(trade_date_provider=trade_date_provider)


if __name__ == "__main__":
    asyncio.run(_main())
