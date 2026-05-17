from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.services.theme_match_engine import ThemeMatchEngine
from theme_service.services.theme_match_types import ThemeMatchRequest, ThemeProfile
from theme_service.tools.profile_eval_common import (
    count_generic_only_related,
    disable_llm_for_engine,
    hard_negative_row,
    is_hard_negative_rejected,
    request_from_hard_negative,
)
from theme_service.tools.profile_quality_common import (
    add_db_args,
    connect,
    default_output_dir,
    load_json,
    normalize_list,
    read_jsonl,
    run_async,
    safe_str,
    table_exists,
    unique,
    write_csv,
    write_jsonl,
)

ALIAS_MAP: dict[str, list[str]] = {
    "AI/AR眼镜": ["AI/AR眼镜", "AI智能眼镜", "AI眼镜", "AR眼镜", "智能眼镜", "XR眼镜"],
    "AI智能体Manus": ["AI智能体Manus", "Manus", "智能体", "AI智能体", "Agent"],
    "SpaceX": ["SpaceX", "星链", "商业航天", "卫星互联网", "星舰"],
    "卫星互联": ["卫星互联", "卫星互联网", "星链", "低轨卫星", "商业航天", "SpaceX"],
    "可控核聚变": ["可控核聚变", "核聚变", "人造太阳"],
    "对日制裁": ["对日制裁", "中日关系", "出口管制", "反制日本"],
    "稀土永磁": ["稀土永磁", "稀土", "中重稀土", "稀土出口管制"],
    "光刻胶": ["光刻胶", "半导体材料", "半导体", "光刻"],
    "液冷数据中心": ["液冷数据中心", "液冷", "数据中心", "算力液冷", "IDC"],
    "海洋经济": ["海洋经济", "海工装备", "航运", "港口", "海洋牧场", "海上风电"],
}


class _StaticRepo:
    def __init__(self, profiles: list[ThemeProfile]):
        self._profiles = profiles

    async def load_active_profiles(self) -> list[ThemeProfile]:
        return self._profiles

    async def semantic_recall_candidates(self, query_embedding, top_k: int = 20):
        return []

    async def sparse_recall_candidates(self, query_text: str, top_k: int = 20):
        return []


def _request_from_row(row: dict[str, Any]) -> ThemeMatchRequest:
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    return ThemeMatchRequest(
        event_id=_safe_int(row.get("event_id") or row.get("id") or row.get("case_no")),
        news_id=_safe_int(row.get("news_id")),
        title=safe_str(row.get("title")),
        content=safe_str(row.get("content") or row.get("summary")),
        summary=safe_str(row.get("summary")),
        event_type=safe_str(row.get("event_type")),
        entities=normalize_list(row.get("entities")),
        raw_event_json=row,
        trace_id=safe_str(row.get("trace_id") or row.get("case_id")),
    )


def _load_events_jsonl(path: Path, limit: int, gold_labels_path: Path | None = None) -> list[dict[str, Any]]:
    rows = read_jsonl(path)[:limit]
    if not gold_labels_path:
        return rows
    gold_by_case = {
        safe_str(row.get("case_id")): safe_str(row.get("gold_theme_name"))
        for row in read_jsonl(gold_labels_path)
        if safe_str(row.get("case_id"))
    }
    for row in rows:
        case_id = safe_str(row.get("case_id"))
        if case_id and gold_by_case.get(case_id):
            row["gold_theme_name"] = gold_by_case[case_id]
            row["gold_terms"] = [gold_by_case[case_id]]
    return rows


