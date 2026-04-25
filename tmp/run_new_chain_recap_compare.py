#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from database_service.gateway import DatabaseGateway
from stock_processing_service.application.orchestrators.bootstrap import build_container


async def _run_one(d: date) -> None:
    gw = await DatabaseGateway.initialize(auto_warm_cache=False)
    try:
        container = build_container(gw, None)
        result = await container.build_post_market_recap.execute(
            trade_date=d,
            snapshot_version="replay_after_pool_gate_v2",
            batch_id=f"batch_{d.isoformat()}",
            trace_id=f"trace_{uuid.uuid4().hex[:8]}",
            lookback_days=7,
        )
        print(
            {
                "trade_date": d.isoformat(),
                "status": result.status,
                "metrics": result.metrics,
            }
        )
    finally:
        await gw.close()


async def main() -> None:
    await _run_one(date(2026, 4, 7))
    await _run_one(date(2026, 4, 15))


if __name__ == "__main__":
    asyncio.run(main())

