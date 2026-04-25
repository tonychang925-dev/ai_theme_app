#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from datetime import date

from stock_processing_service.tests.replay._post_market_replay_runner import run_post_market_replay


async def _run_one(d: date, sample: str) -> dict:
    result = await run_post_market_replay(d, sample)
    recap = result.recap_doc or {}
    return {
        "trade_date": d.isoformat(),
        "snapshot_version": result.snapshot_version,
        "daily_status": result.daily_status,
        "recap_status": result.recap_status,
        "strong_watch_input_count": recap.get("strong_watch_input_count"),
        "strong_watch_input_7d_count": recap.get("strong_watch_input_7d_count"),
        "candidate_count": recap.get("candidate_count"),
    }


async def main() -> None:
    out = {
        "ok": True,
        "results": [
            await _run_one(date(2026, 4, 7), "compare_7d_pool_v3"),
            await _run_one(date(2026, 4, 15), "compare_7d_pool_v3"),
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
