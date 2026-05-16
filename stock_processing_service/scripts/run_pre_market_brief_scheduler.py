from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_processing_service.application.services.pre_market_brief_auto_scheduler import (
    PreMarketBriefAutoScheduler,
    PreMarketBriefSpsClient,
    resolve_pre_market_brief_trade_date,
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
        target_trade_date = await resolve_pre_market_brief_trade_date(
            client,
            explicit_trade_date=args.trade_date,
            now=datetime.now(CN_TZ),
        )
        result = await scheduler.run_once(trade_date=target_trade_date)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return

    async def trade_date_provider(now: datetime) -> date:
        return await resolve_pre_market_brief_trade_date(
            client,
            explicit_trade_date=args.trade_date,
            now=now,
        )

    await scheduler.run_forever(trade_date_provider=trade_date_provider)


if __name__ == "__main__":
    asyncio.run(_main())
