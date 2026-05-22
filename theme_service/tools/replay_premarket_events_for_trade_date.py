from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from theme_service.services.theme_service import ThemeService
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

OLD_HIGH_NOISE_SUBJECT_KEYS = {
    "9053827",  # 雅江水电最新互动
    "9050084",  # 精酿啤酒
    "9022889",  # 著名IP
    "9034544",  # 乌克兰重建
    "9024042",  # 全国文旅
    "9034920",  # 东方头
    "9051378",  # 陆军
    "9059230",  # 美国缺电
    "9020124",  # 天然气重卡
    "9023110",  # AI手机
    "9013587",  # 传媒
}

PHASE2B_SUBJECT_KEYS = {
    "9050659",  # 生猪
    "9020774",  # 券商重组预期
    "9028660",  # 华为芯片链
    "9059277",  # 福建
    "9033890",  # 科技类重组
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


def _contains_low_value(text: str) -> bool:
    return any(term in text for term in LOW_VALUE_TERMS)


def _is_debug_source(value: Any) -> bool:
    source = str(value or "")
    return source.startswith(DEBUG_SOURCE_PREFIXES)


def _list_value(evidence: dict[str, Any], *keys: str) -> list[str]:
    result: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value if item not in (None, ""))
        elif isinstance(value, str) and value:
            result.append(value)
    return list(dict.fromkeys(result))


