from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import (
        db_connect_kwargs,
        read_jsonl,
        require_safe_db,
        table_exists,
        write_json,
    )
else:
    from .common import db_connect_kwargs, read_jsonl, require_safe_db, table_exists, write_json


async def trace_run(
    *,
    db_name: str,
    run_id: str,
    trade_date: str,
    input_path: Path | None = None,
) -> dict[str, Any]:
    import asyncpg

    expected = _expected_cases(input_path) if input_path else {}
    conn = await asyncpg.connect(**db_connect_kwargs(db_name))
    try:
        if not await table_exists(conn, "news_raw"):
            return {"run_id": run_id, "trade_date": trade_date, "rows": [], "counts": {"news_raw_count": 0}}

        rows = await conn.fetch(
            """
            SELECT
              nr.id AS news_raw_id,
              nr.news_id::text AS external_id,
              nr.title,
              nr.source,
              nr.publish_date,
              nr.created_at AS raw_created_at,
              ne.id AS news_event_id,
              ne.created_at AS event_created_at
            FROM news_raw nr
            LEFT JOIN news_event ne ON ne.news_id = nr.id
            WHERE nr.source = 'akshare_replay'
              AND (
                nr.news_id::text LIKE $1
                OR nr.url::text LIKE $2
                OR nr.title::text LIKE $3
                OR nr.content::text LIKE $3
              )
            ORDER BY nr.id
            """,
            f"{run_id}:%",
            f"e2e://{run_id}/%",
            f"%{run_id}%",
        )
        event_ids = [int(row["news_event_id"]) for row in rows if row["news_event_id"] is not None]
        mappings = await _fetch_mappings(conn, event_ids)
        reviews = await _fetch_reviews(conn, event_ids)
    finally:
        await conn.close()

    trace_rows: list[dict[str, Any]] = []
    for row in rows:
        external_id = str(row["external_id"] or "")
        case_id = external_id.split(":")[-1] if ":" in external_id else expected.get(external_id, {}).get("case_id")
        event_id = row["news_event_id"]
        event_mappings = mappings.get(int(event_id), []) if event_id is not None else []
        primary = event_mappings[0] if event_mappings else {}
        trace_rows.append(
            {
                "case_id": case_id,
                "external_id": external_id,
                "news_raw_id": row["news_raw_id"],
                "news_event_id": event_id,
                "decision_id": None,
                "primary_subject_key": primary.get("subject_key"),
                "primary_theme_name": primary.get("theme_name"),
                "related_subject_keys": [item.get("subject_key") for item in event_mappings[1:]],
                "related_theme_names": [item.get("theme_name") for item in event_mappings[1:]],
                "review_status": reviews.get(int(event_id), {}).get("review_status") if event_id is not None else None,
                "pending_status": None,
                "dead_letter_status": None,
            }
        )

    counts = {
        "expected_input_count": len(expected),
        "news_raw_count": len({row["news_raw_id"] for row in rows}),
        "news_event_count": len({row["news_event_id"] for row in rows if row["news_event_id"] is not None}),
        "event_theme_map_count": sum(len(items) for items in mappings.values()),
        "review_queue_count": len(reviews),
    }
    return {"run_id": run_id, "trade_date": trade_date, "counts": counts, "rows": trace_rows}


def _expected_cases(input_path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("external_id")): row for row in read_jsonl(input_path)}


async def _fetch_mappings(conn: Any, event_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not event_ids or not await table_exists(conn, "event_theme_map"):
        return {}
    rows = await conn.fetch(
        """
        SELECT
          etm.event_id,
          COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) AS subject_key,
          tm.name AS theme_name,
          etm.confidence,
          etm.match_reason,
          etm.created_at
        FROM event_theme_map etm
        LEFT JOIN theme_master tm ON tm.id = etm.theme_id
        WHERE etm.event_id = ANY($1::int[])
        ORDER BY etm.event_id, etm.confidence DESC NULLS LAST, etm.created_at ASC
        """,
        event_ids,
    )
    result: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(int(row["event_id"]), []).append(dict(row))
    return result


async def _fetch_reviews(conn: Any, event_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not event_ids or not await table_exists(conn, "event_review_queue"):
        return {}
    rows = await conn.fetch(
        """
        SELECT event_id, review_status, proposed_theme_name, proposed_theme_confidence, reason
        FROM event_review_queue
        WHERE event_id = ANY($1::bigint[])
        """,
        event_ids,
    )
    return {int(row["event_id"]): dict(row) for row in rows}


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="追踪盘前必读 E2E case 从 raw 到 mapping/review 的 DB 状态。")
    parser.add_argument("--db-name", default="stock_data")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()

    require_safe_db(args.db_name, allow_production=args.allow_production)
    result = await trace_run(
        db_name=args.db_name,
        run_id=args.run_id,
        trade_date=args.trade_date,
        input_path=Path(args.input) if args.input else None,
    )
    write_json(Path(args.out), result)
    print(result["counts"])


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

