"""subject_rank 可插拔数据源 — 后端验证脚本.

用法:
  # 默认 provider (jyhf)
  PYTHONPATH=. python stock_processing_service/application/jobs/subject_rank/test_rank.py \
      --trade-date 2026-06-05 --provider jyhf

  # SnapshotAgg provider (从 subject_stock_daily_snapshot 聚合)
  PYTHONPATH=. python stock_processing_service/application/jobs/subject_rank/test_rank.py \
      --trade-date 2026-06-05 --provider snapshot_agg --on-existing replace

  # 通过 Orchestrator（含审计记录）
  PYTHONPATH=. python stock_processing_service/application/jobs/subject_rank/test_rank.py \
      --trade-date 2026-06-05 --provider snapshot_agg --on-existing replace --use-orchestrator
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date

PROJECT_ROOT = "/Users/admin/Desktop/ai_theme_app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test subject_rank producers")
    parser.add_argument("--trade-date", required=True, help="交易日 (YYYY-MM-DD)")
    parser.add_argument("--provider", default="jyhf", choices=["jyhf", "snapshot_agg"])
    parser.add_argument("--on-existing", default="skip", choices=["skip", "upsert", "replace"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--use-orchestrator", action="store_true")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    import sys
    sys.path.insert(0, PROJECT_ROOT)

    from database_service.managers.postgres_manager import PostgresDatabaseManager
    from database_service.scripts.import_jyhf_history_incremental import get_postgres_config

    trade_date_val = date.fromisoformat(args.trade_date)
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        if args.use_orchestrator:
            from stock_processing_service.application.jobs.subject_rank.jyhf_producer import (
                JyhfSubjectRankProducer,
            )
            from stock_processing_service.application.jobs.subject_rank.snapshot_agg_producer import (
                SnapshotAggSubjectRankProducer,
            )
            from stock_processing_service.application.jobs.subject_rank.factory import (
                SubjectRankProducerFactory,
            )
            from stock_processing_service.application.jobs.subject_rank.orchestrator import (
                SubjectRankOrchestrator,
            )

            jyhf_producer = JyhfSubjectRankProducer(db_pool=manager.pool)
            snapshot_agg_producer = SnapshotAggSubjectRankProducer(db_pool=manager.pool)
            factory = SubjectRankProducerFactory(
                jyhf_producer=jyhf_producer,
                snapshot_agg_producer=snapshot_agg_producer,
            )
            orchestrator = SubjectRankOrchestrator(factory=factory, db_pool=manager.pool)

            result = await orchestrator.execute(
                trade_date=trade_date_val,
                provider=args.provider,
                force=args.force,
                on_existing=args.on_existing,
            )
        else:
            if args.provider == "jyhf":
                from stock_processing_service.application.jobs.subject_rank.jyhf_producer import (
                    JyhfSubjectRankProducer,
                )
                producer = JyhfSubjectRankProducer(db_pool=manager.pool)
            else:
                from stock_processing_service.application.jobs.subject_rank.snapshot_agg_producer import (
                    SnapshotAggSubjectRankProducer,
                )
                producer = SnapshotAggSubjectRankProducer(db_pool=manager.pool)

            from stock_processing_service.application.jobs.subject_rank.base import (
                SubjectRankBuildRequest,
            )
            request = SubjectRankBuildRequest(
                trade_date=trade_date_val,
                provider=args.provider,
                force=args.force,
                on_existing=args.on_existing,  # type: ignore[arg-type]
            )
            result = await producer.build(request)
    finally:
        await manager.disconnect()

    print(f"\n{'='*60}")
    print(f"provider:       {result.provider}")
    print(f"trade_date:     {result.trade_date}")
    print(f"status:         {result.status}")
    print(f"affected_rows:  {result.affected_rows}")
    print(f"warnings:       {result.warnings}")
    print(f"metrics:        {result.metrics}")
    print(f"{'='*60}")

    return 0 if result.status.startswith("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))
