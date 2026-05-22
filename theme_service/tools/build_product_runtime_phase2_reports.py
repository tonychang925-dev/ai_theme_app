from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import connect, run_async

CN_TZ = ZoneInfo("Asia/Shanghai")
LOW_VALUE_TERMS = (
    "减持",
    "回购",
    "澄清",
    "交易监管",
    "天气预警",
    "山洪",
    "地震灾害",
    "列车停运",
    "旅客列车停",
    "任命",
    "季度财报",
    "发布财报",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _as_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _list_value(evidence: dict[str, Any], *keys: str) -> list[str]:
    result: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value if item not in (None, ""))
        elif isinstance(value, str) and value:
            result.append(value)
    return list(dict.fromkeys(result))


def _window(trade_date: date) -> tuple[datetime, datetime]:
    end_at = datetime.combine(trade_date, datetime.min.time(), tzinfo=CN_TZ).replace(hour=8)
    start_at = end_at.replace(day=end_at.day)  # keep zoneinfo normalization local
    start_at = datetime.fromtimestamp(end_at.timestamp() - 17 * 3600, tz=CN_TZ)
    return start_at, end_at


async def _load_rows(conn: Any, trade_date: date, limit: int) -> list[dict[str, Any]]:
    start_at, end_at = _window(trade_date)
    rows = await conn.fetch(
        """
        WITH active_v2 AS (
            SELECT subject_key FROM theme_profile_v2 WHERE status = 'accepted_candidate'
        ),
        mapped AS (
            SELECT
                esm.id,
                esm.event_id,
                esm.subject_key,
                COALESCE(NULLIF(esm.subject_name, ''), t.concept, v2.subject_name, esm.subject_key) AS matched_theme_name,
                esm.confidence,
                esm.match_reason,
                esm.evidence_json,
                esm.matched_keywords,
                esm.relation_type,
                esm.created_at,
                esm.updated_at,
                COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
                COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
                COALESCE(ne.summary, nr.content, '') AS summary,
                CASE WHEN av.subject_key IS NOT NULL THEN 'v2_accepted' ELSE 'v1_fallback' END AS runtime_source,
                ROW_NUMBER() OVER (
                    PARTITION BY esm.event_id
                    ORDER BY CASE WHEN esm.relation_type = 'primary' THEN 0 ELSE 1 END,
                             esm.confidence DESC NULLS LAST,
                             esm.updated_at DESC NULLS LAST
                ) AS event_rank
            FROM event_subject_map esm
            JOIN news_event ne ON ne.id = esm.event_id
            LEFT JOIN news_raw nr ON nr.id = COALESCE(esm.news_id, ne.news_id)
            LEFT JOIN theme_gate_profile t ON t.subject_key = esm.subject_key
            LEFT JOIN theme_profile_v2 v2 ON v2.subject_key = esm.subject_key AND v2.status = 'accepted_candidate'
            LEFT JOIN active_v2 av ON av.subject_key = esm.subject_key
            WHERE COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
              AND COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
        )
        SELECT * FROM mapped
        ORDER BY occurred_at DESC NULLS LAST, event_id DESC, event_rank
        LIMIT $3
        """,
        start_at,
        end_at,
        limit,
    )
    return [dict(row) for row in rows]


