from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
    "地震灾害",
    "列车停运",
    "旅客列车停",
    "人事任命",
    "季度财报",
    "发布财报",
    "业绩说明会",
)

LLM_ACCEPT_BLOCK_REASONS = {
    "weak_v1_llm_accept_review",
    "llm_accept_without_hard_evidence",
    "llm_accept_generic_only_review",
    "low_conf_llm_accept_review",
    "low_value_event_match_blocked",
}

DEBUG_SOURCE_PREFIXES = ("product_runtime_", "e2e_", "test_")
TARGET_WATCHLIST_SUBJECT_KEYS = {"9054404", "9012396", "9043698"}
BROAD_THEME_WATCHLIST: dict[str, dict[str, str]] = {
    "9012538": {"theme_name": "VR", "risk_tier": "P0"},
    "9062454": {"theme_name": "AI产业链五大核心", "risk_tier": "P0"},
    "9042007": {"theme_name": "农业新质生产力", "risk_tier": "P0"},
    "9025348": {"theme_name": "汽车国企", "risk_tier": "P0"},
    "9054404": {"theme_name": "A股全球第一", "risk_tier": "P0"},
    "9013055": {"theme_name": "物流", "risk_tier": "P1"},
    "9034811": {"theme_name": "宁德产业链", "risk_tier": "P1"},
    "9010818": {"theme_name": "国企改革", "risk_tier": "P1"},
    "9042824": {"theme_name": "原子级制造", "risk_tier": "P2"},
    "9044821": {"theme_name": "季戊四醇产业链", "risk_tier": "P2"},
    "9048607": {"theme_name": "中美芬太尼合作", "risk_tier": "P2"},
}


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_debug_source(value: Any) -> bool:
    source = str(value or "")
    return source.startswith(DEBUG_SOURCE_PREFIXES)


def _contains_low_value(text: str) -> bool:
    return any(term in text for term in LOW_VALUE_TERMS)


def _list_value(evidence: dict[str, Any], *keys: str) -> list[str]:
    result: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value if item not in (None, ""))
        elif isinstance(value, str) and value:
            result.append(value)
    return list(dict.fromkeys(result))


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


