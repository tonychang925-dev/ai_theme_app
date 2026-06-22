#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database_service.config import DatabaseConfig, DatabaseType  # noqa: E402
from database_service.managers.postgres_manager import PostgresDatabaseManager  # noqa: E402
from stock_processing_service.integrations.a_stock_data.clients.ths_client import ThsClient  # noqa: E402
from stock_processing_service.integrations.a_stock_data.jobs.collect_ths_hot_reason_job import (  # noqa: E402
    CollectThsHotReasonJob,
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _config_from_dsn(dsn: str) -> DatabaseConfig:
    parsed = urlparse(dsn)
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=parsed.hostname or "localhost",
        postgres_port=parsed.port or 5432,
        postgres_database=(parsed.path or "/stock_data_test").lstrip("/"),
        postgres_username=parsed.username or "postgres",
        postgres_password=parsed.password or "",
        postgres_schema="public",
        postgres_pool_size=5,
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _run(args: argparse.Namespace) -> int:
    dsn = args.dsn or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required, or pass --dsn")

    manager = PostgresDatabaseManager(_config_from_dsn(dsn))
    await manager.connect()
    try:
        client = ThsClient(timeout_seconds=args.timeout_seconds, base_url=args.base_url)
        job = CollectThsHotReasonJob(write_port=manager, client=client)
        results = []
        for item in args.dates:
            trade_date = date.fromisoformat(item)
            try:
                result = await job.execute(trade_date)
                payload = {
                    "trade_date": item,
                    "status": result.status,
                    "affected_rows": result.affected_rows,
                    "warnings": result.warnings,
                    "metrics": result.metrics,
                }
            except Exception as exc:
                payload = {
                    "trade_date": item,
                    "status": "failed",
                    "affected_rows": 0,
                    "warnings": [str(exc)],
                    "metrics": {},
                }
                if not args.continue_on_error:
                    print(json.dumps(payload, ensure_ascii=False, default=_json_default))
                    return 2
            results.append(payload)
            print(json.dumps(payload, ensure_ascii=False, default=_json_default))
        return 0 if all(item["status"] == "ok" for item in results) else 2
    finally:
        await manager.disconnect()


def _parse_args() -> argparse.Namespace:
    _load_env_file(Path.cwd() / ".env.theme")
    parser = argparse.ArgumentParser(description="Collect THS hot reason snapshots into local DB.")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dates", nargs="+", required=True, help="Trade dates, e.g. 2026-06-18 2026-06-19")
    parser.add_argument(
        "--base-url",
        default=(
            "http://zx.10jqka.com.cn/event/api/getharden/"
            "date/{date}/orderby/date/orderway/desc/charset/GBK/"
        ),
        help="THS hot reason endpoint URL.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