def _first_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _md_escape(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")[:260]


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
    return (
        datetime.fromisoformat(str(start_raw)).replace(tzinfo=None),
        datetime.fromisoformat(str(end_raw)).replace(tzinfo=None),
    )


async def _load_v2_subject_keys(conn: Any, status: str) -> set[str]:
    rows = await conn.fetch("SELECT subject_key FROM theme_profile_v2 WHERE status = $1", status)
    return {str(row["subject_key"]) for row in rows}


async def _load_window_events(conn: Any, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            ne.id AS event_id,
            ne.news_id,
            ne.event_type,
            ne.summary,
            ne.entities,
            ne.causal_claim,
            ne.evidence_set,
            ne.raw_event_json,
            ne.source_category,
            ne.source_trace_id,
            ne.created_at,
            ne.event_time,
            COALESCE(ne.event_time, ne.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), ne.raw_event_json->>'title', NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(NULLIF(ne.summary, ''), ne.raw_event_json->>'summary', nr.content, '') AS event_summary,
            COALESCE(NULLIF(nr.content, ''), ne.raw_event_json->>'content', ne.summary, '') AS content
        FROM news_event ne
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE COALESCE(ne.event_time, ne.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
          AND COALESCE(ne.event_time, ne.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
          AND COALESCE(ne.source_category, '') !~ '^(product_runtime_|e2e_|test_)'
          AND COALESCE(ne.source_trace_id, '') !~ '^(product_runtime_|e2e_|test_)'
        ORDER BY occurred_at ASC NULLS LAST, ne.id ASC
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


async def _load_old_mappings(conn: Any, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            esm.*,
            COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), ne.raw_event_json->>'title', NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(NULLIF(ne.summary, ''), ne.raw_event_json->>'summary', nr.content, '') AS summary
        FROM event_subject_map esm
        JOIN news_event ne ON ne.id = esm.event_id
        LEFT JOIN news_raw nr ON nr.id = COALESCE(esm.news_id, ne.news_id)
        WHERE COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
          AND COALESCE(ne.event_time, ne.created_at, esm.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
          AND COALESCE(esm.source, '') !~ '^(product_runtime_|e2e_|test_)'
          AND COALESCE(esm.source_trace_id, '') !~ '^(product_runtime_|e2e_|test_)'
        ORDER BY esm.event_id, CASE WHEN esm.relation_type = 'primary' THEN 0 ELSE 1 END,
                 esm.confidence DESC NULLS LAST, esm.updated_at DESC NULLS LAST, esm.id DESC
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


async def _load_quarantine_mappings(conn: Any, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
    exists = await conn.fetchval("SELECT to_regclass('public.event_subject_map_quarantine')::text")
    if not exists:
        return []
    rows = await conn.fetch(
        """
        SELECT
            q.*,
            COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), ne.raw_event_json->>'title', NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(NULLIF(ne.summary, ''), ne.raw_event_json->>'summary', nr.content, '') AS summary
        FROM event_subject_map_quarantine q
        JOIN news_event ne ON ne.id = q.event_id
        LEFT JOIN news_raw nr ON nr.id = COALESCE(q.news_id, ne.news_id)
        WHERE COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) >= $1
          AND COALESCE(ne.event_time, ne.created_at, q.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) < $2
          AND COALESCE(q.source, '') !~ '^(product_runtime_|e2e_|test_)'
          AND COALESCE(q.source_trace_id, '') !~ '^(product_runtime_|e2e_|test_)'
        ORDER BY q.event_id, q.created_at DESC NULLS LAST, q.id DESC NULLS LAST
        """,
        start_at,
        end_at,
    )
    return [dict(row) for row in rows]


async def _load_events_by_ids(conn: Any, event_ids: set[int]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    rows = await conn.fetch(
        """
        SELECT
            ne.id AS event_id,
            ne.news_id,
            ne.event_type,
            ne.summary,
            ne.entities,
            ne.causal_claim,
            ne.evidence_set,
            ne.raw_event_json,
            ne.source_category,
            ne.source_trace_id,
            ne.created_at,
            ne.event_time,
            COALESCE(ne.event_time, ne.created_at, (nr.publish_date + nr.publish_time)::timestamp, nr.created_at) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), ne.raw_event_json->>'title', NULLIF(ne.summary, ''), ne.event_type, ('event#' || ne.id::text)) AS title,
            COALESCE(NULLIF(ne.summary, ''), ne.raw_event_json->>'summary', nr.content, '') AS event_summary,
            COALESCE(NULLIF(nr.content, ''), ne.raw_event_json->>'content', ne.summary, '') AS content
        FROM news_event ne
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE ne.id = ANY($1::bigint[])
          AND COALESCE(ne.source_category, '') !~ '^(product_runtime_|e2e_|test_)'
          AND COALESCE(ne.source_trace_id, '') !~ '^(product_runtime_|e2e_|test_)'
        ORDER BY occurred_at ASC NULLS LAST, ne.id ASC
        """,
        list(event_ids),
    )
    return [dict(row) for row in rows]


def _mapping_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_json(row.get("evidence_json"))
    return {
        "event_id": int(row.get("event_id") or 0),
        "news_id": int(row["news_id"]) if row.get("news_id") is not None else None,
        "subject_key": str(row.get("subject_key") or ""),
        "subject_name": str(row.get("subject_name") or ""),
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "relation_type": str(row.get("relation_type") or ""),
        "match_reason": str(row.get("match_reason") or row.get("reason") or ""),
        "source": str(row.get("source") or row.get("source_channel") or ""),
        "source_trace_id": str(row.get("source_trace_id") or ""),
        "run_id": str(row.get("run_id") or ""),
        "evidence": evidence,
    }


def _primary_mapping(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("relation_type") == "primary" else 1,
            -(float(row.get("confidence") or 0.0)),
        ),
    )
    return sorted_rows[0]


def _event_row_for_match(row: dict[str, Any]) -> dict[str, Any]:
    raw = _as_json(row.get("raw_event_json"))
    return {
        "event_id": int(row.get("event_id") or row.get("id")),
        "id": int(row.get("event_id") or row.get("id")),
        "news_id": int(row.get("news_id") or row.get("event_id") or row.get("id")),
        "title": str(row.get("title") or raw.get("title") or ""),
        "summary": str(row.get("event_summary") or row.get("summary") or raw.get("summary") or ""),
        "content": str(row.get("content") or raw.get("content") or ""),
        "event_type": str(row.get("event_type") or raw.get("event_type") or ""),
        "entities": _as_json(row.get("entities"), []),
        "causal_claim": _as_json(row.get("causal_claim"), []),
        "evidence_set": _as_json(row.get("evidence_set")),
        "raw_event_json": raw,
        "trace_id": f"product_runtime_0522_replay:{row.get('event_id')}",
    }


def _extract_new_fields(result: dict[str, Any], v2_keys: set[str]) -> dict[str, Any]:
    audit = _first_dict(result.get("audit"))
    evidence = _first_dict(audit.get("best_evidence"))
    subject_key = str(result.get("matched_subject_key") or "")
    reason_code = str(result.get("reason_code") or "")
    return {
        "new_decision": str(result.get("decision") or ""),
        "new_subject_key": subject_key,
        "new_theme_name": str(result.get("matched_theme_name") or ""),
        "new_confidence": float(result["confidence"]) if result.get("confidence") is not None else None,
        "new_reason_code": reason_code,
        "new_match_reason": reason_code,
        "runtime_source": "v2_accepted" if subject_key and subject_key in v2_keys else ("v1_fallback" if subject_key else ""),
        "best_evidence": evidence,
        "accepted_anchor_hits": _list_value(evidence, "accepted_anchor_hits", "anchor_hits", "must_hits", "strong_hits"),
        "direct_hit_terms": _list_value(evidence, "direct_hit_terms", "theme_name_hit_terms", "subject_name_hit_terms"),
        "negative_hits": _list_value(evidence, "negative_hits", "not_hits", "reject_hits"),
        "llm_accept_blocked": reason_code in LLM_ACCEPT_BLOCK_REASONS,
        "low_value_blocked": reason_code == "low_value_event_match_blocked",
        "audit": audit,
    }


def _known_issue_reason(title: str, summary: str, subject_key: str) -> str:
    text = f"{title} {summary}"
    if subject_key == "9050659" and any(term in text for term in ("山洪", "天气", "暴雨", "灾害", "预警")):
        return "weather_disaster_to_pig"
    if subject_key == "9020774" and any(term in text for term in ("普通收购", "并购基金", "资产收购", "收购")) and not any(term in text for term in ("券商", "证券公司", "证券行业")):
        return "generic_acquisition_to_brokerage_reorg"
    if subject_key == "9028660" and any(term in text for term in ("芯片", "晶圆", "代工", "封装", "半导体")) and not any(term in text for term in ("华为", "海思", "昇腾", "鲲鹏")):
        return "generic_chip_to_huawei_chip_chain"
    if subject_key == "9059277" and any(term in text for term in ("天气", "交通", "列车", "地震", "灾害", "旅游")):
        return "generic_local_news_to_fujian"
    if subject_key == "9033890" and any(term in text for term in ("科技", "投资", "产业基金", "战略合作")) and not any(term in text for term in ("资产注入", "借壳", "控制权变更", "重组")):
        return "generic_tech_to_tech_reorg"
    if subject_key == "9050371" and any(term in text for term in ("医学AI", "医学 AI", "医疗AI", "肥胖", "临床")):
        return "medical_ai_to_industrial_agent"
    if subject_key == "9046378" and any(term in text for term in ("英国消费者信心", "英国", "消费者信心")):
        return "uk_consumer_confidence_to_asean_fta"
    return ""


def _assessment(row: dict[str, Any], quarantined_subject_keys: set[str]) -> tuple[str, str]:
    title = str(row.get("title") or "")
    summary = str(row.get("summary") or "")
    new_decision = row.get("new_decision")
    new_subject_key = str(row.get("new_subject_key") or "")
    reason = str(row.get("new_reason_code") or "")
    if row.get("low_value_blocked") or (row.get("is_low_value_event") and new_decision != "MATCH"):
        return "blocked_low_value", "low_value_not_matched"
    if new_decision == "HUMAN_REVIEW":
        return "human_review_needed", reason
    if new_decision == "UNKNOWN":
        return "unknown_no_theme", reason
    if new_decision == "MATCH":
        known_issue = _known_issue_reason(title, summary, new_subject_key)
        if known_issue:
            return "likely_wrong", known_issue
        if new_subject_key in quarantined_subject_keys:
            return "likely_wrong", "matched_quarantined_subject_again"
        if row.get("is_low_value_event"):
            return "likely_wrong", "low_value_still_matched"
        if new_subject_key in OLD_HIGH_NOISE_SUBJECT_KEYS | PHASE2B_SUBJECT_KEYS and row.get("runtime_source") == "v1_fallback":
            return "likely_wrong", "high_noise_v1_fallback_match"
    return "likely_correct", ""


def _snapshot_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    payload = _as_json(snapshot.get("payload"))
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    major_events = _as_list(sections.get("major_events"))
    seen: set[str] = set()
    duplicate_primary = 0
    for item in major_events:
        key = str(item.get("event_id") or item.get("item_id") or item.get("title") or "")
        if key and key in seen:
            duplicate_primary += 1
        seen.add(key)
    low_value_major = sum(1 for item in major_events if _contains_low_value(f"{item.get('title') or ''} {item.get('summary') or ''}"))
    return {"snapshot_duplicate_primary_count": duplicate_primary, "snapshot_low_value_major_count": low_value_major}


def _summary_metrics(
    details: list[dict[str, Any]],
    snapshot: dict[str, Any],
    quarantine_by_event: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    old_match_events = {row["event_id"] for row in details if row.get("old_subject_key")}
    quarantined_event_ids = set(quarantine_by_event)
    metrics = {
        "replay_event_count": len(details),
        "old_match_count": len(old_match_events),
        "new_match_count": sum(row.get("new_decision") == "MATCH" for row in details),
        "new_human_review_count": sum(row.get("new_decision") == "HUMAN_REVIEW" for row in details),
        "new_unknown_count": sum(row.get("new_decision") == "UNKNOWN" for row in details),
        "changed_count": sum(bool(row.get("changed")) for row in details),
        "old_wrong_quarantined_count": len(quarantined_event_ids),
        "quarantined_now_blocked_count": sum(
            row.get("event_id") in quarantined_event_ids and row.get("new_decision") != "MATCH"
            for row in details
        ),
        "low_value_blocked_count": sum(bool(row.get("low_value_blocked")) for row in details),
        "llm_accept_blocked_count": sum(bool(row.get("llm_accept_blocked")) for row in details),
        "weak_v1_llm_accept_review_count": sum(row.get("new_reason_code") == "weak_v1_llm_accept_review" for row in details),
        "direct_theme_name_hit_count": sum(row.get("new_reason_code") == "direct_theme_name_hit" for row in details),
        "v1_fallback_direct_hit_count": sum(
            row.get("new_reason_code") == "direct_theme_name_hit" and row.get("runtime_source") == "v1_fallback"
            for row in details
        ),
        "duplicate_primary_count": 0,
        "suspicious_match_count": sum(row.get("assessment") == "likely_wrong" for row in details),
    }
    metrics.update(_snapshot_counts(snapshot))
    return metrics


def _write_table_report(path: Path, title: str, rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    lines = [f"# {title}", "", f"- count: {len(rows)}", ""]
    if rows:
        lines.append("| " + " | ".join(header for header, _ in columns) + " |")
        lines.append("|" + "|".join("---" for _ in columns) + "|")
        for row in rows:
            lines.append("| " + " | ".join(_md_escape(row.get(key)) for _, key in columns) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary(path: Path, trade_date: date, metrics: dict[str, Any], details: list[dict[str, Any]]) -> None:
    by_assessment = Counter(str(row.get("assessment") or "") for row in details)
    by_reason = Counter(str(row.get("new_reason_code") or "") for row in details)
    lines = ["# 2026-05-22 Premarket Replay Summary", "", f"- trade_date: {trade_date.isoformat()}"]
    for key in [
        "replay_event_count",
        "old_match_count",
        "new_match_count",
        "new_human_review_count",
        "new_unknown_count",
        "changed_count",
        "old_wrong_quarantined_count",
        "quarantined_now_blocked_count",
        "low_value_blocked_count",
        "llm_accept_blocked_count",
        "weak_v1_llm_accept_review_count",
        "direct_theme_name_hit_count",
        "v1_fallback_direct_hit_count",
        "duplicate_primary_count",
        "suspicious_match_count",
        "snapshot_low_value_major_count",
        "snapshot_duplicate_primary_count",
    ]:
        lines.append(f"- {key}: {metrics.get(key, 0)}")
    lines.extend(["", "## Assessment Distribution", ""])
    lines.extend(f"- {key}: {count}" for key, count in by_assessment.most_common())
    lines.extend(["", "## New Reason Code Distribution", ""])
    lines.extend(f"- {key}: {count}" for key, count in by_reason.most_common())
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is dry-run replay only. It does not write to `event_subject_map` or rebuild product snapshots.",
            "- `HUMAN_REVIEW` is expected for weak evidence after Phase 2D and should not be treated as a failed match automatically.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _configure_runtime(args: argparse.Namespace) -> None:
    os.environ["DB_TYPE"] = "postgresql"
    os.environ["PG_DATABASE"] = args.db_name
    os.environ["DB_NAME"] = args.db_name
    os.environ["READ_PG_DATABASE"] = args.db_name
    os.environ["POSTGRES_DATABASE"] = args.db_name
    os.environ["THEME_PROFILE_VERSION"] = args.profile_version
    os.environ["THEME_PROFILE_V2_STATUS"] = args.v2_status
    os.environ["THEME_PROFILE_V2_FALLBACK_TO_V1"] = "true"
    os.environ["THEME_PROFILE_V2_REQUIRE_LOADED"] = "true"
    os.environ["THEME_MATCH_LLM_JUDGE_MODE"] = args.llm_judge_mode


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run replay premarket events with current ThemeMatchEngine runtime.")
    parser.add_argument("--db-name", default="stock_data_test")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--write-mode", choices=["dry-run"], default="dry-run")
    parser.add_argument("--include-quarantine", action="store_true")
    parser.add_argument(
        "--event-scope",
        choices=["product-related", "all-window"],
        default="product-related",
        help="product-related replays active/quarantined mapped events; all-window also replays every window news_event.",
    )
    parser.add_argument("--event-id", action="append", type=int, default=[], help="Replay only specific event_id values.")
    parser.add_argument("--event-id-file", type=Path, default=None, help="JSONL/TXT file containing event_id values to replay.")
    parser.add_argument("--limit", type=int, default=0, help="Limit replay count after event selection; 0 means no limit.")
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--llm-judge-mode", choices=["off", "auto", "always"], default="off")
    parser.add_argument("--profile-version", default="v2")
    parser.add_argument("--v2-status", default="accepted_candidate")
    args = parser.parse_args()

    _configure_runtime(args)
    trade_date = date.fromisoformat(args.trade_date)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    conn = await connect(args.db_name)
    try:
        snapshot = await _load_snapshot(conn, trade_date)
        if not snapshot:
            raise RuntimeError(f"pre_market_brief_snapshot not found for trade_date={trade_date}")
        start_at, end_at = _window_from_snapshot(snapshot)
        if not start_at or not end_at:
            raise RuntimeError(f"pre_market_window missing for trade_date={trade_date}")
        v2_keys = await _load_v2_subject_keys(conn, args.v2_status)
        window_events = await _load_window_events(conn, start_at, end_at) if args.event_scope == "all-window" else []
        old_mappings_raw = await _load_old_mappings(conn, start_at, end_at)
        quarantine_raw = await _load_quarantine_mappings(conn, start_at, end_at) if args.include_quarantine else []
        window_event_ids = [int(row["event_id"]) for row in window_events]
        mapped_event_ids = [int(row["event_id"]) for row in old_mappings_raw if row.get("event_id")]
        quarantine_event_ids = [int(row["event_id"]) for row in quarantine_raw if row.get("event_id")]
        prioritized_event_ids = list(dict.fromkeys(mapped_event_ids + quarantine_event_ids + window_event_ids))
        event_ids = set(prioritized_event_ids)
        selected_ids = set(args.event_id)
        if args.event_id_file:
            for line in args.event_id_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    selected_ids.add(int(json.loads(line).get("event_id") if line.startswith("{") else line.split()[0]))
                except Exception:
                    selected_ids.add(int(line.split()[0]))
        if selected_ids:
            selected = selected_ids
            event_ids = event_ids & selected if event_ids else selected
            window_events = [row for row in window_events if int(row["event_id"]) in selected]
            old_mappings_raw = [row for row in old_mappings_raw if int(row["event_id"]) in selected]
            quarantine_raw = [row for row in quarantine_raw if int(row["event_id"]) in selected]
        if args.limit and args.limit > 0:
            limited_ids = set(prioritized_event_ids[: args.limit])
            event_ids = event_ids & limited_ids
            window_events = [row for row in window_events if int(row["event_id"]) in event_ids]
            old_mappings_raw = [row for row in old_mappings_raw if int(row["event_id"]) in event_ids]
            quarantine_raw = [row for row in quarantine_raw if int(row["event_id"]) in event_ids]
        extra_events = await _load_events_by_ids(conn, event_ids - {int(row["event_id"]) for row in window_events})
    finally:
        await conn.close()

    event_by_id: dict[int, dict[str, Any]] = {}
    for row in window_events + extra_events:
        event_by_id[int(row["event_id"])] = row

    old_by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in old_mappings_raw:
        if row.get("event_id") and not _is_debug_source(row.get("source")):
            old_by_event[int(row["event_id"])].append(_mapping_row(row))

    quarantine_by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in quarantine_raw:
        if row.get("event_id") and not _is_debug_source(row.get("source")):
            quarantine_by_event[int(row["event_id"])].append(_mapping_row(row))

    db_config = DatabaseConfig.from_env()
    db_config.db_type = DatabaseType.POSTGRESQL
    db_config.postgres_database = args.db_name
    db_gateway = await DatabaseGateway.initialize(config=db_config, auto_warm_cache=False)
    theme_service = ThemeService(enable_clustering=False)
    theme_service.set_database_gateway(db_gateway)

    details: list[dict[str, Any]] = []
    try:
        total = len(event_by_id)
        for index, event_id in enumerate(sorted(event_by_id), start=1):
            if args.progress_every > 0 and (index == 1 or index % args.progress_every == 0 or index == total):
                print(f"[replay] {index}/{total} event_id={event_id}", flush=True)
            event = event_by_id[event_id]
            match_input = _event_row_for_match(event)
            result = await theme_service.match_event(match_input, database_gateway=db_gateway)
            old_primary = _primary_mapping(old_by_event.get(event_id, []))
            quarantine_rows = quarantine_by_event.get(event_id, [])
            quarantined_subject_keys = {row["subject_key"] for row in quarantine_rows}
            new_fields = _extract_new_fields(result, v2_keys)
            text = f"{match_input.get('title') or ''} {match_input.get('summary') or ''}"
            row = {
                "event_id": event_id,
                "news_id": match_input.get("news_id"),
                "title": match_input.get("title") or "",
                "summary": match_input.get("summary") or "",
                "occurred_at": event.get("occurred_at"),
                "old_subject_key": old_primary.get("subject_key", ""),
                "old_theme_name": old_primary.get("subject_name", ""),
                "old_confidence": old_primary.get("confidence"),
                "old_match_reason": old_primary.get("match_reason", ""),
                "old_all_matches": old_by_event.get(event_id, []),
                "quarantine_matches": quarantine_rows,
                "is_low_value_event": _contains_low_value(text),
                **new_fields,
            }
            row["changed"] = (
                row["old_subject_key"] != row["new_subject_key"]
                or ("MATCH" if row["old_subject_key"] else "") != row["new_decision"]
            )
            assessment, assessment_reason = _assessment(row, quarantined_subject_keys)
            row["assessment"] = assessment
            row["assessment_reason"] = assessment_reason
            details.append(row)
    finally:
        await db_gateway.close()

    metrics = _summary_metrics(details, snapshot, quarantine_by_event)
    suspicious = [row for row in details if row.get("assessment") == "likely_wrong"]
    human_review = [row for row in details if row.get("new_decision") == "HUMAN_REVIEW"]
    unknown = [row for row in details if row.get("new_decision") == "UNKNOWN"]
    low_value_blocked = [row for row in details if row.get("low_value_blocked") or (row.get("is_low_value_event") and row.get("new_decision") != "MATCH")]
    llm_blocked = [row for row in details if row.get("llm_accept_blocked")]
    changed = [row for row in details if row.get("changed")]

    _write_jsonl(args.out_dir / "replay_match_detail.jsonl", details)
    _write_summary(args.out_dir / "replay_match_summary.md", trade_date, metrics, details)

    columns = [
        ("event_id", "event_id"),
        ("old", "old_theme_name"),
        ("new_decision", "new_decision"),
        ("new", "new_theme_name"),
        ("reason", "new_reason_code"),
        ("assessment", "assessment"),
        ("title", "title"),
    ]
    _write_table_report(args.out_dir / "old_vs_new_match_diff.md", "Old vs New Match Diff", changed, columns)
    _write_table_report(args.out_dir / "suspicious_matches.md", "Suspicious Matches", suspicious, columns)
    _write_table_report(args.out_dir / "human_review_cases.md", "Human Review Cases", human_review, columns)
    _write_table_report(args.out_dir / "unknown_cases.md", "Unknown Cases", unknown, columns)
    _write_table_report(args.out_dir / "low_value_blocked_cases.md", "Low Value Blocked Cases", low_value_blocked, columns)
    _write_table_report(args.out_dir / "llm_accept_blocked_cases.md", "LLM Accept Blocked Cases", llm_blocked, columns)

    print(json.dumps({"trade_date": trade_date.isoformat(), "out_dir": str(args.out_dir), **metrics}, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    run_async(_main())
