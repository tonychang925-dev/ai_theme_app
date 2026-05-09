#!/usr/bin/env python3
"""tushare_kline 灰度测试 — 直接运行 5 步 Runner 管线。"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.services.collection_orchestrator import (
    CollectionCommandPlanner,
)
from stock_processing_service.application.services.collection_task_registry import (
    CollectionTaskContext,
    get_default_registry,
)
from stock_processing_service.application.orchestrators.bootstrap import build_container


async def main():
    trade_date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-05-08"
    trade_date_val = date.fromisoformat(trade_date_str)

    print(f"═══ tushare_kline 灰度测试: {trade_date_str} ═══")

    # ── 初始化 Gateway + Container ──
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
    container = build_container(db_gateway=gw)
    registry = get_default_registry()

    # ── 生成 plan ──
    planner = CollectionCommandPlanner()
    plan = planner.build_task_plan(
        task_key="tushare_kline",
        trade_date=trade_date_str,
        payload={"tushare_pause_seconds": 0.1},
        env={"TUSHARE_TOKEN": os.getenv("TUSHARE_TOKEN", "")},
    )

    print(f"Plan: {len(plan.steps)} steps, {len(plan.commands)} legacy commands")
    for i, s in enumerate(plan.steps):
        mode = f"Runner({s.runner_key})" if s.runner_key else f"Script({len(s.commands)} cmds)"
        print(f"  Step {i+1}: {s.key} → {mode}")

    # ── 执行 steps ──
    context = CollectionTaskContext(
        trade_date=trade_date_str,
        payload={"tushare_pause_seconds": 0.1},
        env={"TUSHARE_TOKEN": os.getenv("TUSHARE_TOKEN", "")},
        container=container,
    )

    for i, step in enumerate(plan.steps):
        print(f"\n── Step {i+1}/{len(plan.steps)}: {step.key} ──")
        if step.runner_key:
            runner = registry.get(step.runner_key)
            if runner is None:
                print(f"  ❌ 未知 runner_key: {step.runner_key}")
                break
            print(f"  执行 Runner: {step.runner_key}")
            try:
                result = await runner.run(context)
                print(f"  结果: status={result.status} label={result.current_label}")
                for log in result.logs:
                    print(f"    {log}")
                if result.status == "failed":
                    print(f"  ⚠️ 失败(继续): {result.error_message}")
                    # Tushare API may not have data yet for recent dates; continue pipeline
            except Exception as e:
                print(f"  ❌ 异常: {e}")
                break
        else:
            print(f"  ⚠️ 无 runner_key，跳过")

    # ── 验库 ──
    print(f"\n── 数据库验收 ──")
    async with gw._client.pool.acquire() as conn:
        for table, label in [
            ("subject_stock_daily_snapshot", "K线快照"),
            ("auction_watch_universe", "竞价观察池"),
            ("pre_market_auction_snapshot", "竞价快照"),
        ]:
            cnt = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE trade_date = $1::date",
                trade_date_val,
            )
            print(f"  {label}: {cnt} rows")

    await gw.close()
    print("\n✅ 灰度测试完成")


if __name__ == "__main__":
    asyncio.run(main())