async def _load_events_from_db(conn: Any, trade_date: str, limit: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            ne.id AS event_id,
            ne.news_id,
            COALESCE(ne.title, nr.title, '') AS title,
            COALESCE(ne.summary, nr.summary, nr.content, '') AS summary,
            COALESCE(nr.content, nr.summary, ne.summary, '') AS content,
            COALESCE(ne.event_type, '') AS event_type,
            COALESCE(ne.entities, '[]'::jsonb) AS entities,
            COALESCE(ne.occurred_at, nr.publish_time, nr.created_at) AS occurred_at
        FROM news_event ne
        LEFT JOIN news_raw nr ON nr.id = ne.news_id
        WHERE COALESCE(ne.occurred_at, nr.publish_time, nr.created_at)::date = $1::date
        ORDER BY COALESCE(ne.occurred_at, nr.publish_time, nr.created_at) DESC NULLS LAST, ne.id DESC
        LIMIT $2
        """,
        trade_date,
        limit,
    )
    return [dict(row) for row in rows]


async def _load_v1_profiles(conn: Any) -> list[ThemeProfile]:
    rows = await conn.fetch(
        """
        SELECT
            t.subject_key,
            COALESCE(fc.category_name, t.concept, t.subject_key) AS subject_name,
            t.concept,
            t.semantic_type,
            t.strategy_type,
            t.ontology_json,
            t.gate_json,
            t.must_terms,
            t.should_terms,
            t.not_terms,
            t.strong_terms,
            t.weak_terms,
            t.negative_terms,
            t.search_text,
            t.quality,
            e.rerank_text,
            e.core_anchors,
            e.supporting_entities
        FROM theme_gate_profile t
        LEFT JOIN financial_categories fc
          ON fc.source_system = 'jyhf' AND fc.source_id::text = t.subject_key
        LEFT JOIN theme_profile_ext e ON e.subject_key = t.subject_key
        ORDER BY t.subject_key
        """
    )
    profiles: list[ThemeProfile] = []
    for row in rows:
        data = dict(row)
        ontology = load_json(data.get("ontology_json"), {})
        gate = load_json(data.get("gate_json"), {})
        aliases = unique([safe_str(data.get("subject_name")), safe_str(data.get("concept"))])
        profiles.append(
            ThemeProfile(
                subject_key=safe_str(data.get("subject_key")),
                subject_name=safe_str(data.get("subject_name")),
                theme_master_id=None,
                concept=safe_str(data.get("concept")),
                semantic_type=safe_str(data.get("semantic_type")),
                strategy_type=safe_str(data.get("strategy_type")),
                ontology_json=ontology,
                gate_json=gate,
                must_terms=normalize_list(data.get("must_terms")),
                should_terms=normalize_list(data.get("should_terms")),
                not_terms=normalize_list(data.get("not_terms")),
                strong_terms=normalize_list(data.get("strong_terms")),
                weak_terms=normalize_list(data.get("weak_terms")),
                negative_terms=normalize_list(data.get("negative_terms")),
                search_text=safe_str(data.get("search_text")),
                quality=safe_str(data.get("quality")),
                rerank_text=safe_str(data.get("rerank_text")),
                aliases=aliases,
                entity_hints=normalize_list(data.get("supporting_entities")),
                core_objects=normalize_list(data.get("core_anchors")),
            )
        )
    return profiles


async def _load_v2_profiles(conn: Any, status: str | None) -> list[ThemeProfile]:
    if not await table_exists(conn, "theme_profile_v2"):
        return []
    where = "WHERE status = $1" if status else ""
    args = [status] if status else []
    rows = await conn.fetch(f"SELECT * FROM theme_profile_v2 {where} ORDER BY subject_key", *args)
    profiles: list[ThemeProfile] = []
    for row in rows:
        data = dict(row)
        profiles.append(
            ThemeProfile(
                subject_key=safe_str(data.get("subject_key")),
                subject_name=safe_str(data.get("subject_name")),
                theme_master_id=None,
                concept=safe_str(data.get("subject_name")),
                semantic_type="profile_v2",
                strategy_type="event_driven",
                ontology_json={},
                gate_json={},
                must_terms=normalize_list(data.get("must_terms")),
                should_terms=normalize_list(data.get("should_terms")),
                not_terms=[],
                strong_terms=normalize_list(data.get("strong_terms")),
                weak_terms=normalize_list(data.get("weak_terms")),
                negative_terms=normalize_list(data.get("negative_terms")),
                search_text=" ".join(
                    normalize_list(data.get("entity_anchors"))
                    + normalize_list(data.get("domain_anchors"))
                    + normalize_list(data.get("product_anchors"))
                    + normalize_list(data.get("technology_anchors"))
                    + normalize_list(data.get("should_terms"))
                ),
                quality="v2",
                rerank_text=" ".join(
                    normalize_list(data.get("entity_anchors"))
                    + normalize_list(data.get("domain_anchors"))
                    + normalize_list(data.get("product_anchors"))
                    + normalize_list(data.get("technology_anchors"))
                    + normalize_list(data.get("must_terms"))
                    + normalize_list(data.get("strong_terms"))
                ),
                aliases=normalize_list(data.get("aliases")),
                entity_hints=normalize_list(data.get("entity_anchors")),
                core_objects=unique(
                    normalize_list(data.get("entity_anchors"))
                    + normalize_list(data.get("domain_anchors"))
                    + normalize_list(data.get("product_anchors"))
                    + normalize_list(data.get("technology_anchors"))
                ),
            )
        )
    return profiles


def _gold_hit(result, gold_terms: list[str]) -> bool:
    if not gold_terms:
        return False
    names = [safe_str(result.matched_theme_name)] + [safe_str(item.get("theme_name")) for item in result.related_matches]
    joined = " ".join(names)
    expanded = unique(alias for term in gold_terms for alias in ALIAS_MAP.get(term, [term]))
    return any(term and term in joined for term in expanded)


def _matches_gold_terms(name: str, gold_terms: list[str]) -> bool:
    expanded = unique(alias for term in gold_terms for alias in ALIAS_MAP.get(term, [term]))
    return any(term and name and (term in name or name in term) for term in expanded)


def _theme_set_recall(result, gold_terms: list[str], k: int) -> bool:
    if not gold_terms:
        return False
    names = [safe_str(result.matched_theme_name)] + [safe_str(item.get("theme_name")) for item in result.related_matches]
    joined = " ".join(name for name in names[:k] if name)
    expanded = unique(alias for term in gold_terms for alias in ALIAS_MAP.get(term, [term]))
    return any(term and term in joined for term in expanded)


def _wrong_related_count(result, gold_terms: list[str]) -> int:
    if not gold_terms:
        return 0
    return sum(
        1
        for item in result.related_matches or []
        if safe_str(item.get("theme_name")) and not _matches_gold_terms(safe_str(item.get("theme_name")), gold_terms)
    )


async def _load_v2_diagnostics(conn: Any, status: str | None) -> dict[str, Any]:
    if not await table_exists(conn, "theme_profile_v2"):
        return {
            "theme_profile_version": "v2",
            "v2_loaded_count": 0,
            "v2_review_subject_keys": [],
            "v2_status": status,
        }
    active_rows = await conn.fetch(
        "SELECT subject_key FROM theme_profile_v2 WHERE ($1::text IS NULL OR status = $1) ORDER BY subject_key",
        status,
    )
    review_rows = await conn.fetch(
        "SELECT subject_key FROM theme_profile_v2 WHERE status = 'review' ORDER BY subject_key"
    )
    status_rows = await conn.fetch("SELECT status, count(*) AS count FROM theme_profile_v2 GROUP BY status ORDER BY status")
    return {
        "theme_profile_version": "v2",
        "v2_status": status,
        "v2_loaded_count": len(active_rows),
        "v2_active_subject_keys": [safe_str(row["subject_key"]) for row in active_rows],
        "v2_review_subject_keys": [safe_str(row["subject_key"]) for row in review_rows],
        "v2_status_counts": {safe_str(row["status"]): int(row["count"] or 0) for row in status_rows},
    }


async def _compare_hard_negatives(
    cases: list[dict[str, Any]],
    v1_engine: ThemeMatchEngine,
    v2_engine: ThemeMatchEngine,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    v1_reject_count = 0
    v2_reject_count = 0
    for idx, case in enumerate(cases, start=1):
        request = request_from_hard_negative(case, idx)
        v1 = await v1_engine.match_event(request)
        v2 = await v2_engine.match_event(request)
        v1_rejected = is_hard_negative_rejected(v1, case)
        v2_rejected = is_hard_negative_rejected(v2, case)
        if v1_rejected:
            v1_reject_count += 1
        if v2_rejected:
            v2_reject_count += 1
        if v2_rejected and not v1_rejected:
            comparison = "improved"
        elif v1_rejected and not v2_rejected:
            comparison = "regressed"
        elif v1_rejected == v2_rejected:
            comparison = "unchanged"
        else:
            comparison = "needs_review"
        rows.append(
            {
                "case_id": safe_str(case.get("case_id")),
                "tags": normalize_list(case.get("tags")),
                "positive_subject_keys": normalize_list(case.get("positive_subject_keys")),
                "must_not_subject_keys": normalize_list(case.get("must_not_subject_keys")),
                "must_not_theme_names": normalize_list(case.get("must_not_theme_names")),
                "comparison": comparison,
                **hard_negative_row(case, v1, "v1"),
                **hard_negative_row(case, v2, "v2"),
            }
        )
    total = len(rows)
    summary = {
        "hard_negative_total": total,
        "v1_hard_negative_reject_rate": round(v1_reject_count / max(1, total), 4),
        "v2_hard_negative_reject_rate": round(v2_reject_count / max(1, total), 4),
        "improved": sum(1 for row in rows if row["comparison"] == "improved"),
        "regressed": sum(1 for row in rows if row["comparison"] == "regressed"),
        "unchanged": sum(1 for row in rows if row["comparison"] == "unchanged"),
        "needs_review": sum(1 for row in rows if row["comparison"] == "needs_review"),
        "v1_wrong_related_count": sum(int(row.get("v1_wrong_related_count") or 0) for row in rows),
        "v2_wrong_related_count": sum(int(row.get("v2_wrong_related_count") or 0) for row in rows),
        "v1_generic_only_related_count": sum(int(row.get("v1_generic_only_related_count") or 0) for row in rows),
        "v2_generic_only_related_count": sum(int(row.get("v2_generic_only_related_count") or 0) for row in rows),
    }
    return rows, summary


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ThemeMatchEngine v1 profiles with theme_profile_v2 profiles.")
    add_db_args(parser)
    parser.add_argument("--events-jsonl", type=Path)
    parser.add_argument("--gold-labels-jsonl", type=Path)
    parser.add_argument("--hard-negative-file", type=Path)
    parser.add_argument("--gate-only", action="store_true", help="Skip dense/rerank embeddings for quick local gate checks.")
    parser.add_argument("--trade-date")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--v2-status")
    parser.add_argument("--v2-fallback-to-v1", action="store_true")
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_v1_v2_compare_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    out_dir = args.output_dir or default_output_dir(args.run_id)
    read_conn = await connect(args.read_db_name)
    write_conn = await connect(args.write_db_name)
    try:
        if args.events_jsonl:
            events = _load_events_jsonl(args.events_jsonl, args.limit, args.gold_labels_jsonl)
        elif args.trade_date:
            events = await _load_events_from_db(write_conn, args.trade_date, args.limit)
        elif args.hard_negative_file:
            events = []
        else:
            raise SystemExit("必须传 --events-jsonl、--trade-date 或 --hard-negative-file")
        v1_profiles = await _load_v1_profiles(read_conn)
        v2_profiles = await _load_v2_profiles(write_conn, args.v2_status)
        v2_diagnostics = await _load_v2_diagnostics(write_conn, args.v2_status)
        if not v2_profiles:
            raise SystemExit("theme_profile_v2 无可用数据，请先运行 build_theme_profile_v2.py --write-db")
        raw_v2_count = len(v2_profiles)
        if args.v2_fallback_to_v1:
            merged = {profile.subject_key: profile for profile in v1_profiles}
            for profile in v2_profiles:
                merged[profile.subject_key] = profile
            v2_profiles = list(merged.values())
        v2_diagnostics.update(
            {
                "v1_profile_count": len(v1_profiles),
                "v2_profile_count_after_fallback": len(v2_profiles),
                "v2_raw_profile_count": raw_v2_count,
                "v1_fallback_count": max(0, len(v2_profiles) - raw_v2_count) if args.v2_fallback_to_v1 else 0,
                "v2_fallback_to_v1": bool(args.v2_fallback_to_v1),
            }
        )
        v1_engine = ThemeMatchEngine(_StaticRepo(v1_profiles))
        v2_engine = ThemeMatchEngine(_StaticRepo(v2_profiles))
        disable_llm_for_engine(v1_engine, gate_only=args.gate_only)
        disable_llm_for_engine(v2_engine, gate_only=args.gate_only)
        rows: list[dict[str, Any]] = []
        for row in events:
            request = _request_from_row(row)
            gold_terms = normalize_list(row.get("gold_theme_name") or row.get("gold_terms"))
            v1 = await v1_engine.match_event(request)
            v2 = await v2_engine.match_event(request)
            v1_hit = _gold_hit(v1, gold_terms)
            v2_hit = _gold_hit(v2, gold_terms)
            v1_recall5 = _theme_set_recall(v1, gold_terms, 5)
            v2_recall5 = _theme_set_recall(v2, gold_terms, 5)
            if v2_hit and not v1_hit:
                status = "improved"
            elif v1_hit and not v2_hit:
                status = "regressed"
            elif v1.decision == v2.decision and v1.matched_subject_key == v2.matched_subject_key:
                status = "unchanged"
            else:
                status = "needs_review"
            rows.append(
                {
                    "event_id": request.event_id,
                    "title": request.title,
                    "gold_terms": gold_terms,
                    "v1_decision": v1.decision,
                    "v1_subject_key": v1.matched_subject_key,
                    "v1_theme_name": v1.matched_theme_name,
                    "v1_related_count": len(v1.related_matches),
                    "v1_related_theme_names": [safe_str(item.get("theme_name")) for item in v1.related_matches],
                    "v1_theme_set_recall_at_5": v1_recall5,
                    "v1_primary_hit": v1_hit,
                    "v1_wrong_related_count": _wrong_related_count(v1, gold_terms),
                    "v1_generic_only_related_count": count_generic_only_related(v1),
                    "v2_decision": v2.decision,
                    "v2_subject_key": v2.matched_subject_key,
                    "v2_theme_name": v2.matched_theme_name,
                    "v2_related_count": len(v2.related_matches),
                    "v2_related_theme_names": [safe_str(item.get("theme_name")) for item in v2.related_matches],
                    "v2_theme_set_recall_at_5": v2_recall5,
                    "v2_primary_hit": v2_hit,
                    "v2_wrong_related_count": _wrong_related_count(v2, gold_terms),
                    "v2_generic_only_related_count": count_generic_only_related(v2),
                    "recall5_regressed": bool(v1_recall5 and not v2_recall5),
                    "comparison": status,
                }
            )
        hard_rows: list[dict[str, Any]] = []
        hard_summary: dict[str, Any] = {}
        if args.hard_negative_file:
            hard_rows, hard_summary = await _compare_hard_negatives(
                read_jsonl(args.hard_negative_file)[: args.limit],
                v1_engine,
                v2_engine,
            )
        summary = {
            "total": len(rows),
            "improved": sum(1 for row in rows if row["comparison"] == "improved"),
            "regressed": sum(1 for row in rows if row["comparison"] == "regressed"),
            "unchanged": sum(1 for row in rows if row["comparison"] == "unchanged"),
            "needs_review": sum(1 for row in rows if row["comparison"] == "needs_review"),
            "v1_generic_only_related_count": sum(int(row.get("v1_generic_only_related_count") or 0) for row in rows),
            "v2_generic_only_related_count": sum(int(row.get("v2_generic_only_related_count") or 0) for row in rows),
            "v1_wrong_related_count": sum(int(row.get("v1_wrong_related_count") or 0) for row in rows),
            "v2_wrong_related_count": sum(int(row.get("v2_wrong_related_count") or 0) for row in rows),
            "recall5_regressed_count": sum(1 for row in rows if row.get("recall5_regressed")),
            "v1_theme_set_recall@5": round(
                sum(1 for row in rows if row.get("v1_theme_set_recall_at_5")) / max(1, len(rows)),
                4,
            ),
            "v2_theme_set_recall@5": round(
                sum(1 for row in rows if row.get("v2_theme_set_recall_at_5")) / max(1, len(rows)),
                4,
            ),
            **v2_diagnostics,
            **hard_summary,
        }
        write_jsonl(out_dir / "theme_profile_v1_v2_compare.jsonl", rows)
        write_csv(out_dir / "theme_profile_v1_v2_compare.csv", rows)
        regression_rows = [
            row
            for row in rows
            if row.get("comparison") == "regressed" or row.get("recall5_regressed") or int(row.get("v2_wrong_related_count") or 0) > int(row.get("v1_wrong_related_count") or 0)
        ]
        write_jsonl(out_dir / "regression_cases.jsonl", regression_rows)
        write_csv(out_dir / "regression_cases.csv", regression_rows)
        if hard_rows:
            write_jsonl(out_dir / "hard_negative_eval_report.jsonl", hard_rows)
            write_csv(out_dir / "v1_v2_compare_report.csv", hard_rows)
        (out_dir / "theme_profile_v1_v2_compare_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "phase2_summary.md").write_text(
            "\n".join(
                [
                    "# Theme Profile v2 Phase 2 Summary",
                    "",
                    f"- total_events: {summary.get('total', 0)}",
                    f"- v1_theme_set_recall@5: {summary.get('v1_theme_set_recall@5')}",
                    f"- v2_theme_set_recall@5: {summary.get('v2_theme_set_recall@5')}",
                    f"- recall5_regressed_count: {summary.get('recall5_regressed_count', 0)}",
                    f"- v2_loaded_count: {summary.get('v2_loaded_count', 0)}",
                    f"- v2_review_subject_keys: {summary.get('v2_review_subject_keys', [])}",
                    f"- v1_fallback_count: {summary.get('v1_fallback_count', 0)}",
                    f"- hard_negative_total: {summary.get('hard_negative_total', 0)}",
                    f"- v1_hard_negative_reject_rate: {summary.get('v1_hard_negative_reject_rate')}",
                    f"- v2_hard_negative_reject_rate: {summary.get('v2_hard_negative_reject_rate')}",
                    f"- improved: {summary.get('improved', 0)}",
                    f"- regressed: {summary.get('regressed', 0)}",
                    f"- unchanged: {summary.get('unchanged', 0)}",
                    f"- needs_review: {summary.get('needs_review', 0)}",
                    f"- v1_wrong_related_count: {summary.get('v1_wrong_related_count', 0)}",
                    f"- v2_wrong_related_count: {summary.get('v2_wrong_related_count', 0)}",
                    f"- v1_generic_only_related_count: {summary.get('v1_generic_only_related_count', 0)}",
                    f"- v2_generic_only_related_count: {summary.get('v2_generic_only_related_count', 0)}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print({**summary, "out_dir": str(out_dir)})
    finally:
        await read_conn.close()
        await write_conn.close()


if __name__ == "__main__":
    run_async(main())
