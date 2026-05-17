from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import (
        column_exists,
        db_connect_kwargs,
        parse_trade_date,
        require_safe_db,
        table_exists,
        write_json,
    )
else:
    from .common import column_exists, db_connect_kwargs, parse_trade_date, require_safe_db, table_exists, write_json


async def cleanup_run(
    *,
    db_name: str,
    source: str,
    trade_date: str,
    run_id: str,
    dry_run: bool = False,
    delete_final_snapshot: bool = False,
    clean_trade_date_all_e2e: bool = False,
) -> dict[str, Any]:
    import asyncpg

    parsed_trade_date = parse_trade_date(trade_date)
    conn = await asyncpg.connect(**db_connect_kwargs(db_name))
    try:
        if not await table_exists(conn, "news_raw"):
            return {"db_name": db_name, "run_id": run_id, "skipped": "news_raw_missing"}

        if clean_trade_date_all_e2e:
            raw_where = """
            source = $1
            AND publish_date::date = $2::date
            AND (
              news_id::text LIKE 'pm_e2e_%'
              OR url::text LIKE 'e2e://pm_e2e_%'
              OR title::text LIKE '%pm_e2e_%'
              OR content::text LIKE '%pm_e2e_%'
            )
            """
        else:
            raw_where = """
            source = $1
            AND (
              news_id::text LIKE $2
              OR url::text LIKE $3
              OR title::text LIKE $4
              OR content::text LIKE $4
            )
            """
        if clean_trade_date_all_e2e:
            raw_rows = await conn.fetch(
                f"SELECT id FROM news_raw WHERE {raw_where}",
                source,
                parsed_trade_date,
            )
        else:
            raw_rows = await conn.fetch(
                f"SELECT id FROM news_raw WHERE {raw_where}",
                source,
                f"{run_id}:%",
                f"e2e://{run_id}/%",
                f"%{run_id}%",
            )
        raw_ids = [int(row["id"]) for row in raw_rows]

        event_ids: list[int] = []
        if raw_ids and await table_exists(conn, "news_event"):
            event_ids = [
                int(row["id"])
                for row in await conn.fetch("SELECT id FROM news_event WHERE news_id = ANY($1::int[])", raw_ids)
            ]

        counts = {
            "event_subject_map": 0,
            "event_theme_map": 0,
            "event_review_queue": 0,
            "news_event": len(event_ids),
            "news_raw": len(raw_ids),
            "pre_market_brief_snapshot": 0,
        }
        if dry_run:
            return {
                "db_name": db_name,
                "run_id": run_id,
                "trade_date": trade_date,
                "dry_run": True,
                "delete_final_snapshot": delete_final_snapshot,
                "clean_trade_date_all_e2e": clean_trade_date_all_e2e,
                "counts": counts,
            }

        async with conn.transaction():
            if event_ids and await table_exists(conn, "event_subject_map"):
                result = await conn.execute("DELETE FROM event_subject_map WHERE event_id = ANY($1::int[])", event_ids)
                counts["event_subject_map"] = _affected(result)
            if event_ids and await table_exists(conn, "event_theme_map"):
                result = await conn.execute("DELETE FROM event_theme_map WHERE event_id = ANY($1::int[])", event_ids)
                counts["event_theme_map"] = _affected(result)
            if event_ids and await table_exists(conn, "event_review_queue"):
                result = await conn.execute("DELETE FROM event_review_queue WHERE event_id = ANY($1::bigint[])", event_ids)
                counts["event_review_queue"] = _affected(result)
            if event_ids and await table_exists(conn, "news_event"):
                result = await conn.execute("DELETE FROM news_event WHERE id = ANY($1::int[])", event_ids)
                counts["news_event"] = _affected(result)
            if raw_ids:
                result = await conn.execute("DELETE FROM news_raw WHERE id = ANY($1::int[])", raw_ids)
                counts["news_raw"] = _affected(result)
            if await table_exists(conn, "pre_market_brief_snapshot"):
                if delete_final_snapshot:
                    result = await _delete_e2e_snapshot(conn, trade_date)
                elif await column_exists(conn, "pre_market_brief_snapshot", "status"):
                    result = await conn.execute(
                        """
                        DELETE FROM pre_market_brief_snapshot
                        WHERE trade_date = $1::date
                          AND COALESCE(status, 'draft') <> 'final'
                        """,
                        parsed_trade_date,
                    )
                else:
                    result = await conn.execute(
                        "DELETE FROM pre_market_brief_snapshot WHERE trade_date = $1::date",
                        parsed_trade_date,
                    )
                counts["pre_market_brief_snapshot"] = _affected(result)
        return {
            "db_name": db_name,
            "run_id": run_id,
            "trade_date": trade_date,
            "dry_run": False,
            "delete_final_snapshot": delete_final_snapshot,
            "clean_trade_date_all_e2e": clean_trade_date_all_e2e,
            "counts": counts,
        }
    finally:
        await conn.close()


def _affected(result: str) -> int:
    try:
        return int(str(result).split()[-1])
    except Exception:
        return 0


async def _delete_e2e_snapshot(conn: Any, trade_date: str) -> str:
    parsed_trade_date = parse_trade_date(trade_date)
    has_source_name = await column_exists(conn, "pre_market_brief_snapshot", "source_name")
    has_source_trace_id = await column_exists(conn, "pre_market_brief_snapshot", "source_trace_id")
    has_snapshot_version = await column_exists(conn, "pre_market_brief_snapshot", "snapshot_version")
    conditions = []
    if has_source_name:
        conditions.append("source_name = 'pre_market_brief_builder'")
    if has_source_trace_id:
        conditions.append("source_trace_id LIKE 'e2e:%'")
    if has_snapshot_version:
        conditions.append("snapshot_version = 'pre_market_brief.v1'")
    if not conditions:
        return await conn.execute("DELETE FROM pre_market_brief_snapshot WHERE trade_date = $1::date", parsed_trade_date)
    return await conn.execute(
        f"""
        DELETE FROM pre_market_brief_snapshot
        WHERE trade_date = $1::date
          AND ({' OR '.join(conditions)})
        """,
        parsed_trade_date,
    )


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="清理盘前必读 E2E run 的数据库痕迹。")
    parser.add_argument("--db-name", default="stock_data")
    parser.add_argument("--source", default="akshare_replay")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delete-final-snapshot", action="store_true")
    parser.add_argument(
        "--clean-trade-date-all-e2e",
        action="store_true",
        help="按 trade_date 清理所有 akshare_replay E2E 输入及其下游数据，避免同日期旧 run 污染报告。",
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    require_safe_db(args.db_name, allow_production=args.allow_production)
    result = await cleanup_run(
        db_name=args.db_name,
        source=args.source,
        trade_date=args.trade_date,
        run_id=args.run_id,
        dry_run=args.dry_run,
        delete_final_snapshot=args.delete_final_snapshot,
        clean_trade_date_all_e2e=args.clean_trade_date_all_e2e,
    )
    if args.out:
        write_json(Path(args.out), result)
    print(result)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
