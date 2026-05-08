#!/usr/bin/env python3
"""续命逻辑验证：顺序运行 recap job 4/22 → 4/23，确认维科从池中续命。

流程：
  4/22: recap job → 种子入围维科 → 评分 → 写入持久池
  4/23: recap job → 种子没维科 → refresh 从持久池读取 → 续命评分
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

    job = BuildPostMarketRecapJob(
        read_port=read_port,
        write_port=write_port,
        event_port=event_port,
        idempotency_port=idempotency_port,
    )

    # ── Day 1: 4/22 ──
    td1 = date(2026, 4, 22)
    print(f"── 4/22 recap job ──")
    r1 = await job.execute(td1, "lifeline-v1", uuid4().hex[:12], uuid4().hex[:12])
    print(f"  status={r1.status} rows={r1.affected_rows}")

    # 检查维科是否写入池
    async with gw._client.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM strong_stock_watch_pool WHERE stock_id = '600152.SH'")
        if row:
            print(f"  持久池维科: status={row['watch_status']} entry={row['pool_entry_type']} score={row['watch_score']}")
        else:
            print(f"  持久池维科: NOT FOUND")

    # ── Day 2: 4/23 (新版本，避免幂等跳过) ──
    td2 = date(2026, 4, 23)
    print(f"\n── 4/23 recap job ──")
    r2 = await job.execute(td2, "lifeline-v2", uuid4().hex[:12], uuid4().hex[:12])
    print(f"  status={r2.status} rows={r2.affected_rows}")

    # 检查 recap_doc 中是否包含维科
    recap_doc = {}
    if write_port.recap_docs:
        recap_doc = write_port.recap_docs[-1].recap_doc if len(write_port.recap_docs) > 1 else write_port.recap_docs[0].recap_doc
    top = recap_doc.get("top_candidates", [])
    wk_in_d1 = any("600152" in str(c.get("stock_id", "")) for c in top)
    print(f"  recap top_candidates 含维科: {wk_in_d1} (共{len(top)}条)")

    if wk_in_d1:
        for c in top:
            if "600152" in str(c.get("stock_id", "")):
                print(f"    维科D1: level={c.get('candidate_level')} score={c.get('candidate_score')}")

    # 检查持久池
    async with gw._client.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM strong_stock_watch_pool WHERE stock_id = '600152.SH'")
        if row:
            print(f"  最终持久池维科: status={row['watch_status']} entry={row['pool_entry_type']} score={row['watch_score']}")
        else:
            print(f"  最终持久池维科: NOT FOUND")

    # 检查refresh是否找到了维科
    ref = await gw._client.get_strong_watch_refresh_rows(td2)
    wk_ref = [r for r in ref if '600152' in str(r.get('stock_id', ''))]
    print(f"  4/23 refresh中维科: {len(wk_ref)} 条")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
