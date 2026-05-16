from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import (
        db_connect_kwargs,
        column_exists,
        parse_trade_date,
        require_safe_db,
        table_exists,
        write_json,
    )
else:
    from .common import db_connect_kwargs, column_exists, parse_trade_date, require_safe_db, table_exists, write_json


async def _count_if_table(conn: Any, table: str, sql: str, *args: Any) -> int:
    if not await table_exists(conn, table):
        return 0
    return int(await conn.fetchval(sql, *args) or 0)


async def collect_readiness(db_name: str, trade_date: str, read_db_name: str | None = None) -> dict[str, Any]:
    import asyncpg

    parsed_trade_date = parse_trade_date(trade_date)
    read_db_name = read_db_name or db_name
    write_conn = await asyncpg.connect(**db_connect_kwargs(db_name))
    read_conn = await asyncpg.connect(**db_connect_kwargs(read_db_name))
    try:
        theme_profile_count = await _count_if_table(
            read_conn,
            "theme_match_profile",
            "SELECT COUNT(*) FROM theme_match_profile",
        )
        theme_gate_profile_count = await _count_if_table(
            read_conn,
            "theme_gate_profile",
            "SELECT COUNT(*) FROM theme_gate_profile",
        )
        theme_profile_ext_count = await _count_if_table(
            read_conn,
            "theme_profile_ext",
            "SELECT COUNT(*) FROM theme_profile_ext",
        )
        subject_stock_pool_count = await _count_if_table(
            read_conn,
            "subject_stock_daily_snapshot",
            "SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date = $1::date",
            parsed_trade_date,
        )
        leaderboard_count = await _count_if_table(
            read_conn,
            "theme_stock_leaderboard",
            "SELECT COUNT(*) FROM theme_stock_leaderboard WHERE trade_date = $1::date",
            parsed_trade_date,
        )
        strong_watch_count = 0
        if await table_exists(read_conn, "strong_stock_watch_pool"):
            if await column_exists(read_conn, "strong_stock_watch_pool", "trade_date"):
                strong_watch_count = await _count_if_table(
                    read_conn,
                    "strong_stock_watch_pool",
                    "SELECT COUNT(*) FROM strong_stock_watch_pool WHERE trade_date = $1::date",
                    parsed_trade_date,
                )
            else:
                strong_watch_count = await _count_if_table(
                    read_conn,
                    "strong_stock_watch_pool",
                    "SELECT COUNT(*) FROM strong_stock_watch_pool",
                )
        elif await table_exists(read_conn, "strong_stock_watch_view"):
            strong_watch_count = await _count_if_table(
                read_conn,
                "strong_stock_watch_view",
                "SELECT COUNT(*) FROM strong_stock_watch_view",
            )
        w2s_count = 0
        if await table_exists(read_conn, "weak_to_strong_candidate_pool"):
            has_trade_date = await column_exists(read_conn, "weak_to_strong_candidate_pool", "trade_date")
            has_next_trade_date = await column_exists(read_conn, "weak_to_strong_candidate_pool", "next_trade_date")
            if has_trade_date and has_next_trade_date:
                w2s_count = int(
                    await read_conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM weak_to_strong_candidate_pool
                        WHERE trade_date = $1::date OR next_trade_date = $1::date
                        """,
                        parsed_trade_date,
                    )
                    or 0
                )
            elif has_trade_date:
                w2s_count = await _count_if_table(
                    read_conn,
                    "weak_to_strong_candidate_pool",
                    "SELECT COUNT(*) FROM weak_to_strong_candidate_pool WHERE trade_date = $1::date",
                    parsed_trade_date,
                )
            else:
                w2s_count = await _count_if_table(
                    read_conn,
                    "weak_to_strong_candidate_pool",
                    "SELECT COUNT(*) FROM weak_to_strong_candidate_pool",
                )
        mainline_identity_count = await _count_if_table(
            read_conn,
            "theme_mainline_identity_registry",
            "SELECT COUNT(*) FROM theme_mainline_identity_registry",
        )
        if await table_exists(read_conn, "theme_cycle_judgement_v2"):
            if await column_exists(read_conn, "theme_cycle_judgement_v2", "trade_date"):
                cycle_count = await _count_if_table(
                    read_conn,
                    "theme_cycle_judgement_v2",
                    "SELECT COUNT(*) FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date",
                    parsed_trade_date,
                )
            else:
                cycle_count = await _count_if_table(
                    read_conn,
                    "theme_cycle_judgement_v2",
                    "SELECT COUNT(*) FROM theme_cycle_judgement_v2",
                )
        else:
            cycle_count = 0
        event_review_queue_exists = await table_exists(write_conn, "event_review_queue")
        event_subject_map_exists = await table_exists(write_conn, "event_subject_map")
        pre_market_brief_snapshot_exists = await table_exists(write_conn, "pre_market_brief_snapshot")
    finally:
        await write_conn.close()
        await read_conn.close()

    theme_profiles_count = theme_gate_profile_count or theme_profile_count
    checks = {
        "db_name": db_name,
        "read_db_name": read_db_name,
        "trade_date": trade_date,
        "theme_profiles_count": theme_profiles_count,
        "theme_gate_profile_count": theme_gate_profile_count,
        "theme_profile_ext_count": theme_profile_ext_count,
        "subject_stock_pool_count": subject_stock_pool_count,
        "leaderboard_count": leaderboard_count,
        "strong_watch_count": strong_watch_count,
        "w2s_count": w2s_count,
        "mainline_identity_count": mainline_identity_count,
        "cycle_count": cycle_count,
        "event_review_queue_exists": event_review_queue_exists,
        "event_subject_map_exists": event_subject_map_exists,
        "pre_market_brief_snapshot_exists": pre_market_brief_snapshot_exists,
    }
    checks["passed"] = (
        theme_profiles_count > 0
        and event_subject_map_exists
        and event_review_queue_exists
        and pre_market_brief_snapshot_exists
    )
    return checks


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="检查盘前必读 E2E 所需 stock_data 基础数据。")
    parser.add_argument("--db-name", default="stock_data")
    parser.add_argument("--read-db-name", default=os.getenv("READ_PG_DATABASE") or os.getenv("READ_DB_NAME"))
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    require_safe_db(args.db_name, allow_production=args.allow_production)
    result = await collect_readiness(args.db_name, args.trade_date, read_db_name=args.read_db_name)
    if args.out:
        write_json(Path(args.out), result)
    print(result)
    if not result["passed"]:
        raise SystemExit(1)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
