#!/usr/bin/env python3
"""题材股票日快照 — 后端验证脚本.

测试矩阵:
  1. provider=jyhf,        on_existing=skip     → 旧链路不变
  2. provider=tushare_join, on_existing=replace  → 首次生成
  3. provider=tushare_join, on_existing=replace  → 删除后重建
  4. provider=tushare_join, on_existing=skip     → 已有则跳过
  5. provider=tushare_join, on_existing=upsert   → 覆盖更新
  6. force=true                                   → 等价 replace

用法:
  python -m stock_processing_service.application.jobs.subject_stock_snapshot.test_snapshot \
      --trade-date 2026-06-05 --provider tushare_join --on-existing replace
  python -m stock_processing_service.application.jobs.subject_stock_snapshot.test_snapshot \
      --trade-date 2026-06-05 --provider jyhf --jyhf-token YOUR_TOKEN
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path

# 确保项目根在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg

from stock_processing_service.application.jobs.subject_stock_snapshot.base import (
    SubjectStockDailySnapshotProducer,
    SubjectStockSnapshotBuildRequest,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.config import (
    SubjectStockSnapshotConfig,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.factory import (
    SubjectStockSnapshotProducerFactory,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.jyhf_producer import (
    JyhfSubjectStockDailySnapshotProducer,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.orchestrator import (
    SubjectStockDailySnapshotOrchestrator,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.tushare_join_producer import (
    TushareJoinSubjectStockDailySnapshotProducer,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_snapshot")


def _pg_dsn() -> str:
    return os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'zxbzj~925')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DATABASE', 'stock_data_test')}",
    )


async def _make_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(_pg_dsn(), min_size=1, max_size=5)


async def _test_direct(
    producer: SubjectStockDailySnapshotProducer,
    provider: str,
    trade_date: date,
    on_existing: str,
    force: bool,
):
    """直接调用 Producer（绕过 Orchestrator）."""
    request = SubjectStockSnapshotBuildRequest(
        trade_date=trade_date,
        provider=provider,
        on_existing=on_existing,  # type: ignore[arg-type]
        force=force,
    )
    result = await producer.build(request)
    _print_result(result)


async def _test_orchestrator(
    orchestrator: SubjectStockDailySnapshotOrchestrator,
    trade_date: date,
    provider: str,
    on_existing: str,
    force: bool,
):
    """通过 Orchestrator 调用（含审计记录）."""
    result = await orchestrator.execute(
        trade_date=trade_date,
        provider=provider,
        on_existing=on_existing,
        force=force,
    )
    _print_result(result)


def _print_result(result):
    import json as _json
    print(f"\n{'='*60}")
    print(f"provider    = {result.provider}")
    print(f"trade_date  = {result.trade_date}")
    print(f"status      = {result.status}")
    print(f"rows        = {result.affected_rows}")
    if result.warnings:
        print(f"warnings    = {result.warnings}")
    if result.metrics:
        # 精简打印
        keys = [
            "stock_daily_count", "mapped_stock_count",
            "matched_stock_count", "missing_stock_count", "match_rate",
            "subjects_collected", "subjects_touched", "source",
        ]
        summary = {k: result.metrics[k] for k in keys if k in result.metrics}
        print(f"metrics     = {_json.dumps(summary, ensure_ascii=False)}")
    print(f"{'='*60}\n")


def parse_args():
    p = argparse.ArgumentParser(description="题材股票日快照测试")
    p.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    p.add_argument("--provider", default="tushare_join", choices=["jyhf", "tushare_join"])
    p.add_argument("--on-existing", default="replace", choices=["skip", "upsert", "replace"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--jyhf-token", default="", help="JYHF token (仅 provider=jyhf 时需要)")
    p.add_argument("--use-orchestrator", action="store_true", help="通过 Orchestrator 调用 (含审计记录)")
    return p.parse_args()


async def main():
    args = parse_args()
    td = date.fromisoformat(args.trade_date)
    pool = await _make_pool()

    try:
        # ── 构建 Producer ──
        jyhf_producer = JyhfSubjectStockDailySnapshotProducer(
            db_pool=pool, jyhf_token=args.jyhf_token,
        )
        tushare_producer = TushareJoinSubjectStockDailySnapshotProducer(db_pool=pool)

        factory = SubjectStockSnapshotProducerFactory(
            jyhf_producer=jyhf_producer,
            tushare_join_producer=tushare_producer,
        )

        if args.use_orchestrator:
            orchestrator = SubjectStockDailySnapshotOrchestrator(
                factory=factory,
                db_pool=pool,
                config=SubjectStockSnapshotConfig(
                    provider=args.provider,  # type: ignore[arg-type]
                    on_existing=args.on_existing,  # type: ignore[arg-type]
                ),
            )
            await _test_orchestrator(
                orchestrator, td,
                provider=args.provider,
                on_existing=args.on_existing,
                force=args.force,
            )
        else:
            producer = factory.get(args.provider)
            await _test_direct(
                producer, args.provider, td,
                on_existing=args.on_existing,
                force=args.force,
            )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
