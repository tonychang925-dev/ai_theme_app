from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.services.pre_market_brief_auto_scheduler import (
    PreMarketBriefSpsClient,
    resolve_pre_market_brief_trade_date,
)


CN_TZ = ZoneInfo("Asia/Shanghai")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run minimal realtime pre-market brief draft rebuild loop.")
    parser.add_argument("--sps-base-url", default=None)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--source", default="db_first")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--status-path", default=None)
    parser.add_argument("--once", action="store_true")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = PreMarketBriefSpsClient(base_url=args.sps_base_url)
    interval = max(30, int(args.interval_seconds))
    status_path = Path(args.status_path) if args.status_path else None

    while True:
        now = datetime.now(CN_TZ)
        try:
            trade_date = await resolve_pre_market_brief_trade_date(
                client,
                explicit_trade_date=args.trade_date,
                now=now,
            )
            response = await client.rebuild(
                trade_date=trade_date,
                source=args.source,
                limit=args.limit,
                force=False,
            )
            _write_status(
                status_path,
                {
                    "running": True,
                    "last_rebuild_at": datetime.now(CN_TZ).isoformat(),
                    "trade_date": trade_date.isoformat(),
                    "ok": bool(response.get("ok", True)),
                    "status": response.get("status"),
                    "error": None,
                },
            )
        except Exception as exc:
            logging.exception("pre-market brief realtime rebuild failed")
            _write_status(
                status_path,
                {
                    "running": True,
                    "last_rebuild_at": None,
                    "trade_date": args.trade_date,
                    "ok": False,
                    "status": "error",
                    "error": str(exc),
                },
            )
        if args.once:
            return
        await asyncio.sleep(interval)


def _write_status(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(async_main())
