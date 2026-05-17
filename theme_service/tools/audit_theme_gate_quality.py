from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.profile_quality_common import (
    add_db_args,
    connect,
    default_output_dir,
    is_generic_term,
    jaccard,
    load_json,
    normalize_list,
    safe_str,
    split_generic,
    table_exists,
    unique,
    write_csv,
    write_jsonl,
)


def _read_gate(path: Path) -> dict[str, Any]:
    obj = load_json(path.read_text(encoding="utf-8"), {})
    subject_key = safe_str(obj.get("subject_key") or obj.get("subject_id") or path.name.split("_", 1)[0])
    return {
        "subject_key": subject_key,
        "must": normalize_list(obj.get("must")),
        "should": normalize_list(obj.get("should")),
        "not_terms": normalize_list(obj.get("not")),
        "strong": normalize_list(obj.get("strong")),
        "aliases": normalize_list(obj.get("aliases")),
        "entity_hints": normalize_list(obj.get("entity_hints")),
        "core_objects": normalize_list(obj.get("core_objects")),
        "evidence_refs": obj.get("evidence_refs") if isinstance(obj.get("evidence_refs"), list) else [],
        "quality": safe_str(obj.get("quality")),
        "semantic_type": safe_str(obj.get("semantic_type")),
        "strategy_type": safe_str(obj.get("strategy_type")),
        "source_file": str(path),
    }


