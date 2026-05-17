from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.services.theme_match_engine import ThemeMatchEngine
from theme_service.services.theme_match_types import ThemeMatchRequest, ThemeProfile
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
    return ThemeMatchRequest(
        event_id=int(row.get("event_id") or row.get("id") or 0),
        news_id=int(row.get("news_id") or 0),
        title=safe_str(row.get("title")),
        content=safe_str(row.get("content") or row.get("summary")),
        summary=safe_str(row.get("summary")),
        event_type=safe_str(row.get("event_type")),
        entities=normalize_list(row.get("entities")),
        raw_event_json=row,
        trace_id=safe_str(row.get("trace_id") or row.get("case_id")),
    )


async def _load_events_from_db(conn: Any, trade_date: str, limit: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id AS event_id, news_id, title, summary, content, event_type, entities, occurred_at
        FROM news_event
        WHERE occurred_at::date = $1::date
        ORDER BY occurred_at DESC NULLS LAST, id DESC
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
    return any(term and term in joined for term in gold_terms)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ThemeMatchEngine v1 profiles with theme_profile_v2 profiles.")
    add_db_args(parser)
    parser.add_argument("--events-jsonl", type=Path)
    parser.add_argument("--trade-date")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--v2-status")
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_v1_v2_compare_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    out_dir = args.output_dir or default_output_dir(args.run_id)
    read_conn = await connect(args.read_db_name)
    write_conn = await connect(args.write_db_name)
    try:
        if args.events_jsonl:
            events = read_jsonl(args.events_jsonl)[: args.limit]
        elif args.trade_date:
            events = await _load_events_from_db(write_conn, args.trade_date, args.limit)
        else:
            raise SystemExit("必须传 --events-jsonl 或 --trade-date")
        v1_profiles = await _load_v1_profiles(read_conn)
        v2_profiles = await _load_v2_profiles(write_conn, args.v2_status)
        if not v2_profiles:
            raise SystemExit("theme_profile_v2 无可用数据，请先运行 build_theme_profile_v2.py --write-db")
        v1_engine = ThemeMatchEngine(_StaticRepo(v1_profiles))
        v2_engine = ThemeMatchEngine(_StaticRepo(v2_profiles))
        rows: list[dict[str, Any]] = []
        for row in events:
            request = _request_from_row(row)
            gold_terms = normalize_list(row.get("gold_theme_name") or row.get("gold_terms"))
            v1 = await v1_engine.match_event(request)
            v2 = await v2_engine.match_event(request)
            v1_hit = _gold_hit(v1, gold_terms)
            v2_hit = _gold_hit(v2, gold_terms)
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
                    "v2_decision": v2.decision,
                    "v2_subject_key": v2.matched_subject_key,
                    "v2_theme_name": v2.matched_theme_name,
                    "v2_related_count": len(v2.related_matches),
                    "comparison": status,
                }
            )
        summary = {
            "total": len(rows),
            "improved": sum(1 for row in rows if row["comparison"] == "improved"),
            "regressed": sum(1 for row in rows if row["comparison"] == "regressed"),
            "unchanged": sum(1 for row in rows if row["comparison"] == "unchanged"),
            "needs_review": sum(1 for row in rows if row["comparison"] == "needs_review"),
        }
        write_jsonl(out_dir / "theme_profile_v1_v2_compare.jsonl", rows)
        write_csv(out_dir / "theme_profile_v1_v2_compare.csv", rows)
        (out_dir / "theme_profile_v1_v2_compare_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print({**summary, "out_dir": str(out_dir)})
    finally:
        await read_conn.close()
        await write_conn.close()


if __name__ == "__main__":
    run_async(main())
