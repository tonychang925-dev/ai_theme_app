#!/usr/bin/env python3
"""P2 Worker CLI: SPS 子进程执行单个 collection runner，输出 JSON 结果。

用法:
  python -m stock_processing_service.workers.run_collection_runner \
    --runner-key recap.snapshot --trade-date 2026-05-25 --payload-json '{}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date as date_type
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _db_name() -> str:
    return os.getenv("PG_DATABASE", "stock_data_test")


async def main_async() -> int:
    args = parse_args()

    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.gateway import DatabaseGateway
    from stock_processing_service.application.orchestrators.bootstrap import build_container
    from stock_processing_service.application.services.collection_task_registry import (
        CollectionTaskContext, get_default_registry,
    )

    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_database=_db_name(),
    )
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    try:
        from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
        facade = _ReplayDatabaseStockFacade(gw)
        container = build_container(facade)
        registry = get_default_registry()

        runner = registry.get(args.runner_key)
        if runner is None:
            print(f"unknown runner_key: {args.runner_key}", flush=True)
            return 2

        payload: dict[str, Any] = json.loads(args.payload_json or "{}")

        context = CollectionTaskContext(
            trade_date=args.trade_date,
            payload=payload,
            env=os.environ.copy(),
            container=container,
            project_root=os.getenv("AI_THEME_PROJECT_ROOT", str(PROJECT_ROOT)),
            python_bin=sys.executable,
            commands=None,
        )

        result = await runner.run(context)

        output = {
            "status": result.status,
            "current_label": result.current_label,
            "progress_percent": result.progress_percent,
            "logs": result.logs,
            "error_message": result.error_message,
        }
        print("__SPS_RESULT__" + json.dumps(output, ensure_ascii=False), flush=True)

        return 0 if result.status == "success" else 2
    finally:
        close = getattr(gw, "close", None)
        if callable(close):
            await close()


def parse_args():
    p = argparse.ArgumentParser(description="SPS collection worker")
    p.add_argument("--runner-key", required=True)
    p.add_argument("--trade-date", required=True)
    p.add_argument("--payload-json", default="{}")
    return p.parse_args()


if __name__ == "__main__":
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)
