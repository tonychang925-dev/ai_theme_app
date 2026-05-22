from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import connect, run_async

LOW_VALUE_TERMS = (
    "减持",
    "回购",
    "澄清",
    "交易监管",
    "异常波动",
    "问询函",
    "关注函",
    "天气预警",
    "山洪",
    "暴雨",
    "地震",
    "列车停运",
    "第一季度",
    "一季度",
    "Q1",
    "营收",
    "净利润",
    "无注入",
    "风险提示",
    "监管要求",
    "非法销售风险",
)

OLD_HIGH_NOISE_SUBJECT_KEYS = {
    "9053827",
    "9050084",
    "9022889",
    "9034544",
    "9024042",
    "9034920",
    "9051378",
    "9059230",
    "9020124",
    "9023110",
    "9013587",
}

PHASE2B_SUBJECT_KEYS = {"9050659", "9020774", "9028660", "9059277", "9033890"}


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _as_json(value: Any, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _contains_low_value(text: str) -> bool:
    return any(term in text for term in LOW_VALUE_TERMS)


def _md(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")[:240]


def _match_rows_from_replay(rows: list[dict[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("new_decision") != "MATCH" or not row.get("new_subject_key"):
            continue
        evidence = {
            "best_evidence": row.get("best_evidence") or {},
            "accepted_anchor_hits": row.get("accepted_anchor_hits") or [],
            "direct_hit_terms": row.get("direct_hit_terms") or [],
            "llm_accept_blocked": bool(row.get("llm_accept_blocked")),
            "low_value_blocked": bool(row.get("low_value_blocked")),
            "replay_trace": {
                "source": "tmp/product_runtime_0522_phase2e/replay_runtime_auto_final",
                "event_id": row.get("event_id"),
                "new_reason_code": row.get("new_reason_code"),
                "runtime_source": row.get("runtime_source"),
                "assessment": row.get("assessment"),
            },
            "old_subject_key": row.get("old_subject_key") or "",
            "old_theme_name": row.get("old_theme_name") or "",
            "old_confidence": row.get("old_confidence"),
            "new_reason_code": row.get("new_reason_code") or "",
        }
        out.append(
            {
                "event_id": int(row["event_id"]),
                "news_id": int(row["news_id"]) if row.get("news_id") is not None else None,
                "subject_key": str(row.get("new_subject_key") or ""),
                "subject_name": str(row.get("new_theme_name") or ""),
                "confidence": float(row.get("new_confidence") or 0.0),
                "match_reason": str(row.get("new_match_reason") or row.get("new_reason_code") or ""),
                "evidence_json": evidence,
                "run_id": run_id,
            }
        )
    return out


async def _ensure_backup_table(conn: Any) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_subject_map_replace_backup AS
        SELECT * FROM event_subject_map WHERE false
        """
    )
    await conn.execute("ALTER TABLE event_subject_map_replace_backup ADD COLUMN IF NOT EXISTS backup_run_id text")
    await conn.execute("ALTER TABLE event_subject_map_replace_backup ADD COLUMN IF NOT EXISTS backup_reason text")
    await conn.execute("ALTER TABLE event_subject_map_replace_backup ADD COLUMN IF NOT EXISTS backup_at timestamptz")


async def _apply_replace(conn: Any, args: argparse.Namespace, replay_rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_ids = sorted({int(row["event_id"]) for row in replay_rows if row.get("event_id")})
    match_rows = _match_rows_from_replay(replay_rows, run_id=args.run_id)
    await _ensure_backup_table(conn)
    async with conn.transaction():
        backup_count = await conn.fetchval(
            """
            WITH inserted AS (
                INSERT INTO event_subject_map_replace_backup (
                    id, event_id, subject_key, subject_name, confidence, confidence_level, confidence_weight,
                    evidence_json, relation_type, source_channel, reason, matched_keywords, created_at,
                    updated_at, news_id, match_reason, source, source_trace_id, run_id,
                    backup_run_id, backup_reason, backup_at
                )
                SELECT
                    id, event_id, subject_key, subject_name, confidence, confidence_level, confidence_weight,
                    evidence_json, relation_type, source_channel, reason, matched_keywords, created_at,
                    updated_at, news_id, match_reason, source, source_trace_id, run_id,
                    $2, 'phase2e_replace_20260522', now()
                FROM event_subject_map
                WHERE event_id = ANY($1::bigint[])
                  AND NOT EXISTS (
                      SELECT 1 FROM event_subject_map_replace_backup b
                      WHERE b.backup_run_id = $2 AND b.id = event_subject_map.id
                  )
                RETURNING 1
            )
            SELECT count(*) FROM inserted
            """,
            event_ids,
            args.run_id,
        )
        deleted_count = await conn.fetchval(
            """
            WITH deleted AS (
                DELETE FROM event_subject_map
                WHERE event_id = ANY($1::bigint[])
                RETURNING 1
            )
            SELECT count(*) FROM deleted
            """,
            event_ids,
        )
        inserted_count = 0
        for row in match_rows:
            await conn.execute(
                """
                INSERT INTO event_subject_map (
                    event_id, subject_key, subject_name, confidence, confidence_level, confidence_weight,
                    evidence_json, relation_type, source_channel, reason, matched_keywords, created_at,
                    updated_at, news_id, match_reason, source, source_trace_id, run_id
                )
                VALUES (
                    $1, $2, $3, $4, 'high', 100,
                    $5::jsonb, 'primary', 'phase2e_replace', $6, ARRAY[]::text[], now(),
                    now(), $7, $6, 'product_runtime_phase2e_replace', $8, $9
                )
                ON CONFLICT (event_id, subject_key, relation_type) DO UPDATE SET
                    subject_name = EXCLUDED.subject_name,
                    confidence = EXCLUDED.confidence,
                    confidence_level = EXCLUDED.confidence_level,
                    confidence_weight = EXCLUDED.confidence_weight,
                    evidence_json = EXCLUDED.evidence_json,
                    source_channel = EXCLUDED.source_channel,
                    reason = EXCLUDED.reason,
                    updated_at = now(),
                    news_id = EXCLUDED.news_id,
                    match_reason = EXCLUDED.match_reason,
                    source = EXCLUDED.source,
                    source_trace_id = EXCLUDED.source_trace_id,
                    run_id = EXCLUDED.run_id
                """,
                row["event_id"],
                row["subject_key"],
                row["subject_name"],
                row["confidence"],
                json.dumps(row["evidence_json"], ensure_ascii=False),
                row["match_reason"],
                row["news_id"],
                f"phase2e_replace:{row['event_id']}:{row['subject_key']}",
                row["run_id"],
            )
            inserted_count += 1
    return {
        "replay_event_count": len(event_ids),
        "match_rows_in_replay": len(match_rows),
        "backup_row_count": int(backup_count or 0),
        "deleted_row_count": int(deleted_count or 0),
        "inserted_match_count": inserted_count,
    }


async def _rollback(conn: Any, args: argparse.Namespace) -> dict[str, Any]:
    await _ensure_backup_table(conn)
    event_ids = await conn.fetch(
        "SELECT DISTINCT event_id FROM event_subject_map_replace_backup WHERE backup_run_id = $1 ORDER BY event_id",
        args.run_id,
    )
    ids = [int(row["event_id"]) for row in event_ids]
    async with conn.transaction():
        deleted_count = await conn.fetchval(
            """
            WITH deleted AS (
                DELETE FROM event_subject_map
                WHERE source = 'product_runtime_phase2e_replace'
                  AND run_id = $1
                RETURNING 1
            )
            SELECT count(*) FROM deleted
            """,
            args.run_id,
        )
        restored_count = await conn.fetchval(
            """
            WITH restored AS (
                INSERT INTO event_subject_map (
                    id, event_id, subject_key, subject_name, confidence, confidence_level, confidence_weight,
                    evidence_json, relation_type, source_channel, reason, matched_keywords, created_at,
                    updated_at, news_id, match_reason, source, source_trace_id, run_id
                )
                SELECT
                    id, event_id, subject_key, subject_name, confidence, confidence_level, confidence_weight,
                    evidence_json, relation_type, source_channel, reason, matched_keywords, created_at,
                    updated_at, news_id, match_reason, source, source_trace_id, run_id
                FROM event_subject_map_replace_backup
                WHERE backup_run_id = $1
                ON CONFLICT (event_id, subject_key, relation_type) DO NOTHING
                RETURNING 1
            )
            SELECT count(*) FROM restored
            """,
            args.run_id,
        )
    return {"rollback_event_count": len(ids), "deleted_replace_count": int(deleted_count or 0), "restored_row_count": int(restored_count or 0)}


async def _load_snapshot(conn: Any, trade_date: date) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT trade_date, status, updated_at, payload
        FROM pre_market_brief_snapshot
        WHERE trade_date = $1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        trade_date,
    )
    return dict(row) if row else {}


async def _post_report(
    conn: Any,
    *,
    trade_date: date,
    run_id: str,
    replay_rows: list[dict[str, Any]],
    out_dir: Path,
    operation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    event_ids = sorted({int(row["event_id"]) for row in replay_rows if row.get("event_id")})
    quarantine_by_event: dict[int, set[str]] = defaultdict(set)
    for row in replay_rows:
        for item in row.get("quarantine_matches") or []:
            if item.get("subject_key"):
                quarantine_by_event[int(row["event_id"])].add(str(item["subject_key"]))
    active_rows = await conn.fetch(
        """
        SELECT
            esm.event_id,
            esm.news_id,
            esm.subject_key,
            esm.subject_name,
            esm.confidence,
            esm.relation_type,
            esm.match_reason,
            esm.source,
            esm.source_channel,
            esm.run_id,
            esm.evidence_json,
            COALESCE(NULLIF(nr.title, ''), ne.raw_event_json->>'title', NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(NULLIF(ne.summary, ''), ne.raw_event_json->>'summary', nr.content, '') AS summary
        FROM event_subject_map esm
        JOIN news_event ne ON ne.id = esm.event_id
        LEFT JOIN news_raw nr ON nr.id = COALESCE(esm.news_id, ne.news_id)
        WHERE esm.event_id = ANY($1::bigint[])
        ORDER BY esm.event_id, esm.confidence DESC NULLS LAST
        """,
        event_ids,
    )
    details = [dict(row) for row in active_rows]
    snapshot = await _load_snapshot(conn, trade_date)
    payload = _as_json(snapshot.get("payload"))
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    major_events = sections.get("major_events") if isinstance(sections.get("major_events"), list) else []
    matched_themes = sections.get("matched_themes") if isinstance(sections.get("matched_themes"), list) else []
    primary_counts = Counter(int(row["event_id"]) for row in details if str(row.get("relation_type") or "") == "primary")
    duplicate_primary = sum(1 for count in primary_counts.values() if count > 1)
    low_value_major = sum(1 for row in major_events if _contains_low_value(f"{row.get('title') or ''} {row.get('summary') or ''}"))
    quarantine_residual = 0
    for row in details:
        if str(row.get("subject_key") or "") in quarantine_by_event.get(int(row["event_id"]), set()):
            quarantine_residual += 1
    product_runtime_debug_source_residual = sum(
        1
        for row in major_events
        if str(row.get("source_channel") or "").startswith("product_runtime_")
        or str(row.get("source_type") or "").startswith("product_runtime_")
    )
    old_high_noise_residual = sum(1 for row in details if str(row.get("subject_key") or "") in OLD_HIGH_NOISE_SUBJECT_KEYS)
    phase2b_residual = sum(1 for row in details if str(row.get("subject_key") or "") in PHASE2B_SUBJECT_KEYS)
    suspicious = [
        row
        for row in details
        if _contains_low_value(f"{row.get('title') or ''} {row.get('summary') or ''}")
        or str(row.get("subject_key") or "") in quarantine_by_event.get(int(row["event_id"]), set())
    ]
    metrics = {
        **(operation or {}),
        "active_replaced_event_count": len({int(row["event_id"]) for row in details if row.get("run_id") == run_id}),
        "inserted_match_count": sum(1 for row in details if row.get("run_id") == run_id),
        "backup_row_count_total": int(await conn.fetchval("SELECT count(*) FROM event_subject_map_replace_backup WHERE backup_run_id = $1", run_id) or 0),
        "duplicate_primary_count": duplicate_primary,
        "snapshot_low_value_major_count": low_value_major,
        "suspicious_match_count": len(suspicious),
        "quarantine_old_wrong_residual_count": quarantine_residual,
        "old_high_noise_residual_count": old_high_noise_residual,
        "phase2b_subject_residual_count": phase2b_residual,
        "product_runtime_debug_source_residual_count": product_runtime_debug_source_residual,
        "major_events": len(major_events),
        "matched_themes": len(matched_themes),
    }
    detail_rows = [
        {
            "event_id": int(row["event_id"]),
            "title": row.get("title") or "",
            "subject_key": row.get("subject_key") or "",
            "subject_name": row.get("subject_name") or "",
            "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
            "match_reason": row.get("match_reason") or "",
            "source": row.get("source") or "",
            "source_channel": row.get("source_channel") or "",
            "run_id": row.get("run_id") or "",
            "is_low_value_event": _contains_low_value(f"{row.get('title') or ''} {row.get('summary') or ''}"),
            "is_quarantine_residual": str(row.get("subject_key") or "") in quarantine_by_event.get(int(row["event_id"]), set()),
        }
        for row in details
    ]
    (out_dir / "post_replace_detail.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in detail_rows) + ("\n" if detail_rows else ""),
        encoding="utf-8",
    )
    lines = ["# Phase 2E Replace Mode Post Report", ""]
    lines.extend(f"- {key}: {value}" for key, value in metrics.items())
    lines.extend(["", "## Suspicious Active Rows", "", "| event_id | subject | source | title |", "|---|---|---|---|"])
    for row in detail_rows:
        if row["is_low_value_event"] or row["is_quarantine_residual"]:
            lines.append(f"| {row['event_id']} | {row['subject_key']} {_md(row['subject_name'])} | {_md(row['source'])}/{_md(row['source_channel'])} | {_md(row['title'])} |")
    (out_dir / "post_replace_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metrics


def _str_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.lower() in {"1", "true", "yes", "on"}


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Apply or rollback 2026-05-22 Phase 2E replay replace mode.")
    parser.add_argument("--db-name", default="stock_data_test")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--replay-detail", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/product_runtime_0522_phase2e_replace"))
    args = parser.parse_args()

    replay_rows = _load_jsonl(args.replay_detail)
    trade_date = date.fromisoformat(args.trade_date)
    conn = await connect(args.db_name)
    try:
        if args.report_only:
            result = await _post_report(conn, trade_date=trade_date, run_id=args.run_id, replay_rows=replay_rows, out_dir=args.out_dir)
        elif args.rollback:
            if _str_bool(args.dry_run):
                result = {"dry_run": True, "rollback_event_count": len({row.get("event_id") for row in replay_rows})}
            else:
                operation = await _rollback(conn, args)
                result = await _post_report(conn, trade_date=trade_date, run_id=args.run_id, replay_rows=replay_rows, out_dir=args.out_dir, operation=operation)
        else:
            if _str_bool(args.dry_run):
                match_rows = _match_rows_from_replay(replay_rows, run_id=args.run_id)
                result = {
                    "dry_run": True,
                    "replay_event_count": len({row.get("event_id") for row in replay_rows}),
                    "match_rows_in_replay": len(match_rows),
                }
            else:
                operation = await _apply_replace(conn, args, replay_rows)
                result = await _post_report(conn, trade_date=trade_date, run_id=args.run_id, replay_rows=replay_rows, out_dir=args.out_dir, operation=operation)
    finally:
        await conn.close()
    print(json.dumps(result, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    run_async(_main())