def _window_from_snapshot(snapshot: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    payload = _as_json(snapshot.get("payload"))
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    window = diagnostics.get("pre_market_window") if isinstance(diagnostics.get("pre_market_window"), dict) else {}
    start_raw = window.get("start_at")
    end_raw = window.get("end_at")
    if not start_raw or not end_raw:
        return None, None
    # Most source timestamps in this schema are `timestamp without time zone`.
    # Use the local wall-clock window from the snapshot and drop tzinfo before
    # binding to asyncpg to avoid aware/naive comparison errors.
    return (
        datetime.fromisoformat(str(start_raw)).replace(tzinfo=None),
        datetime.fromisoformat(str(end_raw)).replace(tzinfo=None),
    )


async def _load_mapped_rows(conn: Any, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        WITH mapped AS (
            SELECT
                esm.id,
                esm.event_id,
                esm.news_id,
                esm.subject_key,
                COALESCE(NULLIF(esm.subject_name, ''), v2.subject_name, g.concept, esm.subject_key) AS subject_name,
                esm.confidence,
                esm.relation_type,
                esm.match_reason,
                esm.evidence_json,
                esm.source,
                esm.source_trace_id,
                esm.run_id,
                esm.created_at,
                esm.updated_at,
                COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
                COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
                COALESCE(ne.summary, nr.content, '') AS summary,
                CASE WHEN v2.subject_key IS NOT NULL THEN 'v2_accepted' ELSE 'v1_fallback' END AS runtime_source,
                ROW_NUMBER() OVER (
                    PARTITION BY esm.event_id
                    ORDER BY CASE WHEN esm.relation_type = 'primary' THEN 0 ELSE 1 END,
                             esm.confidence DESC NULLS LAST,
                             esm.updated_at DESC NULLS LAST
                ) AS event_rank
            FROM event_subject_map esm
            JOIN news_event ne ON ne.id = esm.event_id
            LEFT JOIN news_raw nr ON nr.id = COALESCE(esm.news_id, ne.news_id)
            LEFT JOIN theme_profile_v2 v2 ON v2.subject_key = esm.subject_key AND v2.status = 'accepted_candidate'
            LEFT JOIN theme_gate_profile g ON g.subject_key = esm.subject_key
            WHERE COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
              AND COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
              AND COALESCE(esm.source, '') !~ '^(product_runtime_|e2e_|test_)'
        )
        SELECT * FROM mapped
        ORDER BY occurred_at DESC NULLS LAST, event_id DESC, event_rank
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


async def _load_review_rows(conn: Any, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
    exists = await conn.fetchval("SELECT to_regclass('public.event_review_queue')::text")
    if not exists:
        return []
    rows = await conn.fetch(
        """
        SELECT
            q.id,
            q.event_id,
            q.review_status,
            q.proposed_theme_name,
            q.proposed_theme_confidence,
            q.reason,
            q.source_channel,
            q.created_at,
            COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(ne.summary, nr.content, '') AS summary
        FROM event_review_queue q
        JOIN news_event ne ON ne.id = q.event_id
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
          AND COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
          AND COALESCE(q.source_channel, '') !~ '^(product_runtime_|e2e_|test_)'
        ORDER BY occurred_at DESC NULLS LAST, q.event_id DESC
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


def _snapshot_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = _as_json(snapshot.get("payload"))
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    major_events = _as_list(sections.get("major_events"))
    matched_themes = _as_list(sections.get("matched_themes"))
    low_value_major = sum(
        1
        for row in major_events
        if _contains_low_value(f"{row.get('title') or ''} {row.get('summary') or ''}")
    )
    seen_event_ids: set[str] = set()
    duplicate_primary = 0
    for row in major_events:
        key = str(row.get("event_id") or row.get("item_id") or row.get("title") or "")
        if key and key in seen_event_ids:
            duplicate_primary += 1
        seen_event_ids.add(key)
    return {
        "major_events_count": len(major_events),
        "matched_themes_count": len(matched_themes),
        "review_events_count": len(_as_list(sections.get("review_events"))),
        "unknown_watch_count": len(_as_list(sections.get("unknown_watch"))),
        "low_value_major_count": low_value_major,
        "duplicate_primary_count": duplicate_primary,
        "dropped_event_count": int(diagnostics.get("dropped_event_count") or 0),
        "low_value_dropped_count": int(diagnostics.get("low_value_dropped_count") or 0),
        "review_ineligible_dropped_count": int(diagnostics.get("review_ineligible_dropped_count") or 0),
        "high_value_review_count": int(diagnostics.get("high_value_review_count") or 0),
        "match_count": int(diagnostics.get("matched_event_count") or len(major_events) or 0),
        "human_review_count": int(diagnostics.get("review_event_count") or 0),
        "unknown_count": int(diagnostics.get("unknown_event_count") or 0),
        "diagnostics": diagnostics,
    }


def _detail_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_json(row.get("evidence_json"))
    text = f"{row.get('title') or ''} {row.get('summary') or ''}"
    return {
        "event_id": row.get("event_id"),
        "title": row.get("title") or "",
        "summary": row.get("summary") or "",
        "subject_key": row.get("subject_key") or "",
        "subject_name": row.get("subject_name") or "",
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "match_reason": row.get("match_reason") or "",
        "runtime_source": row.get("runtime_source") or "",
        "source": row.get("source") or "",
        "run_id": row.get("run_id") or "",
        "event_rank": int(row.get("event_rank") or 0),
        "is_low_value_event": _contains_low_value(text),
        "direct_hit_terms": _list_value(evidence, "direct_hit_terms", "direct_hits", "theme_name_hit_terms", "subject_name_hit_terms"),
        "accepted_anchor_hits": _list_value(evidence, "accepted_anchor_hits", "anchor_hits", "must_hits", "strong_hits"),
        "negative_hits": _list_value(evidence, "negative_hits", "not_hits", "reject_hits"),
        "best_evidence": evidence,
    }


def _obvious_wrong_candidates(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in details:
        reason = str(row.get("match_reason") or "")
        runtime_source = str(row.get("runtime_source") or "")
        confidence = row.get("confidence")
        low_conf = isinstance(confidence, (int, float)) and confidence < 0.90
        if row.get("is_low_value_event"):
            out.append({**row, "candidate_reason": "low_value_matched"})
        elif int(row.get("event_rank") or 0) > 1:
            out.append({**row, "candidate_reason": "duplicate_primary_candidate"})
        elif runtime_source == "v1_fallback" and reason in {"direct_theme_name_hit", "llm_accept_match"} and low_conf:
            out.append({**row, "candidate_reason": "low_conf_v1_fallback_accept"})
        elif reason == "direct_theme_name_hit" and low_conf:
            out.append({**row, "candidate_reason": "low_conf_direct_hit"})
        elif reason == "llm_accept_match" and low_conf and not row.get("accepted_anchor_hits"):
            out.append({**row, "candidate_reason": "low_conf_llm_no_anchor"})
    return out


def _quality_watch_metrics(details: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, int]:
    direct_hits = [row for row in details if row.get("match_reason") == "direct_theme_name_hit"]
    v1_fallback_direct_hits = [row for row in direct_hits if row.get("runtime_source") == "v1_fallback"]
    direct_hit_bad = [row for row in candidates if row.get("match_reason") == "direct_theme_name_hit"]
    v1_fallback_direct_hit_bad = [
        row for row in direct_hit_bad if row.get("runtime_source") == "v1_fallback"
    ]
    direct_hit_event_groups: dict[int, int] = {}
    for row in direct_hits:
        event_id = int(row.get("event_id") or 0)
        if event_id:
            direct_hit_event_groups[event_id] = direct_hit_event_groups.get(event_id, 0) + 1
    ambiguous_direct_hit_candidates = sum(count > 1 for count in direct_hit_event_groups.values())
    target_wrong_theme_residual = sum(
        row.get("subject_key") in TARGET_WATCHLIST_SUBJECT_KEYS for row in direct_hit_bad
    )
    return {
        "direct_theme_name_hit_count": len(direct_hits),
        "v1_fallback_direct_hit_count": len(v1_fallback_direct_hits),
        "direct_theme_name_hit_bad_count": len(direct_hit_bad),
        "v1_fallback_direct_hit_bad_count": len(v1_fallback_direct_hit_bad),
        "ambiguous_direct_hit_candidates_count": ambiguous_direct_hit_candidates,
        "target_wrong_theme_residual_count": target_wrong_theme_residual,
    }


def _watchlist_subject_rows(
    details: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    details_by_subject: dict[str, list[dict[str, Any]]] = {}
    for row in details:
        subject_key = str(row.get("subject_key") or "")
        if not subject_key:
            continue
        details_by_subject.setdefault(subject_key, []).append(row)

    review_by_theme: Counter[str] = Counter(
        str(row.get("proposed_theme_name") or "") for row in reviews if str(row.get("proposed_theme_name") or "")
    )
    bad_by_subject: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        subject_key = str(row.get("subject_key") or "")
        if not subject_key:
            continue
        bad_by_subject.setdefault(subject_key, []).append(row)

    rows: list[dict[str, Any]] = []
    for subject_key, meta in BROAD_THEME_WATCHLIST.items():
        subject_rows = details_by_subject.get(subject_key, [])
        direct_hits = [row for row in subject_rows if row.get("match_reason") == "direct_theme_name_hit"]
        v1_direct_hits = [row for row in direct_hits if row.get("runtime_source") == "v1_fallback"]
        bad_rows = bad_by_subject.get(subject_key, [])
        top_bad_examples = [
            f"{row.get('event_id')}:{str(row.get('title') or '')[:40]}"
            for row in bad_rows[:3]
        ]
        direct_pressure = len(direct_hits) + len(v1_direct_hits)
        suggested_action = "observe"
        if meta["risk_tier"] == "P0" and bad_rows:
            suggested_action = "delta_repair"
        elif meta["risk_tier"] == "P0" and direct_pressure > 0:
            suggested_action = "watch_direct_hit_pressure"
        elif meta["risk_tier"] == "P1" and direct_pressure > 0:
            suggested_action = "watch_boundary_width"
        rows.append(
            {
                "subject_key": subject_key,
                "theme_name": meta["theme_name"],
                "risk_tier": meta["risk_tier"],
                "match_count": len(subject_rows),
                "review_count": review_by_theme.get(meta["theme_name"], 0),
                "direct_theme_name_hit_count": len(direct_hits),
                "v1_fallback_direct_hit_count": len(v1_direct_hits),
                "bad_count": len(bad_rows),
                "top_bad_examples": top_bad_examples,
                "suggested_action": suggested_action,
            }
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _write_quality_report(path: Path, trade_date: date, metrics: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    lines = [
        "# Product Runtime Daily Quality Report",
        "",
        f"- trade_date: {trade_date.isoformat()}",
    ]
    for key in [
        "major_events_count",
        "matched_themes_count",
        "review_events_count",
        "unknown_watch_count",
        "dropped_event_count",
        "low_value_dropped_count",
        "review_ineligible_dropped_count",
        "high_value_review_count",
        "duplicate_primary_count",
        "low_value_major_count",
        "hard_negative_violation_count",
        "match_count",
        "human_review_count",
        "unknown_count",
        "direct_theme_name_hit_count",
        "v1_fallback_direct_hit_count",
        "direct_theme_name_hit_bad_count",
        "v1_fallback_direct_hit_bad_count",
        "ambiguous_direct_hit_candidates_count",
        "target_wrong_theme_residual_count",
        "hard_negative_subject_count",
        "watchlist_subject_count",
        "watchlist_subject_bad_count",
        "llm_accept_blocked_count",
        "v1_fallback_match_count",
        "v2_accepted_match_count",
        "obvious_wrong_match_sample_count",
    ]:
        lines.append(f"- {key}: {metrics.get(key, 0)}")
    lines.extend(
        [
            "",
            "## Observation Notes",
            "",
            "- This report is observational. Do not enter Phase 3C unless real new data triggers a Phase 3C condition.",
            "- Phase 3B baseline: product review should only contain high-value uncertain events.",
            "- Do not continue gate repair unless a Phase 3C trigger is observed.",
            "- Watchlist themes: 9054404 / A股全球第一, 9012396 / 新疆自贸区, 9043698 / 深海经济.",
            "- `target_wrong_theme_residual_count` should remain 0 during the observation window.",
            "",
            "## Broad Theme Watchlist",
            "",
            "| subject_key | theme_name | risk_tier | match_count | review_count | direct_hit | v1_fallback_direct_hit | bad_count | top_bad_examples | suggested_action |",
            "|---|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in _as_list(metrics.get("watchlist_subject_rows")):
        examples = "<br>".join(str(item).replace("|", "/") for item in row.get("top_bad_examples") or []) or "-"
        lines.append(
            f"| {row.get('subject_key')} | {row.get('theme_name')} | {row.get('risk_tier')} | "
            f"{row.get('match_count')} | {row.get('review_count')} | {row.get('direct_theme_name_hit_count')} | "
            f"{row.get('v1_fallback_direct_hit_count')} | {row.get('bad_count')} | {examples} | {row.get('suggested_action')} |"
        )
    hard_rows = _as_list(metrics.get("hard_negative_subject_rows"))
    lines.extend(
        [
            "",
            "## Hard Negative Watchlist",
            "",
            "| subject_key | subject_name | hard_negative_case_count | hard_negative_reject_count | hard_negative_reject_rate | failed_hard_negative_cases |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in hard_rows:
        failed = "<br>".join(str(item).replace("|", "/") for item in row.get("failed_hard_negative_cases") or []) or "-"
        lines.append(
            f"| {row.get('subject_key')} | {row.get('subject_name')} | {row.get('hard_negative_case_count')} | "
            f"{row.get('hard_negative_reject_count')} | {row.get('hard_negative_reject_rate')} | {failed} |"
        )
    lines.extend(
        [
            "",
            "## Obvious Wrong Match Candidates",
            "",
            "| event_id | subject | reason | source | confidence | title | candidate_reason |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    for row in candidates[:50]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(
            f"| {row.get('event_id')} | {row.get('subject_key')} {row.get('subject_name')} | "
            f"{row.get('match_reason')} | {row.get('runtime_source')} | {row.get('confidence')} | "
            f"{title} | {row.get('candidate_reason')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hard_negative_violation_count(summary_path: Path | None) -> int:
    candidates = []
    if summary_path is not None:
        candidates.append(summary_path)
    candidates.extend(
        [
            Path("tmp/product_runtime_phase3b/full_hard_negative_active_v2/theme_profile_v1_v2_compare_summary.json"),
            Path("tmp/product_runtime_phase3/full_hard_negative_active_v2/theme_profile_v1_v2_compare_summary.json"),
        ]
    )
    for path in candidates:
        if not path.exists():
            continue
        data = _as_json(path.read_text(encoding="utf-8"))
        total = int(data.get("hard_negative_total") or 0)
        rate = float(data.get("v2_hard_negative_reject_rate") or 0.0)
        return max(0, round(total * (1.0 - rate)))
    return 0


def _hard_negative_subject_rows(summary_path: Path | None) -> list[dict[str, Any]]:
    candidates = []
    if summary_path is not None:
        candidates.append(summary_path)
    candidates.extend(
        [
            Path("tmp/product_runtime_phase3b/full_hard_negative_active_v2/theme_profile_v1_v2_compare_summary.json"),
            Path("tmp/product_runtime_phase3/full_hard_negative_active_v2/theme_profile_v1_v2_compare_summary.json"),
        ]
    )
    for path in candidates:
        if not path.exists():
            continue
        data = _as_json(path.read_text(encoding="utf-8"))
        rows = data.get("hard_negative_subject_rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _write_direct_hit_audit(path: Path, details: list[dict[str, Any]]) -> None:
    grouped: Counter[tuple[str, str, str]] = Counter()
    for row in details:
        if row.get("match_reason") == "direct_theme_name_hit":
            grouped[(str(row.get("subject_key")), str(row.get("subject_name")), str(row.get("runtime_source")))] += 1
    lines = [
        "# Direct Theme Name Hit Audit",
        "",
        f"- direct_theme_name_hit_count: {sum(grouped.values())}",
        "",
        "| subject_key | subject_name | runtime_source | n |",
        "|---|---|---|---:|",
    ]
    for (subject_key, subject_name, runtime_source), count in grouped.most_common():
        lines.append(f"| {subject_key} | {subject_name} | {runtime_source} | {count} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_match_audit(path: Path, details: list[dict[str, Any]]) -> None:
    by_subject: Counter[tuple[str, str, str]] = Counter()
    by_reason: Counter[str] = Counter()
    for row in details:
        by_subject[(str(row.get("subject_key")), str(row.get("subject_name")), str(row.get("runtime_source")))] += 1
        by_reason[str(row.get("match_reason") or "")] += 1
    lines = [
        "# Match Audit",
        "",
        f"- match_rows: {len(details)}",
        "",
        "## By Match Reason",
    ]
    lines.extend(f"- {reason or 'unknown'}: {count}" for reason, count in by_reason.most_common())
    lines.extend(["", "## By Subject", "", "| subject_key | subject_name | runtime_source | n |", "|---|---|---|---:|"])
    for (subject_key, subject_name, runtime_source), count in by_subject.most_common(80):
        lines.append(f"| {subject_key} | {subject_name} | {runtime_source} | {count} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_review_audit(path: Path, reviews: list[dict[str, Any]]) -> None:
    by_status = Counter(str(row.get("review_status") or "") for row in reviews)
    by_reason = Counter(str(row.get("reason") or "") for row in reviews)
    lines = [
        "# Review Audit",
        "",
        f"- review_queue_rows_in_window: {len(reviews)}",
        "",
        "## By Status",
    ]
    lines.extend(f"- {status or 'unknown'}: {count}" for status, count in by_status.most_common())
    lines.extend(["", "## By Reason", ""])
    lines.extend(f"- {reason or 'unknown'}: {count}" for reason, count in by_reason.most_common(30))
    lines.extend(["", "## Detail", "", "| event_id | status | reason | proposed_theme | title |", "|---|---|---|---|---|"])
    for row in reviews[:120]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(
            f"| {row.get('event_id')} | {row.get('review_status')} | {row.get('reason') or ''} | "
            f"{row.get('proposed_theme_name') or ''} | {title} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_llm_accept_audit(path: Path, details: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> None:
    match_rows = [row for row in details if row.get("match_reason") == "llm_accept_match"]
    blocked = [row for row in reviews if row.get("reason") in LLM_ACCEPT_BLOCK_REASONS]
    by_reason = Counter(str(row.get("reason") or "") for row in blocked)
    lines = [
        "# LLM Accept Audit",
        "",
        f"- llm_accept_match_count: {len(match_rows)}",
        f"- llm_accept_blocked_count: {len(blocked)}",
    ]
    lines.extend(f"- {reason}: {count}" for reason, count in by_reason.most_common())
    lines.extend(
        [
            "",
            "## Active LLM MATCH Rows",
            "",
            "| event_id | subject | source | confidence | title |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in match_rows[:80]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(f"| {row.get('event_id')} | {row.get('subject_key')} {row.get('subject_name')} | {row.get('runtime_source')} | {row.get('confidence')} | {title} |")
    lines.extend(["", "## Blocked LLM Accept Reviews", "", "| event_id | reason | proposed_theme | confidence | title |", "|---|---|---|---:|---|"])
    for row in blocked[:80]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(f"| {row.get('event_id')} | {row.get('reason')} | {row.get('proposed_theme_name') or ''} | {row.get('proposed_theme_confidence') or ''} | {title} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_low_value_audit(path: Path, details: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> None:
    matched = [row for row in details if row.get("is_low_value_event")]
    blocked = [row for row in reviews if row.get("reason") == "low_value_event_match_blocked"]
    lines = [
        "# Low Value Audit",
        "",
        f"- low_value_matched_count: {len(matched)}",
        f"- low_value_event_match_blocked_count: {len(blocked)}",
        "",
        "## Low Value Matched Rows",
        "",
        "| event_id | subject | reason | title |",
        "|---|---|---|---|",
    ]
    for row in matched[:80]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(f"| {row.get('event_id')} | {row.get('subject_key')} {row.get('subject_name')} | {row.get('match_reason')} | {title} |")
    lines.extend(["", "## Low Value Blocked Reviews", "", "| event_id | reason | title |", "|---|---|---|"])
    for row in blocked[:80]:
        title = str(row.get("title") or "").replace("|", "/")
        lines.append(f"| {row.get('event_id')} | {row.get('reason')} | {title} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_drop_audit(path: Path, metrics: dict[str, Any], reviews: list[dict[str, Any]]) -> None:
    dropped_reviews = [row for row in reviews if str(row.get("review_status") or "") == "dropped"]
    by_reason = Counter(str(row.get("reason") or "") for row in dropped_reviews)
    lines = [
        "# Drop Audit",
        "",
        f"- dropped_event_count: {metrics.get('dropped_event_count', 0)}",
        f"- low_value_dropped_count: {metrics.get('low_value_dropped_count', 0)}",
        f"- review_ineligible_dropped_count: {metrics.get('review_ineligible_dropped_count', 0)}",
        f"- dropped_review_queue_rows_in_window: {len(dropped_reviews)}",
        "",
        "## Dropped Review Queue Reasons",
    ]
    lines.extend(f"- {reason or 'unknown'}: {count}" for reason, count in by_reason.most_common(30))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Build daily product runtime quality observation report.")
    parser.add_argument("--db-name", default="stock_data_test")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--hard-negative-summary", type=Path, default=None)
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date)
    out_dir = args.out_dir or Path("tmp/product_runtime_daily_quality") / trade_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = await connect(args.db_name)
    try:
        snapshot = await _load_snapshot(conn, trade_date)
        if not snapshot:
            raise RuntimeError(f"pre_market_brief_snapshot not found for trade_date={trade_date}")
        start_at, end_at = _window_from_snapshot(snapshot)
        if not start_at or not end_at:
            raise RuntimeError(f"snapshot pre_market_window missing for trade_date={trade_date}")
        mapped_rows = await _load_mapped_rows(conn, start_at, end_at)
        review_rows = await _load_review_rows(conn, start_at, end_at)
    finally:
        await conn.close()

    details = [_detail_row(row) for row in mapped_rows]
    snapshot_metrics = _snapshot_counts(snapshot)
    candidates = _obvious_wrong_candidates(details)
    watch_metrics = _quality_watch_metrics(details, candidates)
    watchlist_subject_rows = _watchlist_subject_rows(details, review_rows, candidates)
    hard_negative_subject_rows = _hard_negative_subject_rows(args.hard_negative_summary)
    llm_blocked = [row for row in review_rows if row.get("reason") in LLM_ACCEPT_BLOCK_REASONS]
    metrics = {
        **snapshot_metrics,
        "llm_accept_match_count": sum(row.get("match_reason") == "llm_accept_match" for row in details),
        "llm_accept_blocked_count": len(llm_blocked),
        "weak_v1_llm_accept_review_count": sum(row.get("reason") == "weak_v1_llm_accept_review" for row in review_rows),
        "low_conf_llm_accept_review_count": sum(row.get("reason") == "low_conf_llm_accept_review" for row in review_rows),
        "low_value_event_match_blocked_count": sum(row.get("reason") == "low_value_event_match_blocked" for row in review_rows),
        "v1_fallback_match_count": sum(row.get("runtime_source") == "v1_fallback" for row in details),
        "v2_accepted_match_count": sum(row.get("runtime_source") == "v2_accepted" for row in details),
        "obvious_wrong_match_sample_count": len(candidates),
        "hard_negative_violation_count": _hard_negative_violation_count(args.hard_negative_summary),
        "hard_negative_subject_count": len(hard_negative_subject_rows),
        "hard_negative_subject_rows": hard_negative_subject_rows,
        "watchlist_subject_count": len(watchlist_subject_rows),
        "watchlist_subject_bad_count": sum(int(row.get("bad_count") or 0) for row in watchlist_subject_rows),
        **watch_metrics,
        "watchlist_subject_rows": watchlist_subject_rows,
    }
    metrics.pop("diagnostics", None)

    _write_jsonl(out_dir / "quality_detail.jsonl", details)
    _write_quality_report(out_dir / "quality_report.md", trade_date, metrics, candidates)
    _write_review_audit(out_dir / "review_audit.md", review_rows)
    _write_drop_audit(out_dir / "drop_audit.md", metrics, review_rows)
    _write_match_audit(out_dir / "match_audit.md", details)
    _write_direct_hit_audit(out_dir / "direct_hit_audit.md", details)
    _write_llm_accept_audit(out_dir / "llm_accept_audit.md", details, review_rows)
    _write_low_value_audit(out_dir / "low_value_audit.md", details, review_rows)
    print(json.dumps({"trade_date": trade_date.isoformat(), "out_dir": str(out_dir), **metrics}, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    run_async(_main())
