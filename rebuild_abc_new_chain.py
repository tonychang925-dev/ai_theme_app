#!/usr/bin/env python3
"""新链 A/B/C 层重建脚本。

独立于 SPS API，直接调用新链 Job 重建指定日期范围的 identity/cycle/state 数据。
不依赖任何旧链脚本。
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import get_config
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_processing_service.infrastructure.gateway_adapters.db_theme_data_gateway import DBThemeDataGateway
from stock_processing_service.infrastructure.gateway_adapters.db_stock_object_gateway import DBStockObjectGateway
from stock_processing_service.application.jobs.build_cycle_judgement_job import BuildCycleJudgementJob
from stock_processing_service.application.jobs.build_identity_job import BuildIdentityJob
from stock_processing_service.application.jobs.build_mainline_state_job import BuildMainlineStateJob


def trading_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return days


class _NoopEventPort:
    async def publish_stock_processing_event(self, event): return "ok"
    async def record_dead_letter(self, *args, **kwargs): return "ok"

class _NoopIdempotencyPort:
    async def acquire_job_idempotency(self, **kwargs): return True
    async def is_job_completed(self, *args, **kwargs): return False
    async def mark_job_completed(self, *args, **kwargs): return None

async def rebuild_date(
    db: PostgresDatabaseManager,
    td: date,
    *,
    run_cycle: bool = True,
    run_identity: bool = True,
    run_state: bool = True,
) -> dict:
    theme_gw = DBThemeDataGateway(db)
    stock_gw = DBStockObjectGateway(db)
    event_port = _NoopEventPort()
    idempotency_port = _NoopIdempotencyPort()

    batch_id = f"rebuild_{td.isoformat().replace('-', '')}"
    trace_id = f"rebuild_{td.isoformat()}_{datetime.now().strftime('%H%M%S')}"
    results = {}

    # Step 1: Cycle Judgement
    if run_cycle:
        cycle_job = BuildCycleJudgementJob(
            read_port=theme_gw,
            write_port=stock_gw,
        )
        cycle_result = await cycle_job.execute(
            trade_date=td,
            batch_id=batch_id,
            trace_id=trace_id,
        )
        results["cycle"] = {
            "status": cycle_result.status,
            "rows": cycle_result.affected_rows,
            "metrics": cycle_result.metrics,
        }
        print(f"  cycle: {cycle_result.status} rows={cycle_result.affected_rows} "
              f"tracked={cycle_result.metrics.get('tracked_subjects', '?')}")

    # Step 2: Identity
    if run_identity:
        identity_job = BuildIdentityJob(
            read_port=theme_gw,
            write_port=stock_gw,
            event_port=event_port,
            idempotency_port=idempotency_port,
        )
        identity_result = await identity_job.execute(
            trade_date=td,
            snapshot_version="identity_rebuild.v1",
            batch_id=batch_id,
            trace_id=trace_id,
        )
        results["identity"] = {
            "status": identity_result.status,
            "rows": identity_result.affected_rows,
            "metrics": identity_result.metrics,
        }
        print(f"  identity: {identity_result.status} rows={identity_result.affected_rows} "
              f"universe={identity_result.metrics.get('universe_subject_count', '?')}")

    # Step 3: Mainline State
    if run_state:
        state_job = BuildMainlineStateJob(
            read_port=theme_gw,
            write_port=stock_gw,
        )
        state_result = await state_job.execute(
            trade_date=td,
            batch_id=batch_id,
            trace_id=trace_id,
        )
        results["state"] = {
            "status": state_result.status,
            "rows": state_result.affected_rows,
            "metrics": state_result.metrics,
        }
        print(f"  state: {state_result.status} rows={state_result.affected_rows}")

    return results


async def main():
    start_str = sys.argv[1] if len(sys.argv) > 1 else "2026-04-15"
    end_str = sys.argv[2] if len(sys.argv) > 2 else "2026-04-30"
    start_date = date.fromisoformat(start_str)
    end_date = date.fromisoformat(end_str)

    days = trading_days(start_date, end_date)
    print(f"Rebuilding {len(days)} trading days: {start_str} → {end_str}")
    print(f"Pipeline: Cycle → Identity → MainlineState")
    print()

    config = get_config()
    db = PostgresDatabaseManager(config)
    await db.connect()

    try:
        for td in days:
            print(f"=== {td.isoformat()} ===")
            try:
                results = await rebuild_date(db, td)
            except Exception as e:
                print(f"  ERROR: {e}")
    finally:
        # PostgresDatabaseManager uses pool-managed connections
        pass

    print(f"\nDone. {len(days)} dates processed.")


if __name__ == "__main__":
    asyncio.run(main())
