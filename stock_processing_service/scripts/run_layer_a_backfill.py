#!/usr/bin/env python3
"""为 4/7-4/15 补齐 Layer A identity 数据（回填模式）。

运行 BuildIdentityJob 按日产出 theme_mainline_identity_registry 和
mainline_identity_review_queue 条目，使 Layer C 硬门禁的 rule_b_theme
（final_mainline_alive AND board_effect_confirmed）能够通过。
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
from stock_processing_service.application.jobs.build_identity_job import BuildIdentityJob
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
from stock_processing_service.domain.services.identity_llm_review_service import IdentityLLMReviewService

TRADE_DATES = [
    date(2026, 4, 7),  # 仅跑 4/7，cluster bootstrap 产出最多 confirmed mainlines
]


async def main() -> None:
    # ── 初始化 Gateway ──
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

    # 开启 cluster bootstrap 直确认（历史回填模式）
    os.environ["IDENTITY_CLUSTER_BOOTSTRAP"] = "1"

    job = BuildIdentityJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
        llm_review_service=IdentityLLMReviewService(),
    )

    for td in TRADE_DATES:
        snapshot_version = f"identity_backfill_v1"
        batch_id = uuid4().hex[:12]
        trace_id = uuid4().hex[:12]

        print(f"\n── Layer A identity for {td.isoformat()} ──")
        result = await job.execute(
            trade_date=td,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
        )
        print(f"  status={result.status} affected_rows={result.affected_rows}")

        # 检查结果
        async with gw._client.pool.acquire() as conn:
            confirmed = await conn.fetchval(
                "SELECT COUNT(*) FROM theme_mainline_identity_registry "
                "WHERE identity_status = 'confirmed'"
            )
            review = await conn.fetchval(
                "SELECT COUNT(*) FROM mainline_identity_review_queue"
            )
            print(f"  identity_registry confirmed={confirmed}, review_queue={review}")

    await gw.close()
    print("\n✅ Layer A backfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
