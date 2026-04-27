"""Backfill identity data for recent trade dates.

Usage:
  RUN_REPLAY_DB=1 SPS_OUTPUT_MODE=db REPLAY_DB_WRITE_OK=1 \
  python -m stock_processing_service.tests.replay._backfill_identity \
    --start-date 2026-04-20 --end-date 2026-04-25
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.jobs import BuildIdentityJob
from stock_processing_service.infrastructure.gateway_adapters.db_stock_object_gateway import (
    DBStockObjectGateway,
)
from stock_processing_service.infrastructure.gateway_adapters.db_theme_data_gateway import (
    DBThemeDataGateway,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
    StockEventGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
    StockIdempotencyGatewayAdapter,
)


async def _get_test_gateway() -> DatabaseGateway:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")

    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.postgres_ssl_mode = os.getenv("PG_SSL_MODE", "prefer")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    old = DatabaseGateway._instance
    if old is not None and getattr(old, "_client", None) is not None:
        try:
            await old._client.close()
        except Exception:
            pass
    DatabaseGateway._instance = None
    DatabaseGateway._client = None
    DatabaseGateway._initialized = False
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


async def backfill_date(
    gateway: DatabaseGateway,
    read_port: DBThemeDataGateway,
    write_port: DBStockObjectGateway,
    event_port: StockEventGatewayAdapter,
    idempotency_port: StockIdempotencyGatewayAdapter,
    trade_date: date,
    batch_version: str,
) -> dict:
    job = BuildIdentityJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    batch_id = f"backfill-{trade_date.isoformat()}"
    trace_id = f"backfill-{trade_date.isoformat()}"

    pool_rows = await read_port.get_subject_stock_pool_by_trade_date(trade_date)
    if not pool_rows:
        return {"date": trade_date.isoformat(), "status": "no_pool_data", "affected_rows": 0}

    result = await job.execute(
        trade_date=trade_date,
        snapshot_version=batch_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )

    return {
        "date": trade_date.isoformat(),
        "status": result.status,
        "affected_rows": result.affected_rows,
        "metrics": result.metrics,
        "warnings": result.warnings,
    }


async def main() -> None:
    output_mode = os.getenv("SPS_OUTPUT_MODE", "").strip().lower()
    if output_mode != "db":
        print("ERROR: SPS_OUTPUT_MODE must be set to 'db' for backfill.")
        print("Set: SPS_OUTPUT_MODE=db")
        sys.exit(1)

    start_date_str = "2026-04-20"
    end_date_str = "2026-04-25"
    for arg in sys.argv[1:]:
        if arg.startswith("--start-date="):
            start_date_str = arg.split("=", 1)[1]
        elif arg.startswith("--end-date="):
            end_date_str = arg.split("=", 1)[1]

    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    batch_version = f"p1-phase0-backfill-{datetime.now().strftime('%Y%m%dT%H%M%S')}"

    print(f"Backfill identity data: {start_date_str} → {end_date_str}")
    print(f"Batch version: {batch_version}")
    print()

    print("Connecting to database...")
    gateway = await _get_test_gateway()
    print("Connected.")

    read_port = DBThemeDataGateway(db_gateway=gateway)
    write_port = DBStockObjectGateway(db_gateway=gateway)
    event_port = StockEventGatewayAdapter(db_gateway=gateway)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gateway)

    current = start_date
    total_affected = 0
    results = []

    while current <= end_date:
        print(f"Processing {current.isoformat()}...", end=" ", flush=True)
        r = await backfill_date(
            gateway=gateway,
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
            trade_date=current,
            batch_version=batch_version,
        )
        print(f"status={r['status']}, affected_rows={r['affected_rows']}")
        if r.get("metrics"):
            print(f"  metrics: {r['metrics']}")
        if r.get("warnings"):
            print(f"  warnings: {r['warnings']}")
        total_affected += r["affected_rows"]
        results.append(r)
        current += timedelta(days=1)

    print("\n--- Backfill Summary ---")
    for r in results:
        print(f"  {r['date']}: {r['status']}, rows={r['affected_rows']}")
    print(f"Total affected rows: {total_affected}")

    # Final verification
    print("\nFinal DB counts:")
    async with gateway._client.pool.acquire() as conn:
        identity_count = await conn.fetchval(
            "SELECT COUNT(*) FROM theme_mainline_identity_registry"
        )
        review_count = await conn.fetchval(
            "SELECT COUNT(*) FROM mainline_identity_review_queue"
        )
        print(f"  theme_mainline_identity_registry: {identity_count} rows")
        print(f"  mainline_identity_review_queue: {review_count} rows")

        # Status breakdown
        statuses = await conn.fetch(
            "SELECT identity_status, COUNT(*) as cnt FROM theme_mainline_identity_registry GROUP BY identity_status ORDER BY cnt DESC"
        )
        print(f"  Status breakdown:")
        for s in statuses:
            print(f"    {s['identity_status']}: {s['cnt']}")

    await gateway.close()
    print("Done.")


if __name__ == "__main__":
    if os.getenv("RUN_REPLAY_DB", "0") != "1":
        print("Set RUN_REPLAY_DB=1 to enable real DB access.")
        sys.exit(1)
    asyncio.run(main())
