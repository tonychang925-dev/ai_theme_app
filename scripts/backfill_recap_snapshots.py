#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from frontend_bff.repositories.bff_repository import FrontendBffRepository


async def _run(trade_date: str, db_name: str, include_pre_market: bool) -> None:
    d = date.fromisoformat(trade_date)
    repo = FrontendBffRepository()
    await repo.initialize()
    gw = await DatabaseGateway.initialize(
        config=DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=db_name),
        auto_warm_cache=False,
    )
    try:
        post_report = await repo.fetch_recap_view(trade_date=trade_date, report_type="post_market")
        post_doc = {
            "trade_date": d,
            "snapshot_version": "backfill_from_frontend_bff_v1",
            "payload": {"report": post_report, "source": "frontend_bff.fetch_recap_view"},
        }
        affected_post = await gw.upsert_post_market_recap_snapshot(post_doc)
        print(f"[ok] post_market_recap_snapshot backfilled: {trade_date}, affected={affected_post}")

        if include_pre_market:
            pre_report = await repo.fetch_recap_view(trade_date=trade_date, report_type="pre_market")
            pre_doc = {
                "trade_date": d,
                "snapshot_version": "backfill_from_frontend_bff_v1",
                "payload": {"report": pre_report, "source": "frontend_bff.fetch_recap_view"},
            }
            affected_pre = await gw.upsert_pre_market_brief_snapshot(pre_doc)
            print(f"[ok] pre_market_brief_snapshot backfilled: {trade_date}, affected={affected_pre}")
    finally:
        await repo.close()
        await gw.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill recap snapshots from frontend_bff recap output")
    parser.add_argument("--trade-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--db-name", default="stock_data_test")
    parser.add_argument("--include-pre-market", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.trade_date, args.db_name, args.include_pre_market))


if __name__ == "__main__":
    main()
