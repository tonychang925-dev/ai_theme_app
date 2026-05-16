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
    redis_url: str | None = None,
    decision_stream: str = "stream:events:decision",
    pending_stream: str = "stream:events:pending",
    dead_letter_stream: str = "stream:dead:letter",
    redis_scan_limit: int = 1000,
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

    redis_trace = await _fetch_redis_trace(
        redis_url=redis_url,
        run_id=run_id,
        decision_stream=decision_stream,
        pending_stream=pending_stream,
        dead_letter_stream=dead_letter_stream,
        scan_limit=redis_scan_limit,
    )
    counts = {
        "expected_input_count": len(expected),
        "news_raw_count": len({row["news_raw_id"] for row in rows}),
        "news_event_count": len({row["news_event_id"] for row in rows if row["news_event_id"] is not None}),
        "event_theme_map_count": sum(len(items) for items in mappings.values()),
        "review_queue_count": len(reviews),
        "decision_count": redis_trace["decision_count"],
        "pending_count": redis_trace["pending_count"],
        "dead_letter_count": redis_trace["dead_letter_count"],
    }
    return {
        "run_id": run_id,
        "trade_date": trade_date,
        "counts": counts,
        "redis_streams": redis_trace,
        "rows": trace_rows,
    }


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


async def _fetch_redis_trace(
    *,
    redis_url: str | None,
    run_id: str,
    decision_stream: str,
    pending_stream: str,
    dead_letter_stream: str,
    scan_limit: int,
) -> dict[str, Any]:
    empty = {
        "decision_stream": decision_stream,
        "pending_stream": pending_stream,
        "dead_letter_stream": dead_letter_stream,
        "decision_count": 0,
        "pending_count": 0,
        "dead_letter_count": 0,
        "decision_entries": [],
        "pending_entries": [],
        "dead_letter_entries": [],
    }
    if not redis_url:
        return empty
    try:
        import redis.asyncio as redis
    except Exception as exc:
        return {**empty, "error": f"redis import failed: {exc}"}

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        decision_entries = await _scan_stream_for_run(client, decision_stream, run_id, scan_limit)
        pending_entries = await _scan_stream_for_run(client, pending_stream, run_id, scan_limit)
        dead_entries = await _scan_stream_for_run(client, dead_letter_stream, run_id, scan_limit)
    except Exception as exc:
        return {**empty, "error": str(exc)}
    finally:
        await client.aclose()
    return {
        **empty,
        "decision_count": len(decision_entries),
        "pending_count": len(pending_entries),
        "dead_letter_count": len(dead_entries),
        "decision_entries": decision_entries,
        "pending_entries": pending_entries,
        "dead_letter_entries": dead_entries,
    }


async def _scan_stream_for_run(client: Any, stream: str, run_id: str, scan_limit: int) -> list[dict[str, Any]]:
    entries = await client.xrevrange(stream, max="+", min="-", count=scan_limit)
    matched: list[dict[str, Any]] = []
    for stream_id, fields in entries:
        haystack = str(fields)
        if run_id not in haystack:
            continue
        matched.append(
            {
                "stream_id": stream_id,
                "case_id": _first_matching_field(fields, "case_id"),
                "event_id": _first_matching_field(fields, "event_id"),
                "decision": _first_matching_field(fields, "decision", "action"),
            }
        )
    return list(reversed(matched))


def _first_matching_field(fields: dict[str, Any], *names: str) -> str | None:
    for name in names:
        if fields.get(name):
            return str(fields[name])
    return None


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="追踪盘前必读 E2E case 从 raw 到 mapping/review 的 DB 状态。")
    parser.add_argument("--db-name", default="stock_data")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--out", required=True)
    parser.add_argument("--redis-url")
    parser.add_argument("--decision-stream", default="stream:events:decision")
    parser.add_argument("--pending-stream", default="stream:events:pending")
    parser.add_argument("--dead-letter-stream", default="stream:dead:letter")
    parser.add_argument("--redis-scan-limit", type=int, default=1000)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()

    require_safe_db(args.db_name, allow_production=args.allow_production)
    result = await trace_run(
        db_name=args.db_name,
        run_id=args.run_id,
        trade_date=args.trade_date,
        input_path=Path(args.input) if args.input else None,
        redis_url=args.redis_url,
        decision_stream=args.decision_stream,
        pending_stream=args.pending_stream,
        dead_letter_stream=args.dead_letter_stream,
        redis_scan_limit=args.redis_scan_limit,
    )
    write_json(Path(args.out), result)
    print(result["counts"])


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
