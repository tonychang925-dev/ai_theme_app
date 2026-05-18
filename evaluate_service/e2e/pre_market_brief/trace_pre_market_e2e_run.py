from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import (
        column_exists,
        db_connect_kwargs,
        parse_trade_date,
        read_jsonl,
        require_safe_db,
        table_exists,
        write_json,
    )
else:
    from .common import column_exists, db_connect_kwargs, parse_trade_date, read_jsonl, require_safe_db, table_exists, write_json


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

        rows = [
            dict(row)
            for row in await conn.fetch(
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
        ]
        rows = await _attach_orphan_news_events(conn, rows, trade_date)
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
        match_performance = _extract_mapping_performance(primary)
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
                "related_mappings": event_mappings[1:],
                "review_status": reviews.get(int(event_id), {}).get("review_status") if event_id is not None else None,
                "review_reason": reviews.get(int(event_id), {}).get("reason") if event_id is not None else None,
                "pending_status": None,
                "dead_letter_status": None,
                "match_performance": match_performance,
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
    decision_by_event_id = {
        str(item.get("event_id")): item
        for item in redis_trace.get("decision_entries", [])
        if item.get("event_id") is not None
    }
    for row in trace_rows:
        decision_entry = decision_by_event_id.get(str(row.get("news_event_id")))
        if not decision_entry:
            continue
        row["decision_id"] = decision_entry.get("stream_id")
        if not row.get("match_performance"):
            row["match_performance"] = decision_entry.get("match_performance") or {}
        if not row.get("review_reason") and decision_entry.get("reason_code"):
            row["review_reason"] = decision_entry.get("reason_code")
    counts = {
        "expected_input_count": len(expected),
        "news_raw_count": len({row["news_raw_id"] for row in rows}),
        "news_event_count": len({row["news_event_id"] for row in rows if row["news_event_id"] is not None}),
        "mapped_event_count": len(mappings),
        "event_subject_map_count": sum(len(items) for items in mappings.values()),
        "event_theme_map_count": sum(len(items) for items in mappings.values()),
        "review_queue_count": len(reviews),
        "decision_count": redis_trace["decision_count"],
        "pending_count": redis_trace["pending_count"],
        "dead_letter_count": redis_trace["dead_letter_count"],
    }
    counts.update(_aggregate_match_performance(trace_rows))
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
    if not event_ids:
        return {}
    if await table_exists(conn, "event_subject_map"):
        has_legacy_reason = await column_exists(conn, "event_subject_map", "reason")
        reason_expr = "COALESCE(match_reason, reason)" if has_legacy_reason else "match_reason"
        rows = await conn.fetch(
            f"""
            SELECT
              event_id,
              subject_key,
              COALESCE(NULLIF(subject_name, ''), subject_key) AS theme_name,
              confidence,
              {reason_expr} AS match_reason,
              relation_type,
              evidence_json,
              created_at
            FROM event_subject_map
            WHERE event_id = ANY($1::int[])
            ORDER BY event_id,
                     CASE relation_type WHEN 'primary' THEN 0 ELSE 1 END,
                     confidence DESC NULLS LAST,
                     created_at ASC
            """,
            event_ids,
        )
        result: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(int(row["event_id"]), []).append(dict(row))
        return result

    if not await table_exists(conn, "event_theme_map"):
        return {}
    has_match_reason = await column_exists(conn, "event_theme_map", "match_reason")
    match_reason_expr = "etm.match_reason" if has_match_reason else "NULL::text AS match_reason"
    rows = await conn.fetch(
        f"""
        SELECT
          etm.event_id,
          COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) AS subject_key,
          tm.name AS theme_name,
          etm.confidence,
          {match_reason_expr},
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


async def _attach_orphan_news_events(
    conn: Any,
    rows: list[dict[str, Any]],
    trade_date: str,
) -> list[dict[str, Any]]:
    """兼容旧结构化链路：news_event.news_id 为空时按本轮 raw 创建窗口归因。"""
    missing = [row for row in rows if row.get("news_event_id") is None]
    if not rows or not missing or not await table_exists(conn, "news_event"):
        return rows

    raw_times = [row.get("raw_created_at") for row in rows if row.get("raw_created_at") is not None]
    if not raw_times:
        return rows

    event_rows = await conn.fetch(
        """
        SELECT id AS news_event_id, created_at AS event_created_at
        FROM news_event
        WHERE news_id IS NULL
          AND created_at >= $1::timestamptz - interval '30 seconds'
          AND created_at <= $2::timestamptz + interval '20 minutes'
          AND created_at::date = $3::date
        ORDER BY created_at ASC, id ASC
        LIMIT $4
        """,
        min(raw_times),
        max(raw_times),
        parse_trade_date(trade_date),
        len(rows),
    )
    if not event_rows:
        return rows

    orphan_events = [dict(row) for row in event_rows]
    event_iter = iter(orphan_events)
    patched: list[dict[str, Any]] = []
    for row in rows:
        patched_row = dict(row)
        if patched_row.get("news_event_id") is None:
            event = next(event_iter, None)
            if event:
                patched_row["news_event_id"] = event["news_event_id"]
                patched_row["event_created_at"] = event["event_created_at"]
                patched_row["event_inferred_by"] = "raw_created_at_window"
        patched.append(patched_row)
    return patched


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


def _extract_mapping_performance(mapping: dict[str, Any]) -> dict[str, Any]:
    evidence = mapping.get("evidence_json") if isinstance(mapping, dict) else {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    if not isinstance(evidence, dict):
        return {}
    audit = evidence.get("audit") if isinstance(evidence.get("audit"), dict) else {}
    performance = audit.get("performance") if isinstance(audit.get("performance"), dict) else {}
    return performance if isinstance(performance, dict) else {}


def _aggregate_match_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: list[float] = []
    llm_judge_count = 0
    event_profile_llm_count = 0
    query_hit_count = 0
    query_miss_count = 0
    rerank_hit_count = 0
    rerank_miss_count = 0
    profile_cache_stats: dict[str, int] = {}
    for row in rows:
        perf = row.get("match_performance") if isinstance(row.get("match_performance"), dict) else {}
        timing = perf.get("timing_ms") if isinstance(perf.get("timing_ms"), dict) else {}
        total_ms = timing.get("total_match_ms")
        if total_ms is not None:
            try:
                totals.append(float(total_ms))
            except (TypeError, ValueError):
                pass
        counters = perf.get("counters") if isinstance(perf.get("counters"), dict) else {}
        llm_judge_count += int(counters.get("llm_judge_count") or 0)
        event_profile_llm_count += int(counters.get("event_profile_llm_count") or 0)
        query_hit_count += int(counters.get("query_vector_cache_hit_count") or 0)
        query_miss_count += int(counters.get("query_vector_cache_miss_count") or 0)
        rerank_hit_count += int(counters.get("rerank_doc_vector_cache_hit_count") or 0)
        rerank_miss_count += int(counters.get("rerank_doc_vector_cache_miss_count") or 0)
        cache_stats = perf.get("profile_cache_stats") if isinstance(perf.get("profile_cache_stats"), dict) else {}
        for key, value in cache_stats.items():
            try:
                profile_cache_stats[key] = max(profile_cache_stats.get(key, 0), int(value or 0))
            except (TypeError, ValueError):
                continue

    totals.sort()
    out: dict[str, Any] = {
        "match_timing_sample_count": len(totals),
        "llm_judge_count": llm_judge_count,
        "event_profile_llm_count": event_profile_llm_count,
        "query_vector_cache_hit_count": query_hit_count,
        "query_vector_cache_miss_count": query_miss_count,
        "rerank_doc_vector_cache_hit_count": rerank_hit_count,
        "rerank_doc_vector_cache_miss_count": rerank_miss_count,
    }
    out.update(profile_cache_stats)
    if not totals:
        return out
    out.update(
        {
            "avg_match_ms": round(sum(totals) / len(totals), 3),
            "p50_match_ms": round(_percentile(totals, 0.50), 3),
            "p95_match_ms": round(_percentile(totals, 0.95), 3),
        }
    )
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * pct))))
    return values[idx]


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
                **_extract_decision_payload_trace(fields),
            }
        )
    return list(reversed(matched))


def _first_matching_field(fields: dict[str, Any], *names: str) -> str | None:
    for name in names:
        if fields.get(name):
            return str(fields[name])
    return None


def _extract_decision_payload_trace(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("decision")
    if not raw:
        return {}
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    match_result = payload.get("match_result") if isinstance(payload.get("match_result"), dict) else {}
    audit = match_result.get("audit") if isinstance(match_result.get("audit"), dict) else {}
    return {
        "action": payload.get("action"),
        "reason_code": match_result.get("reason_code") or payload.get("reason"),
        "match_performance": audit.get("performance") if isinstance(audit.get("performance"), dict) else {},
    }


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
