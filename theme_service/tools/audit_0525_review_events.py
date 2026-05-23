from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database_service.streams.services.review_eligibility import should_enter_human_review


def _database_dsn(db_name: str | None) -> str:
    raw = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if raw:
        return raw
    db = db_name or os.getenv("PG_DATABASE") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DATABASE") or "stock_data_test"
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or "postgres"
    password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or "127.0.0.1"
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _md(value: Any, limit: int = 160) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")[:limit]


async def _load_review_rows(conn: asyncpg.Connection, trade_date: date, limit: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            q.id AS review_id,
            q.event_id,
            COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('待复核事件#' || q.event_id::text)) AS title,
            COALESCE(ne.summary, nr.content, q.reason, '') AS summary,
            q.reason,
            q.source_channel,
            q.proposed_theme_name AS theme_name,
            q.proposed_theme_confidence AS confidence,
            q.created_at
        FROM event_review_queue q
        LEFT JOIN news_event ne ON ne.id = q.event_id
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE q.review_status = 'waiting'
          AND (
            ne.created_at::date = $1::date
            OR nr.publish_date::date = $1::date
            OR q.created_at::date = $1::date
          )
        ORDER BY q.created_at DESC
        LIMIT $2
        """,
        trade_date,
        int(limit),
    )
    return [dict(row) for row in rows]


async def _load_snapshot_review_rows(conn: asyncpg.Connection, trade_date: date, limit: int) -> list[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT payload
        FROM pre_market_brief_snapshot
        WHERE trade_date = $1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        trade_date,
    )
    if not row:
        return []
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    sections = payload.get("sections") if isinstance(payload, dict) else {}
    review_events = sections.get("review_events") if isinstance(sections, dict) else []
    if not isinstance(review_events, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in review_events[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "review_id": item.get("review_id") or item.get("id"),
                "event_id": item.get("event_id"),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "reason": item.get("reason") or item.get("reason_code"),
                "source_channel": item.get("source_channel"),
                "theme_name": item.get("theme_name") or item.get("proposed_theme_name"),
                "confidence": item.get("confidence") or item.get("proposed_theme_confidence"),
                "created_at": item.get("occurred_at") or item.get("created_at"),
                "triage_result": item.get("triage_result"),
                "runtime_source": item.get("runtime_source"),
                "match_reason": item.get("match_reason"),
            }
        )
    return rows


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    match_result = {
        "reason_code": row.get("reason"),
        "runtime_source": row.get("runtime_source"),
        "match_reason": row.get("match_reason"),
        "confidence": row.get("confidence"),
    }
    triage_result = row.get("triage_result") if isinstance(row.get("triage_result"), dict) else {}
    eligibility = should_enter_human_review(row, match_result, triage_result)
    return {
        "review_id": row.get("review_id"),
        "event_id": row.get("event_id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "reason_code": row.get("reason"),
        "runtime_source": row.get("runtime_source") or "",
        "match_reason": row.get("match_reason") or "",
        "triage_decision": triage_result.get("decision") or "",
        "importance_level": triage_result.get("importance_level") or "",
        "event_value_type": triage_result.get("event_value_type") or "",
        "evidence": triage_result.get("evidence") or [],
        "theme_name": row.get("theme_name"),
        "confidence": float(row.get("confidence") or 0),
        "source_channel": row.get("source_channel"),
        "created_at": row.get("created_at"),
        "should_keep_review": bool(eligibility.get("should_keep_review")),
        "drop_reason": eligibility.get("drop_reason") or "",
        "suggested_action": eligibility.get("suggested_action") or "keep_review",
        "eligibility_reason_code": eligibility.get("reason_code") or "",
    }


def _write_outputs(out_dir: Path, rows: list[dict[str, Any]], apply: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "review_99_attribution.jsonl"
    md_path = out_dir / "review_99_attribution.md"
    jsonl_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    action_counts = Counter(str(row["suggested_action"]) for row in rows)
    reason_counts = Counter(str(row["eligibility_reason_code"]) for row in rows)
    keep = sum(1 for row in rows if row["should_keep_review"])
    lines = [
        "# 5/25 Review Eligibility Audit",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- apply: `{str(apply).lower()}`",
        f"- total_review_rows: {len(rows)}",
        f"- keep_review: {keep}",
        f"- drop_or_archive: {len(rows) - keep}",
        "",
        "## Suggested Actions",
    ]
    for key, value in action_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Reason Codes"])
    for key, value in reason_counts.most_common(20):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Detail",
            "",
            "| event_id | keep | action | reason | theme | title |",
            "|---:|---:|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('event_id')} | {str(row.get('should_keep_review')).lower()} | "
            f"{_md(row.get('suggested_action'), 40)} | {_md(row.get('eligibility_reason_code'), 60)} | "
            f"{_md(row.get('theme_name'), 80)} | {_md(row.get('title'), 180)} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _apply_drop(conn: asyncpg.Connection, rows: list[dict[str, Any]], run_id: str) -> int:
    ids = [int(row["review_id"]) for row in rows if row.get("review_id") and not row.get("should_keep_review")]
    event_ids = [int(row["event_id"]) for row in rows if row.get("event_id") and not row.get("should_keep_review")]
    if not ids and not event_ids:
        return 0
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_review_queue_phase3b_backup AS
        SELECT *, NULL::text AS backup_run_id, NULL::timestamptz AS backup_at
        FROM event_review_queue
        WHERE false
        """
    )
    await conn.execute(
        """
        INSERT INTO event_review_queue_phase3b_backup
        SELECT q.*, $2::text AS backup_run_id, NOW() AS backup_at
        FROM event_review_queue q
        WHERE (q.id = ANY($1::bigint[]) OR q.event_id = ANY($3::bigint[]))
        ON CONFLICT DO NOTHING
        """,
        ids,
        run_id,
        event_ids,
    )
    result = await conn.execute(
        """
        UPDATE event_review_queue
        SET review_status = 'dropped',
            reviewed_at = NOW(),
            review_note = $2
        WHERE (id = ANY($1::bigint[]) OR event_id = ANY($3::bigint[]))
          AND review_status = 'waiting'
        """,
        ids,
        f"phase3b_review_ineligible_dropped:{run_id}",
        event_ids,
    )
    return int(result.split()[-1]) if result else 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and optionally drop ineligible 5/25 review queue events.")
    parser.add_argument("--trade-date", default="2026-05-25")
    parser.add_argument("--out-dir", default="tmp/product_runtime_0525_review_audit")
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--source", choices=["snapshot", "queue"], default="snapshot")
    parser.add_argument("--run-id", default="phase3b_review_eligibility_20260525")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date)
    conn = await asyncpg.connect(_database_dsn(args.db_name))
    try:
        raw_rows = (
            await _load_snapshot_review_rows(conn, trade_date, args.limit)
            if args.source == "snapshot"
            else await _load_review_rows(conn, trade_date, args.limit)
        )
        rows = [_classify(row) for row in raw_rows]
        if args.apply:
            changed = await _apply_drop(conn, rows, args.run_id)
            rows.append(
                {
                    "event_id": "",
                    "title": "__APPLY_RESULT__",
                    "should_keep_review": True,
                    "suggested_action": "apply_result",
                    "eligibility_reason_code": f"dropped_rows={changed}",
                }
            )
        _write_outputs(Path(args.out_dir), rows, args.apply)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
