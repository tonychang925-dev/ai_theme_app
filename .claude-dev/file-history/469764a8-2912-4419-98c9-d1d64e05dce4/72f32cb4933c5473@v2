"""Quick test: verify BuildIdentityJob write path (identity_registry + review_queue) end-to-end.

Matches production adapter chain:
  BuildIdentityJob(read_port=DBThemeDataGateway, write_port=DBStockObjectGateway)
  → DBStockObjectGateway(getattr) → DatabaseGateway → PostgresDatabaseManager

Usage:
  RUN_REPLAY_DB=1 SPS_OUTPUT_MODE=db \
  python -m stock_processing_service.tests.replay._test_identity_write_path \
    --trade-date 2026-04-25
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime

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


async def main() -> None:
    output_mode = os.getenv("SPS_OUTPUT_MODE", "").strip().lower()
    if output_mode != "db":
        print("WARNING: SPS_OUTPUT_MODE is not set to 'db'. Writes will go to JSON files, not the database.")
        print("Set SPS_OUTPUT_MODE=db to persist writes to the database.")
        if os.getenv("REPLAY_DB_WRITE_OK", "0") != "1":
            print("Set REPLAY_DB_WRITE_OK=1 to bypass this check.")
            sys.exit(1)

    trade_date_str = "2026-04-25"
    for arg in sys.argv[1:]:
        if arg.startswith("--trade-date="):
            trade_date_str = arg.split("=", 1)[1]

    trade_date = date.fromisoformat(trade_date_str)

    print(f"Connecting to database (stock_data_test)...")
    gateway = await _get_test_gateway()
    print(f"Connected. Testing write path for trade_date={trade_date_str}")

    # Match production adapter chain from bootstrap.py:
    #   build_identity=BuildIdentityJob(
    #       read_port=theme_data_gateway,   # DBThemeDataGateway
    #       write_port=stock_object_gateway, # DBStockObjectGateway
    #       ...
    #   )
    read_port = DBThemeDataGateway(db_gateway=gateway)
    write_port = DBStockObjectGateway(db_gateway=gateway)
    event_port = StockEventGatewayAdapter(db_gateway=gateway)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gateway)

    # Check pool data exists
    raw_pool = await read_port.get_subject_stock_pool_by_trade_date(trade_date)
    print(f"Pool rows (raw): {len(raw_pool)}, type={type(raw_pool[0]).__name__ if raw_pool else 'N/A'}")

    if not raw_pool:
        print("No pool data — try a different trade date.")
        return

    # Show sample row
    if raw_pool:
        r0 = raw_pool[0]
        if isinstance(r0, dict):
            print(f"Sample [0] keys: {list(r0.keys())[:8]}")
            subject_keys = sorted({r["subject_key"] for r in raw_pool})
        else:
            print(f"Sample [0]: {r0}")
            subject_keys = sorted({r.subject_key for r in raw_pool})
    print(f"Unique subject_keys: {len(subject_keys)}")

    job = BuildIdentityJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    snapshot_version = f"p1-phase0-test-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    batch_id = f"test-{trade_date_str}"
    trace_id = f"trace-{trade_date_str}"

    print(f"\nRunning BuildIdentityJob.execute()...")
    print(f"  snapshot_version={snapshot_version}")
    print(f"  batch_id={batch_id}")

    result = await job.execute(
        trade_date=trade_date,
        snapshot_version=snapshot_version,
        batch_id=batch_id,
        trace_id=trace_id,
    )

    print(f"\nResult:")
    print(f"  name: {result.name}")
    print(f"  status: {result.status}")
    print(f"  trade_date: {result.trade_date}")
    print(f"  affected_rows: {result.affected_rows}")
    print(f"  warnings: {result.warnings}")
    print(f"  metrics: {result.metrics}")

    # Verify data was written by reading it back
    print(f"\nVerifying writes by reading back from DB...")
    async with gateway._client.pool.acquire() as conn:
        identity_count = await conn.fetchval(
            "SELECT COUNT(*) FROM theme_mainline_identity_registry"
        )
        review_count = await conn.fetchval(
            "SELECT COUNT(*) FROM mainline_identity_review_queue WHERE trade_date = $1::date",
            trade_date,
        )
        print(f"  theme_mainline_identity_registry total rows: {identity_count}")
        print(f"  mainline_identity_review_queue for {trade_date_str}: {review_count}")

        # Sample check
        if identity_count > 0:
            sample = await conn.fetchrow(
                "SELECT subject_key, theme_name, identity_status, is_main_theme, source_trade_date "
                "FROM theme_mainline_identity_registry ORDER BY updated_at DESC LIMIT 5"
            )
            print(f"  Recent identity rows: {dict(sample) if sample else 'N/A'}")

        if review_count > 0:
            sample = await conn.fetchrow(
                "SELECT subject_key, theme_name, review_status, trade_date "
                "FROM mainline_identity_review_queue ORDER BY trade_date DESC LIMIT 5"
            )
            print(f"  Recent review rows: {dict(sample) if sample else 'N/A'}")

    await gateway.close()


if __name__ == "__main__":
    if os.getenv("RUN_REPLAY_DB", "0") != "1":
        print("Set RUN_REPLAY_DB=1 to enable real DB access.")
        sys.exit(1)
    asyncio.run(main())
