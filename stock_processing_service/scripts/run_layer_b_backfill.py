#!/usr/bin/env python3
"""为 4/7-4/15 补齐 Layer B 数据。

运行 BuildThemeCycleEvidenceDailyJob 产出 theme_cycle_evidence_daily，
然后 BuildDailySnapshotJob 产出周期判定和快照对象。
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from uuid import uuid4

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.jobs.build_theme_cycle_evidence_daily_job import (
    BuildThemeCycleEvidenceDailyJob,
)
from stock_processing_service.application.jobs.build_daily_snapshot_job import (
    BuildDailySnapshotJob,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_write_gateway_adapter import (
    StockWriteGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
    StockEventGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
    StockIdempotencyGatewayAdapter,
)

TRADE_DATES = [
    date(2026, 4, 7),
    date(2026, 4, 8),
    date(2026, 4, 9),
    date(2026, 4, 10),
    date(2026, 4, 13),
    date(2026, 4, 14),
    date(2026, 4, 15),
]


async def main() -> None:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    read_port = StockReadGatewayAdapter(db_gateway=gw)
    write_port = StockWriteGatewayAdapter(db_gateway=gw)
    event_port = StockEventGatewayAdapter(db_gateway=gw)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gw)

    # ── Step 1: Build theme_cycle_evidence_daily ──
    evidence_job = BuildThemeCycleEvidenceDailyJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    for td in TRADE_DATES:
        ver = f"evidence_backfill_v1"
        bid = uuid4().hex[:12]
        tid = uuid4().hex[:12]

        result = await evidence_job.execute(td, ver, bid, tid)
        print(f"Evidence {td}: status={result.status} rows={result.affected_rows}")

    # ── Step 2: Build daily snapshot (含周期判定) ──
    snapshot_job = BuildDailySnapshotJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    for td in TRADE_DATES:
        ver = f"snapshot_backfill_v1"
        bid = uuid4().hex[:12]
        tid = uuid4().hex[:12]

        result = await snapshot_job.execute(td, ver, bid, tid)
        print(f"Snapshot {td}: status={result.status} rows={result.affected_rows}")

    # ── 检查 cycle_v2 数据 ──
    async with gw._client.pool.acquire() as conn:
        for td in TRADE_DATES:
            cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date",
                td,
            )
            print(f"  cycle_v2 rows on {td}: {cnt}")

    await gw.close()
    print("\n✅ Layer B backfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
