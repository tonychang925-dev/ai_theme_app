#!/usr/bin/env python3
"""为 4/15-4/30 补齐 Layer C 强势股观察池数据。

运行 BuildPostMarketRecapJob 产出 strong_stock_watch_pool 及快照。
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from uuid import uuid4

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 同时添加 stock_processing_service 自身
SPS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SPS_ROOT not in sys.path:
    sys.path.insert(0, SPS_ROOT)

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.jobs.build_post_market_recap_job import (
    BuildPostMarketRecapJob,
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

# 4/15 - 4/30 所有交易日（跳过周末）
TRADE_DATES = [
    date(2026, 4, 15),
    date(2026, 4, 16),
    date(2026, 4, 17),
    date(2026, 4, 20),
    date(2026, 4, 21),
    date(2026, 4, 22),
    date(2026, 4, 23),
    date(2026, 4, 24),
    date(2026, 4, 27),
    date(2026, 4, 28),
    date(2026, 4, 29),
    date(2026, 4, 30),
]

# 每次重建递增版本以绕过幂等锁
BACKFILL_VERSION = "layer_c_v7"


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

    # ── Step 0: 清空旧数据 ──
    # history: 按日期清理，确保 API 展示新鲜数据
    # pool: 全部清空后让每天 build 滚动累积（watch_window_days 才能到期触发剔除）
    async with gw._client.pool.acquire() as conn:
        for td in TRADE_DATES:
            h = await conn.execute(
                "DELETE FROM strong_stock_watch_history WHERE trade_date = $1::date",
                td,
            )
        p = await conn.execute("DELETE FROM strong_stock_watch_pool")
        print(f"清理: history(全部日期) pool 全部删除({p.split()[-1]} rows)")

    recap_job = BuildPostMarketRecapJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    for td in TRADE_DATES:
        snapshot_version = BACKFILL_VERSION
        batch_id = uuid4().hex[:12]
        trace_id = uuid4().hex[:12]

        try:
            result = await recap_job.execute(
                trade_date=td,
                snapshot_version=snapshot_version,
                batch_id=batch_id,
                trace_id=trace_id,
                lookback_days=7,
            )
            status = result.status
            ws = getattr(result, "watch_pool_size", "N/A")
            pruned = getattr(result, "pruned_count", "N/A")
            print(f"[{td}] status={status} watch_pool={ws} pruned={pruned}")
        except Exception as e:
            print(f"[{td}] FAILED: {e}")

    # ── 汇总：对比 history vs pool ──
    async with gw._client.pool.acquire() as conn:
        print(f"\n{'='*60}")
        print(f"{'Date':<12} {'pool_total':>10} {'pool_weaken':>12} {'hist_nonrem':>12}")
        print(f"{'='*60}")
        for td in TRADE_DATES:
            pool_total = await conn.fetchval(
                "SELECT COUNT(*) FROM strong_stock_watch_pool WHERE last_trade_date = $1::date", td,
            )
            pool_weaken = await conn.fetchval(
                "SELECT COUNT(*) FROM strong_stock_watch_pool WHERE last_trade_date = $1::date AND watch_status = 'weakening'", td,
            )
            hist_nonrem = await conn.fetchval(
                "SELECT COUNT(*) FROM strong_stock_watch_history WHERE trade_date = $1::date AND watch_status <> 'removed'", td,
            )
            print(f"{td}  {str(pool_total):>10}  {str(pool_weaken):>12}  {str(hist_nonrem):>12}")

    await gw.close()
    print("\n✅ Layer C backfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