def _load_subject_gates(gate_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not gate_dir.exists():
        return out
    for path in sorted(gate_dir.glob("*_gate.json")):
        gate = _read_gate(path)
        if gate["subject_key"]:
            out[gate["subject_key"]] = gate
    return out


async def _load_db_profiles(conn: Any) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            t.subject_key,
            COALESCE(fc.category_name, t.concept, t.subject_key) AS subject_name,
            t.concept,
            t.semantic_type,
            t.strategy_type,
            t.must_terms,
            t.should_terms,
            t.not_terms,
            t.strong_terms,
            t.weak_terms,
            t.negative_terms,
            t.ontology_json,
            t.gate_json,
            t.search_text,
            t.quality,
            e.summary,
            e.core_anchors,
            e.supporting_entities,
            e.representative_events,
            e.rerank_text
        FROM theme_gate_profile t
        LEFT JOIN financial_categories fc
          ON fc.source_system = 'jyhf' AND fc.source_id::text = t.subject_key
        LEFT JOIN theme_profile_ext e ON e.subject_key = t.subject_key
        ORDER BY t.subject_key
        """
    )
    return {safe_str(row["subject_key"]): dict(row) for row in rows}


async def _load_stock_pool_sizes(conn: Any) -> dict[str, int]:
    if not await table_exists(conn, "subject_stock_daily_snapshot"):
        return {}
    rows = await conn.fetch(
        """
        WITH latest AS (
            SELECT subject_key, max(trade_date) AS trade_date
            FROM subject_stock_daily_snapshot
            GROUP BY subject_key
        )
        SELECT s.subject_key, count(DISTINCT s.stock_id) AS stock_pool_size
        FROM subject_stock_daily_snapshot s
        JOIN latest l ON l.subject_key = s.subject_key AND l.trade_date = s.trade_date
        GROUP BY s.subject_key
        """
    )
    return {safe_str(row["subject_key"]): int(row["stock_pool_size"] or 0) for row in rows}


async def _load_recent_event_counts(conn: Any, recent_days: int) -> dict[str, int]:
    if not await table_exists(conn, "event_subject_map"):
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=recent_days)
    rows = await conn.fetch(
        """
        SELECT subject_key, count(*) AS event_count
        FROM event_subject_map
        WHERE created_at >= $1
        GROUP BY subject_key
        """,
        since,
    )
    return {safe_str(row["subject_key"]): int(row["event_count"] or 0) for row in rows}


def _aliases_from_profile(row: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    ontology = load_json(row.get("ontology_json"), {})
    gate = load_json(row.get("gate_json"), {})
    for key in ("aliases", "synonyms", "alias", "same_as"):
        aliases.extend(normalize_list(ontology.get(key)))
        aliases.extend(normalize_list(gate.get(key)))
    aliases.extend([safe_str(row.get("subject_name")), safe_str(row.get("concept"))])
    return unique(aliases)


def _audit_terms(gate: dict[str, Any], db_row: dict[str, Any]) -> dict[str, Any]:
    must = unique(normalize_list(gate.get("must")) + normalize_list(db_row.get("must_terms")))
    strong = unique(normalize_list(gate.get("strong")) + normalize_list(db_row.get("strong_terms")))
    should = unique(normalize_list(gate.get("should")) + normalize_list(db_row.get("should_terms")))
    aliases = unique(normalize_list(gate.get("aliases")) + _aliases_from_profile(db_row))
    core_objects = unique(normalize_list(gate.get("core_objects")) + normalize_list(db_row.get("core_anchors")))
    negative = unique(normalize_list(gate.get("not_terms")) + normalize_list(db_row.get("not_terms")) + normalize_list(db_row.get("negative_terms")))
    anchor_candidates = unique([safe_str(db_row.get("subject_name")), safe_str(db_row.get("concept")), *aliases, *must, *strong, *core_objects])
    anchors, generic = split_generic(anchor_candidates)
    must_generic = [term for term in must if is_generic_term(term)]
    alias_generic = [term for term in aliases if is_generic_term(term)]
    no_anchor_candidates = unique([term for term in [*must_generic, *alias_generic, *should] if is_generic_term(term)])
    return {
        "must": must,
        "strong": strong,
        "should": should,
        "aliases": aliases,
        "core_objects": core_objects,
        "negative": negative,
        "anchor_candidates": anchor_candidates,
        "anchors": anchors,
        "generic": generic,
        "must_generic": must_generic,
        "alias_generic": alias_generic,
        "no_anchor_candidates": no_anchor_candidates,
    }


def _nearby_overlap(subject_key: str, term_map: dict[str, set[str]]) -> tuple[float, list[str]]:
    scored: list[tuple[float, str]] = []
    terms = term_map.get(subject_key, set())
    for other_key, other_terms in term_map.items():
        if other_key == subject_key:
            continue
        score = jaccard(terms, other_terms)
        if score > 0:
            scored.append((score, other_key))
    scored.sort(reverse=True)
    return (round(scored[0][0], 4) if scored else 0.0, [key for _, key in scored[:10]])


def _risk_row(
    subject_key: str,
    db_row: dict[str, Any],
    gate: dict[str, Any],
    terms: dict[str, Any],
    nearby_score: float,
    nearby_keys: list[str],
    stock_pool_size: int,
    recent_heat_score: float,
) -> dict[str, Any]:
    anchor_count = len(terms["anchors"])
    generic_anchor_ratio = round(len(terms["generic"]) / max(1, len(terms["anchor_candidates"])), 4)
    negative_count = len(terms["negative"])
    false_positive_risk = round(
        min(
            1.0,
            generic_anchor_ratio * 0.40
            + min(len(terms["must_generic"]) / 4, 1.0) * 0.25
            + min(len(terms["alias_generic"]) / 4, 1.0) * 0.15
            + nearby_score * 0.15
            + (0.10 if anchor_count < 3 else 0.0)
            + (0.08 if negative_count == 0 else 0.0),
        ),
        4,
    )
    priority_score = round(
        min(
            100.0,
            false_positive_risk * 58
            + recent_heat_score * 18
            + min(stock_pool_size / 80, 1.0) * 14
            + (10 if terms["must_generic"] or terms["alias_generic"] else 0),
        ),
        2,
    )
    return {
        "subject_key": subject_key,
        "subject_name": safe_str(db_row.get("subject_name") or db_row.get("concept") or subject_key),
        "concept": safe_str(db_row.get("concept")),
        "semantic_type": safe_str(db_row.get("semantic_type") or gate.get("semantic_type")),
        "strategy_type": safe_str(db_row.get("strategy_type") or gate.get("strategy_type")),
        "source_gate_file": safe_str(gate.get("source_file")),
        "generic_anchor_ratio": generic_anchor_ratio,
        "must_generic_count": len(terms["must_generic"]),
        "alias_generic_count": len(terms["alias_generic"]),
        "anchor_count": anchor_count,
        "negative_count": negative_count,
        "nearby_overlap_score": nearby_score,
        "nearby_subject_keys": nearby_keys,
        "stock_pool_size": stock_pool_size,
        "recent_heat_score": round(recent_heat_score, 4),
        "false_positive_risk": false_positive_risk,
        "priority_score": priority_score,
        "must_generic_terms": terms["must_generic"],
        "alias_generic_terms": terms["alias_generic"],
        "generic_terms": terms["generic"],
        "no_anchor_candidates": terms["no_anchor_candidates"],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit legacy subject_gates/theme_gate_profile quality and produce Top50 v2 rebuild list.")
    add_db_args(parser)
    parser.add_argument("--gate-dir", type=Path, default=Path("subject_gates"))
    parser.add_argument("--run-id", default=datetime.now().strftime("theme_gate_audit_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--recent-days", type=int, default=30)
    parser.add_argument("--pin-subject-key", action="append", default=[], help="强制纳入 rebuild list 的已知高风险 subject_key，可重复传")
    args = parser.parse_args()

    out_dir = args.output_dir or default_output_dir(args.run_id)
    read_conn = await connect(args.read_db_name)
    write_conn = None
    try:
        subject_gates = _load_subject_gates(args.gate_dir)
        db_profiles = await _load_db_profiles(read_conn)
        stock_sizes = await _load_stock_pool_sizes(read_conn)
        write_conn = await connect(args.write_db_name)
        recent_counts = await _load_recent_event_counts(write_conn, args.recent_days)
        max_recent = max(recent_counts.values() or [0])

        all_keys = sorted(set(subject_gates) | set(db_profiles))
        audited_terms: dict[str, dict[str, Any]] = {}
        term_map: dict[str, set[str]] = {}
        for key in all_keys:
            terms = _audit_terms(subject_gates.get(key, {}), db_profiles.get(key, {}))
            audited_terms[key] = terms
            term_map[key] = set(terms["anchors"])

        rows: list[dict[str, Any]] = []
        for key in all_keys:
            nearby_score, nearby_keys = _nearby_overlap(key, term_map)
            recent_heat_score = recent_counts.get(key, 0) / max(1, max_recent)
            rows.append(
                _risk_row(
                    key,
                    db_profiles.get(key, {}),
                    subject_gates.get(key, {}),
                    audited_terms[key],
                    nearby_score,
                    nearby_keys,
                    stock_sizes.get(key, 0),
                    recent_heat_score,
                )
            )

        rows.sort(key=lambda row: (-float(row["priority_score"]), -float(row["false_positive_risk"]), row["subject_key"]))
        pinned = [row for row in rows if row["subject_key"] in set(args.pin_subject_key or [])]
        pinned_keys = {row["subject_key"] for row in pinned}
        top_rows = pinned + [row for row in rows if row["subject_key"] not in pinned_keys][: max(0, args.top_n - len(pinned))]
        pollution_rows = [
            row
            for row in rows
            if row["must_generic_count"] > 0 or row["alias_generic_count"] > 0 or row["generic_anchor_ratio"] > 0
        ]
        pollution_counter = Counter()
        for row in pollution_rows:
            for term in row["must_generic_terms"] + row["alias_generic_terms"]:
                pollution_counter[term] += 1
        write_jsonl(out_dir / "theme_profile_audit_report.jsonl", rows)
        write_csv(out_dir / "generic_pollution_report.csv", pollution_rows)
        (out_dir / "top50_rebuild_list.json").write_text(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "read_db": args.read_db_name,
                    "write_db_for_history": args.write_db_name,
                    "profile_count": len(rows),
                    "top_n": len(top_rows),
                    "subjects": top_rows,
                    "generic_term_counts": dict(pollution_counter.most_common(50)),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(
            {
                "profile_count": len(rows),
                "subject_gate_file_count": len(subject_gates),
                "top_n": len(top_rows),
                "generic_pollution_count": len(pollution_rows),
                "out_dir": str(out_dir),
            }
        )
    finally:
        await read_conn.close()
        if write_conn:
            await write_conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
