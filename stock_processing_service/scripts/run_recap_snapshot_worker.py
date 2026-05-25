#!/usr/bin/env python3
"""P2: recap.snapshot worker — 独立子进程执行，不阻塞 SPS 主进程。"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date as date_type
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_processing_service.application.orchestrators.bootstrap import build_container
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trade-date", required=True)
    p.add_argument("--skip-prereqs", action="store_true", default=True)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("recap_worker")

    td = date_type.fromisoformat(args.trade_date)

    db_cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL)
    from database_service.gateway import DatabaseGateway
    gw = await DatabaseGateway.initialize(config=db_cfg, auto_warm_cache=False)

    container = build_container(db_gateway=gw)

    job = container.build_post_market_recap
    result = await job.execute(
        trade_date=td,
        snapshot_version="collection.post_market_recap.v1",
        batch_id=f"worker_{td.isoformat()}",
        trace_id=f"worker_{td.isoformat()}",
        lookback_days=7,
        skip_prereqs=args.skip_prereqs,
    )

    output = {
        "status": result.status,
        "affected_rows": result.affected_rows,
        "trade_date": result.trade_date,
    }
    print(json.dumps(output, ensure_ascii=False))

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
