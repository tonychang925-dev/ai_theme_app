"""Dual-run comparison: old IdentityRuleEngine vs new EnhancedMainlineJudgementService.

Runs BuildIdentityJob with DUAL_RUN_TRACE=1 for specified dates, then prints comparison.

Usage:
  RUN_REPLAY_DB=1 SPS_OUTPUT_MODE=db REPLAY_DB_WRITE_OK=1 \
  USE_ENHANCED_MAINLINE=0 DUAL_RUN_TRACE=1 \
  python -m stock_processing_service.tests.replay._dual_run_compare \
    --trade-dates 2026-04-07,2026-04-15
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

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
    trade_dates_str = "2026-04-07,2026-04-15"
    for arg in sys.argv[1:]:
        if arg.startswith("--trade-dates="):
            trade_dates_str = arg.split("=", 1)[1]
    trade_dates = [date.fromisoformat(s.strip()) for s in trade_dates_str.split(",")]

    # Ensure dual-run trace is enabled
    os.environ["DUAL_RUN_TRACE"] = "1"

    use_enhanced = os.environ.get("USE_ENHANCED_MAINLINE", "0") == "1"
    print(f"USE_ENHANCED_MAINLINE={os.environ.get('USE_ENHANCED_MAINLINE', '0')}")
    print(f"DUAL_RUN_TRACE=1")
    print(f"(Writing to DB: {'YES (enhanced path)' if use_enhanced else 'NO (old path, comparison only)'})")
    print()

    print("Connecting to database...")
    gateway = await _get_test_gateway()
    print("Connected.\n")

    read_port = DBThemeDataGateway(db_gateway=gateway)
    write_port = DBStockObjectGateway(db_gateway=gateway)
    event_port = StockEventGatewayAdapter(db_gateway=gateway)
    idempotency_port = StockIdempotencyGatewayAdapter(db_gateway=gateway)

    snapshot_version = f"dual-run-{datetime.now().strftime('%Y%m%dT%H%M%S')}"

    for td in trade_dates:
        print(f"{'='*60}")
        print(f"Processing {td.isoformat()}")
        print(f"{'='*60}")

        # First check pool data
        raw_pool = await read_port.get_subject_stock_pool_by_trade_date(td)
        if not raw_pool:
            print(f"  No pool data for {td.isoformat()} — skipping")
            continue

        print(f"  Pool rows: {len(raw_pool)}")
        if isinstance(raw_pool[0], dict):
            subject_keys = sorted({r["subject_key"] for r in raw_pool})
        else:
            subject_keys = sorted({r.subject_key for r in raw_pool})
        print(f"  Unique subjects: {len(subject_keys)}")

        batch_id = f"dual-run-{td.isoformat()}"
        trace_id = f"dual-run-{td.isoformat()}"

        job = BuildIdentityJob(
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
        )

        result = await job.execute(
            trade_date=td,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
        )

        print(f"  Result: status={result.status}, affected_rows={result.affected_rows}")
        print(f"  Metrics: {result.metrics}")

        # Read comparison JSON
        comparison_file = Path("tmp") / f"dual_run_identity_{td.isoformat()}_{snapshot_version}.json"
        if comparison_file.exists():
            data = json.loads(comparison_file.read_text())
            print(f"\n  --- Comparison Summary ---")
            print(f"  Total subjects: {data['total_subjects']}")
            print(f"  Agreement: {data['agreement_count']}")
            print(f"  Disagreement: {data['disagreement_count']}")
            print(f"  New path active: {data['new_path_active']}")

            # Show disagreements in detail
            disagreements = [c for c in data["comparisons"] if not c["agreement"]]
            if disagreements:
                print(f"\n  --- Disagreements ({len(disagreements)}) ---")
                for d in disagreements:
                    print(f"\n  Subject: {d['subject_key']} ({d['subject_name']})")
                    print(f"    OLD: status={d['old']['identity_status']}, main_theme={d['old']['rule_is_main_theme']}, "
                          f"composite={d['old']['composite_score']}, logic={d['old']['logic_score']}, market={d['old']['market_score']}")
                    print(f"    NEW: status={d['new']['identity_status']}, main_theme={d['new']['rule_is_main_theme']}, "
                          f"composite={d['new']['composite_score']}, logic={d['new']['logic_score']}, market={d['new']['market_score']}, "
                          f"tier={d['new']['theme_tier']}")
                    if d['new'].get('conclusion'):
                        print(f"    conclusion: {d['new']['conclusion']}")

            # Show agreements briefly
            agreements = [c for c in data["comparisons"] if c["agreement"]]
            print(f"\n  --- Agreements ({len(agreements)}) ---")
            for a in agreements:
                print(f"    {a['subject_key']} ({a['subject_name']}): {a['old']['identity_status']}")
        else:
            print(f"  WARNING: Comparison file not found at {comparison_file}")

        print()

    await gateway.close()
    print("Done.")


if __name__ == "__main__":
    if os.getenv("RUN_REPLAY_DB", "0") != "1":
        print("Set RUN_REPLAY_DB=1 to enable real DB access.")
        sys.exit(1)
    asyncio.run(main())