def _attribution_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_json(row.get("evidence_json"))
    matched_keywords = [str(item) for item in row.get("matched_keywords") or [] if item]
    direct_hit_terms = _list_value(evidence, "direct_hit_terms", "direct_hits", "direct_theme_name_hits")
    if row.get("match_reason") == "direct_theme_name_hit" and not direct_hit_terms:
        direct_hit_terms = matched_keywords
    accepted_anchor_hits = _list_value(evidence, "accepted_anchor_hits", "anchor_hits", "must_hits", "strong_hits")
    no_anchor_hits = _list_value(evidence, "no_anchor_hits", "weak_hits")
    negative_hits = _list_value(evidence, "negative_hits", "not_hits", "reject_hits")
    text = f"{row.get('title') or ''} {row.get('summary') or ''}"
    is_low_value = any(term in text for term in LOW_VALUE_TERMS)
    is_duplicate = int(row.get("event_rank") or 0) > 1
    match_reason = str(row.get("match_reason") or "")
    runtime_source = str(row.get("runtime_source") or "")

    auto_label = "review"
    root_cause = "needs_manual_review"
    suggested_fix = "manual_review"
    if is_low_value:
        auto_label, root_cause, suggested_fix = "low_value", "display_layer", "keep_out_of_major_events"
    elif is_duplicate:
        auto_label, root_cause, suggested_fix = "duplicate", "display_layer", "primary_only"
    elif runtime_source == "v1_fallback" and match_reason == "direct_theme_name_hit":
        auto_label, root_cause, suggested_fix = "review", "direct_hit_over_accept", "audit_direct_hit_or_add_v2_profile"
    elif runtime_source == "v1_fallback":
        auto_label, root_cause, suggested_fix = "review", "bad_v1_fallback", "repair_source_gate_to_v2"
    elif match_reason == "direct_theme_name_hit":
        auto_label, root_cause, suggested_fix = "review", "direct_hit_over_accept", "check_accept_requires_any"
    elif match_reason == "llm_accept_match" and not accepted_anchor_hits:
        auto_label, root_cause, suggested_fix = "review", "llm_accept_weak_evidence", "add_anchor_or_llm_veto"

    return {
        "event_id": row.get("event_id"),
        "title": row.get("title") or "",
        "summary": row.get("summary") or "",
        "matched_subject_key": row.get("subject_key") or "",
        "matched_theme_name": row.get("matched_theme_name") or "",
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "match_reason": match_reason,
        "runtime_source": runtime_source,
        "best_evidence": evidence,
        "direct_hit_terms": direct_hit_terms,
        "accepted_anchor_hits": accepted_anchor_hits,
        "no_anchor_hits": no_anchor_hits,
        "negative_hits": negative_hits,
        "is_low_value_event": is_low_value,
        "is_duplicate_primary": is_duplicate,
        "manual_label": "",
        "auto_label": auto_label,
        "root_cause": root_cause,
        "suggested_fix": suggested_fix,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_attribution_md(path: Path, rows: list[dict[str, Any]], trade_date: date) -> None:
    labels = Counter(row["auto_label"] for row in rows)
    roots = Counter(row["root_cause"] for row in rows)
    lines = [
        "# Product Runtime Phase 2 Match Attribution",
        "",
        f"- trade_date: {trade_date.isoformat()}",
        f"- mapped_rows: {len(rows)}",
        f"- low_value_rows: {labels.get('low_value', 0)}",
        f"- duplicate_rows: {labels.get('duplicate', 0)}",
        f"- v1_fallback_rows: {sum(row['runtime_source'] == 'v1_fallback' for row in rows)}",
        f"- direct_theme_name_hit_rows: {sum(row['match_reason'] == 'direct_theme_name_hit' for row in rows)}",
        "",
        "## Root Cause Counts",
        "",
    ]
    lines.extend(f"- {root}: {count}" for root, count in roots.most_common())
    lines.extend(["", "## Priority Rows", "", "| event_id | subject | reason | source | title | suggested_fix |", "|---|---|---|---|---|---|"])
    for row in rows[:120]:
        title = str(row["title"]).replace("|", "/")
        lines.append(
            f"| {row['event_id']} | {row['matched_subject_key']} {row['matched_theme_name']} | "
            f"{row['match_reason']} | {row['runtime_source']} | {title} | {row['suggested_fix']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _direct_hit_rows(conn: Any, trade_date: date) -> list[dict[str, Any]]:
    start_at, end_at = _window(trade_date)
    rows = await conn.fetch(
        """
        SELECT
            esm.subject_key,
            COALESCE(NULLIF(esm.subject_name, ''), g.concept, v2.subject_name, esm.subject_key) AS subject_name,
            CASE WHEN v2.subject_key IS NOT NULL THEN 'v2_accepted' ELSE 'v1_fallback' END AS runtime_source,
            COUNT(*) AS n,
            COUNT(*) FILTER (WHERE esm.confidence < 0.90) AS low_conf_n,
            MIN(esm.confidence) AS min_conf,
            MAX(esm.confidence) AS max_conf
        FROM event_subject_map esm
        JOIN news_event ne ON ne.id = esm.event_id
        LEFT JOIN news_raw nr ON nr.id = COALESCE(esm.news_id, ne.news_id)
        LEFT JOIN theme_gate_profile g ON g.subject_key = esm.subject_key
        LEFT JOIN theme_profile_v2 v2 ON v2.subject_key = esm.subject_key AND v2.status = 'accepted_candidate'
        WHERE esm.match_reason = 'direct_theme_name_hit'
          AND COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
          AND COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
        GROUP BY esm.subject_key, COALESCE(NULLIF(esm.subject_name, ''), g.concept, v2.subject_name, esm.subject_key), v2.subject_key
        ORDER BY n DESC, min_conf ASC NULLS LAST, esm.subject_key
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


def _write_direct_hit_md(path: Path, rows: list[dict[str, Any]], trade_date: date) -> None:
    lines = [
        "# Direct Theme Name Hit Audit",
        "",
        f"- trade_date: {trade_date.isoformat()}",
        f"- subject_count: {len(rows)}",
        f"- direct_hit_rows: {sum(int(row['n']) for row in rows)}",
        f"- v1_fallback_direct_hit_rows: {sum(int(row['n']) for row in rows if row['runtime_source'] == 'v1_fallback')}",
        "",
        "| subject_key | subject_name | runtime_source | n | low_conf_n | min_conf | max_conf |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['subject_key']} | {row['subject_name']} | {row['runtime_source']} | {row['n']} | "
            f"{row['low_conf_n']} | {row['min_conf']} | {row['max_conf']} |"
        )
    lines.extend(
        [
            "",
            "## Review Notes",
            "",
            "- Prioritize v1_fallback direct hits and short or ambiguous subject names.",
            "- For v2 rows, verify direct hits satisfy accept_requires_any instead of relying on a generic title token.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Build Product Runtime Repair Phase 2 attribution reports.")
    parser.add_argument("--db-name", default="stock_data_test")
    parser.add_argument("--trade-date", default="2026-05-22")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/product_runtime_phase2"))
    args = parser.parse_args()
    trade_date = date.fromisoformat(args.trade_date)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    conn = await connect(args.db_name)
    try:
        rows = [_attribution_row(row) for row in await _load_rows(conn, trade_date, args.limit)]
        direct_rows = await _direct_hit_rows(conn, trade_date)
    finally:
        await conn.close()
    _write_jsonl(args.out_dir / "product_match_quality_attribution.jsonl", rows)
    _write_attribution_md(args.out_dir / "product_match_quality_attribution.md", rows, trade_date)
    _write_direct_hit_md(args.out_dir / "direct_theme_name_hit_audit.md", direct_rows, trade_date)
    print(json.dumps({"rows": len(rows), "direct_hit_subjects": len(direct_rows), "out_dir": str(args.out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    run_async(_main())
