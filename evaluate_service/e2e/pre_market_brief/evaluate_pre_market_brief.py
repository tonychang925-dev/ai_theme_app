from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import read_jsonl, write_json
else:
    from .common import read_jsonl, write_json

ALIAS_MAP: dict[str, list[str]] = {
    "AI/AR眼镜": ["AI/AR眼镜", "AI智能眼镜", "AR眼镜", "智能眼镜", "XR眼镜"],
    "SpaceX": ["SpaceX", "星链", "商业航天", "卫星互联网", "星舰"],
    "可控核聚变": ["可控核聚变", "核聚变", "人造太阳"],
    "对日制裁": ["对日制裁", "中日关系", "出口管制", "反制日本"],
    "稀土永磁": ["稀土永磁", "稀土", "中重稀土", "稀土出口管制"],
    "卫星互联": ["卫星互联", "卫星互联网", "低轨卫星", "商业航天", "SpaceX", "星链"],
    "液冷数据中心": ["液冷数据中心", "液冷", "数据中心液冷", "服务器液冷"],
    "光刻胶": ["光刻胶", "半导体光刻胶", "KrF光刻胶", "EUV光刻胶"],
    "AI智能体Manus": ["AI智能体Manus", "Manus", "AI智能体", "智能体"],
    # ── Phase 4.6 P0-C2: 海洋经济 neighbor map ──
    # 深海经济 is a valid sub-domain of 海洋经济 (deep-sea economy ⊆ marine economy).
    # Events about broad marine economy policy/planning may match to 深海经济
    # because the two subjects share "海洋" + "经济" semantics.
    "海洋经济": [
        "海洋经济", "深海经济", "海工装备", "海洋工程",
        "航运", "港口", "海洋牧场", "海上风电",
    ],
}

COMMERCIAL_SPACE_TERMS = {
    "SpaceX",
    "星链",
    "星舰",
    "卫星互联网",
    "卫星互联",
    "商业航天",
    "蓝箭航天",
    "蓝箭航天IPO",
    "火箭",
    "运载火箭",
    "航天发射",
    "航天发射场",
    "广州商业航天",
    "商业航天8大IPO",
}
COMMERCIAL_SPACE_RELATED_LIMIT = 3


def _matches_gold(gold: str, candidate: str | None) -> bool:
    if not gold or not candidate:
        return False
    aliases = ALIAS_MAP.get(gold, [gold])
    return any(alias and (alias in candidate or candidate in alias) for alias in aliases)


def _is_commercial_space_neighbor(gold: str, primary: str | None, related: str | None) -> bool:
    """商业航天族群近邻单独计数，避免把合理扩展直接混入 wrong related。"""
    if not gold or not related:
        return False
    has_space_context = any(term in gold or term in (primary or "") for term in COMMERCIAL_SPACE_TERMS)
    has_space_related = any(term in related for term in COMMERCIAL_SPACE_TERMS)
    return has_space_context and has_space_related


def _load_snapshot(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "payload" in payload and isinstance(payload["payload"], dict):
        return payload["payload"]
    return payload if isinstance(payload, dict) else {}


def evaluate(
    *,
    gold_path: Path,
    trace_path: Path,
    snapshot_path: Path | None,
    out_dir: Path,
) -> dict[str, Any]:
    gold_rows = read_jsonl(gold_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    snapshot = _load_snapshot(snapshot_path)
    gold_by_case = {row["case_id"]: row["gold_theme_name"] for row in gold_rows}

    evaluated_rows: list[dict[str, Any]] = []
    primary_hits = 0
    related_hits = 0
    recall3_hits = 0
    recall5_hits = 0
    human_review_count = 0
    unknown_count = 0
    wrong_related_count = 0
    neighbor_related_count = 0
    over_expanded_related_count = 0
    generic_only_related_count = 0
    llm_anchor_guard_count = 0
    wrong_related_rows: list[dict[str, Any]] = []

    for row in trace.get("rows", []):
        case_id = row.get("case_id")
        gold = gold_by_case.get(case_id)
        if not gold:
            continue
        primary_name = row.get("primary_theme_name")
        related_names = [name for name in row.get("related_theme_names", []) if name]
        theme_names = [name for name in [primary_name, *related_names] if name]
        primary_hit = _matches_gold(gold, primary_name)
        related_hit = any(_matches_gold(gold, name) for name in related_names)
        recall3_hit = any(_matches_gold(gold, name) for name in theme_names[:3])
        recall5_hit = any(_matches_gold(gold, name) for name in theme_names[:5])
        neighbor_related_names = [
            name for name in related_names if _is_commercial_space_neighbor(gold, primary_name, name)
        ]
        neighbor_related_count += len(neighbor_related_names)
        over_expanded_related_count += max(0, len(neighbor_related_names) - COMMERCIAL_SPACE_RELATED_LIMIT)
        wrong_items = [
            item
            for item in row.get("related_mappings", [])
            if not _matches_gold(gold, item.get("theme_name"))
            and not _is_commercial_space_neighbor(gold, primary_name, item.get("theme_name"))
        ]
        wrong_related_count += len(wrong_items)
        for item in wrong_items:
            wrong_related_rows.append(_wrong_related_attribution_row(row, item, gold, primary_name))
        generic_only_related_count += sum(
            1 for item in row.get("related_mappings", []) if _is_generic_only_related(item)
        )
        if row.get("review_reason") == "llm_accept_without_anchor_evidence":
            llm_anchor_guard_count += 1
        status = "unknown"
        if primary_hit:
            status = "exact_or_alias_primary"
        elif related_hit:
            status = "alias_related"
        elif row.get("review_status"):
            status = "human_review"
            human_review_count += 1
        elif not theme_names:
            unknown_count += 1
        primary_hits += int(primary_hit)
        related_hits += int(related_hit)
        recall3_hits += int(recall3_hit)
        recall5_hits += int(recall5_hit)
        evaluated_rows.append(
            {
                "case_id": case_id,
                "gold_theme_name": gold,
                "primary_theme_name": primary_name,
                "related_theme_names": related_names,
                "status": status,
            }
        )

    total = len(evaluated_rows)
    sections = snapshot.get("sections") or {}
    diagnostics = snapshot.get("diagnostics") or {}
    snapshot_name_quality = _snapshot_theme_name_quality(sections)
    accuracy_report = {
        "total": total,
        "primary_hit_count": primary_hits,
        "related_hit_count": related_hits,
        "theme_set_recall_at_3_count": recall3_hits,
        "theme_set_recall_at_5_count": recall5_hits,
        "primary_hit_rate": _rate(primary_hits, total),
        "related_hit_rate": _rate(related_hits, total),
        "theme_set_recall@3": _rate(recall3_hits, total),
        "theme_set_recall@5": _rate(recall5_hits, total),
        "human_review_count": human_review_count,
        "unknown_count": unknown_count,
        "wrong_related_count": wrong_related_count,
        "neighbor_related_count": neighbor_related_count,
        "over_expanded_related_count": over_expanded_related_count,
        "generic_only_related_count": generic_only_related_count,
        "llm_anchor_guard_count": llm_anchor_guard_count,
        "brief_major_event_count": len(sections.get("major_events") or []),
        "brief_theme_count": len(sections.get("matched_themes") or []),
        "brief_opportunity_count": len(sections.get("event_driven_opportunities") or []),
        **snapshot_name_quality,
        "performance": _extract_performance_summary(trace.get("counts", {})),
        "diagnostics": diagnostics,
    }
    stock_report = {
        "brief_opportunity_count": accuracy_report["brief_opportunity_count"],
        "opportunity_count": diagnostics.get("opportunity_count", accuracy_report["brief_opportunity_count"]),
    }
    write_json(out_dir / "accuracy_report.json", accuracy_report)
    write_json(out_dir / "stock_candidate_report.json", stock_report)
    _write_wrong_related_attribution(out_dir, wrong_related_rows)
    _write_confusion(out_dir / "confusion_matrix.csv", evaluated_rows)
    _write_summary(out_dir / "summary.md", accuracy_report, trace.get("counts", {}))
    return accuracy_report


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _is_generic_only_related(item: dict[str, Any]) -> bool:
    evidence = _extract_related_evidence(item)
    anchor_hits = evidence.get("anchor_hits") or []
    strong_hits = (
        evidence.get("theme_name_hit_terms")
        or evidence.get("object_hits")
        or evidence.get("must_hits")
        or evidence.get("strong_hits")
        or evidence.get("entity_hits")
    )
    support_hits = evidence.get("support_hits") or []
    return bool(support_hits) and not bool(anchor_hits) and not bool(strong_hits)


def _extract_related_evidence(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence_json") or {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    if isinstance(evidence, dict) and isinstance(evidence.get("related_match"), dict):
        evidence = evidence["related_match"].get("evidence") or {}
    if not isinstance(evidence, dict):
        return {}
    return evidence


def _wrong_related_attribution_row(
    trace_row: dict[str, Any],
    item: dict[str, Any],
    gold: str,
    primary_name: str | None,
) -> dict[str, Any]:
    evidence = _extract_related_evidence(item)
    hit_terms = evidence.get("hit_terms") or evidence.get("anchor_hits") or []
    hit_roles = evidence.get("hit_term_roles") if isinstance(evidence.get("hit_term_roles"), dict) else {}
    summary = evidence.get("evidence_summary") if isinstance(evidence.get("evidence_summary"), dict) else {}
    root_cause = _classify_wrong_related_root_cause(item, evidence)
    return {
        "case_id": trace_row.get("case_id"),
        "event_title": trace_row.get("event_title") or trace_row.get("title") or "",
        "gold_theme": gold,
        "primary_theme_name": primary_name or "",
        "wrong_subject_key": item.get("subject_key") or "",
        "wrong_theme_name": item.get("theme_name") or "",
        "confidence": item.get("confidence"),
        "match_reason": item.get("match_reason") or "",
        "source_profile_version": _profile_version_from_evidence(evidence),
        "evidence_summary": json.dumps(summary or evidence, ensure_ascii=False, default=str),
        "hit_terms": "|".join(str(x) for x in hit_terms),
        "hit_term_roles": "|".join(f"{k}:{v}" for k, v in hit_roles.items()),
        "root_cause": root_cause,
        "fix_action": _fix_action_for_root_cause(root_cause),
    }


def _profile_version_from_evidence(evidence: dict[str, Any]) -> str:
    version = evidence.get("profile_version") or evidence.get("source_profile_version")
    if version:
        return str(version)
    return "unknown"


def _classify_wrong_related_root_cause(item: dict[str, Any], evidence: dict[str, Any]) -> str:
    theme_name = str(item.get("theme_name") or "")
    hit_roles = evidence.get("hit_term_roles") if isinstance(evidence.get("hit_term_roles"), dict) else {}
    roles = set(str(v) for v in hit_roles.values())
    hit_terms = [str(x) for x in evidence.get("hit_terms") or evidence.get("anchor_hits") or []]
    if roles and roles <= {"source_org", "speaker", "organizer"}:
        return "source_org_as_anchor"
    if roles and roles <= {"location"}:
        return "location_as_anchor"
    if roles and roles <= {"support", "generic_short_term"}:
        return "matcher_related_gate_too_loose"
    if theme_name in {"半导体", "服务器", "数据中心", "证券", "深圳", "高温", "一带一路", "游戏", "港口"}:
        return "broad_policy_profile"
    if len(theme_name) <= 2:
        return "short_generic_theme"
    return "profile_boundary_missing"


def _fix_action_for_root_cause(root_cause: str) -> str:
    return {
        "source_org_as_anchor": "downgrade_source_org_terms_and_add_negative",
        "location_as_anchor": "downgrade_location_terms_and_add_location_strict_rule",
        "short_generic_theme": "add_short_theme_direct_hit_guard",
        "broad_policy_profile": "rebuild_profile_v2_with_strict_related_policy",
        "profile_boundary_missing": "rebuild_profile_v2_with_negative_terms",
        "matcher_related_gate_too_loose": "tighten_related_gate",
        "eval_alias_error": "update_alias_or_neighbor_map",
    }.get(root_cause, "manual_review")


def _write_wrong_related_attribution(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    path_jsonl = out_dir / "wrong_related_attribution_report.jsonl"
    path_csv = out_dir / "wrong_related_attribution_report.csv"
    with path_jsonl.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    if not rows:
        path_csv.write_text("", encoding="utf-8")
        return
    with path_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


DISPLAY_NAME_KEYS = {
    "theme_name",
    "subject_name",
    "matched_theme_name",
    "primary_theme_name",
    "latest_theme_name",
    "name",
}


def _snapshot_theme_name_quality(sections: dict[str, Any]) -> dict[str, int]:
    numeric_count = 0
    unnamed_count = 0
    subject_key_chip_count = 0

    def _is_numeric_name(value: Any) -> bool:
        text = str(value).strip() if value is not None else ""
        return bool(text) and text.isdigit()

    def _visit(value: Any) -> None:
        nonlocal numeric_count, unnamed_count, subject_key_chip_count
        if isinstance(value, list):
            for item in value:
                _visit(item)
            return
        if not isinstance(value, dict):
            return

        subject_key = str(value.get("subject_key") or value.get("matched_subject_key") or "").strip()
        saw_display_key = False
        for key in DISPLAY_NAME_KEYS:
            if key not in value:
                continue
            saw_display_key = True
            text = str(value.get(key) or "").strip()
            if not text:
                unnamed_count += 1
                continue
            if _is_numeric_name(text):
                numeric_count += 1
            if subject_key and text == subject_key:
                subject_key_chip_count += 1
        if subject_key and not saw_display_key and any(k in value for k in ("theme_id", "confidence", "event_count")):
            unnamed_count += 1

        for item in value.values():
            if isinstance(item, (dict, list)):
                _visit(item)

    _visit(sections)
    return {
        "numeric_theme_name_count": numeric_count,
        "unnamed_theme_count": unnamed_count,
        "subject_key_chip_count": subject_key_chip_count,
    }


def _write_confusion(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["case_id", "gold_theme_name", "primary_theme_name", "related_theme_names", "status"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "related_theme_names": "|".join(row.get("related_theme_names") or [])})


def _write_summary(path: Path, report: dict[str, Any], trace_counts: dict[str, Any]) -> None:
    perf = report.get("performance") if isinstance(report.get("performance"), dict) else {}
    lines = [
        "# 盘前必读 E2E Summary",
        "",
        f"- 测试库: stock_data",
        f"- 注入/期望数量: {trace_counts.get('expected_input_count', 0)}",
        f"- news_raw_count: {trace_counts.get('news_raw_count', 0)}",
        f"- news_event_count: {trace_counts.get('news_event_count', 0)}",
        f"- decision_entry_count: {trace_counts.get('decision_entry_count', trace_counts.get('decision_count', 0))}",
        f"- decision_distinct_event_count: {trace_counts.get('decision_distinct_event_count', trace_counts.get('decision_count', 0))}",
        f"- duplicate_decision_event_count: {trace_counts.get('duplicate_decision_event_count', 0)}",
        f"- terminal_distinct_event_count: {trace_counts.get('terminal_distinct_event_count', 0)}",
        f"- non_terminal_event_count: {trace_counts.get('non_terminal_event_count', 0)}",
        f"- decision_seen_but_no_output_count: {trace_counts.get('decision_seen_but_no_output_count', 0)}",
        f"- event_subject_map_count: {trace_counts.get('event_subject_map_count', trace_counts.get('event_theme_map_count', 0))}",
        f"- mapped_distinct_event_count: {trace_counts.get('mapped_distinct_event_count', trace_counts.get('mapped_event_count', 0))}",
        f"- review_queue_count: {trace_counts.get('review_queue_count', 0)}",
        f"- review_distinct_event_count: {trace_counts.get('review_distinct_event_count', trace_counts.get('review_queue_count', 0))}",
        f"- pending_distinct_event_count: {trace_counts.get('pending_distinct_event_count', trace_counts.get('pending_count', 0))}",
        f"- primary_hit_rate: {report['primary_hit_rate']}",
        f"- related_hit_rate: {report['related_hit_rate']}",
        f"- theme_set_recall@5: {report['theme_set_recall@5']}",
        f"- wrong_related_count: {report['wrong_related_count']}",
        f"- neighbor_related_count: {report.get('neighbor_related_count', 0)}",
        f"- over_expanded_related_count: {report.get('over_expanded_related_count', 0)}",
        f"- generic_only_related_count: {report['generic_only_related_count']}",
        f"- llm_anchor_guard_count: {report['llm_anchor_guard_count']}",
        f"- avg_match_ms: {perf.get('avg_match_ms', trace_counts.get('avg_match_ms', 0))}",
        f"- p50_match_ms: {perf.get('p50_match_ms', trace_counts.get('p50_match_ms', 0))}",
        f"- p95_match_ms: {perf.get('p95_match_ms', trace_counts.get('p95_match_ms', 0))}",
        f"- llm_judge_count: {perf.get('llm_judge_count', trace_counts.get('llm_judge_count', 0))}",
        f"- event_profile_llm_count: {perf.get('event_profile_llm_count', trace_counts.get('event_profile_llm_count', 0))}",
        f"- profile_load_count: {perf.get('profile_load_count', trace_counts.get('profile_load_count', 0))}",
        f"- profile_cache_hit_count: {perf.get('profile_cache_hit_count', trace_counts.get('profile_cache_hit_count', 0))}",
        f"- profile_cache_miss_count: {perf.get('profile_cache_miss_count', trace_counts.get('profile_cache_miss_count', 0))}",
        f"- profile_map_cache_hit_count: {perf.get('profile_map_cache_hit_count', trace_counts.get('profile_map_cache_hit_count', 0))}",
        f"- profile_map_cache_miss_count: {perf.get('profile_map_cache_miss_count', trace_counts.get('profile_map_cache_miss_count', 0))}",
        f"- query_vector_cache_hit_count: {perf.get('query_vector_cache_hit_count', trace_counts.get('query_vector_cache_hit_count', 0))}",
        f"- query_vector_cache_miss_count: {perf.get('query_vector_cache_miss_count', trace_counts.get('query_vector_cache_miss_count', 0))}",
        f"- rerank_doc_vector_cache_hit_count: {perf.get('rerank_doc_vector_cache_hit_count', trace_counts.get('rerank_doc_vector_cache_hit_count', 0))}",
        f"- rerank_doc_vector_cache_miss_count: {perf.get('rerank_doc_vector_cache_miss_count', trace_counts.get('rerank_doc_vector_cache_miss_count', 0))}",
        f"- brief_theme_count: {report['brief_theme_count']}",
        f"- brief_opportunity_count: {report['brief_opportunity_count']}",
        f"- numeric_theme_name_count: {report.get('numeric_theme_name_count', 0)}",
        f"- unnamed_theme_count: {report.get('unnamed_theme_count', 0)}",
        f"- subject_key_chip_count: {report.get('subject_key_chip_count', 0)}",
        f"- 是否通过基础门禁: {_base_gate_passed(report, trace_counts)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _extract_performance_summary(trace_counts: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "match_timing_sample_count",
        "avg_match_ms",
        "p50_match_ms",
        "p95_match_ms",
        "llm_judge_count",
        "event_profile_llm_count",
        "profile_load_count",
        "profile_cache_hit_count",
        "profile_cache_miss_count",
        "profile_map_cache_hit_count",
        "profile_map_cache_miss_count",
        "query_vector_cache_hit_count",
        "query_vector_cache_miss_count",
        "rerank_doc_vector_cache_hit_count",
        "rerank_doc_vector_cache_miss_count",
    ]
    return {key: trace_counts.get(key, 0) for key in keys}


def _base_gate_passed(report: dict[str, Any], trace_counts: dict[str, Any]) -> bool:
    expected = int(trace_counts.get("expected_input_count") or 0)
    return (
        expected > 0
        and int(trace_counts.get("news_raw_count") or 0) >= expected
        and int(trace_counts.get("news_event_count") or 0) >= max(1, int(expected * 0.95))
        and report.get("brief_theme_count", 0) > 0
        and int(report.get("numeric_theme_name_count") or 0) == 0
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="评估盘前必读 E2E 题材召回与报告快照质量。")
    parser.add_argument("--gold-labels", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    result = evaluate(
        gold_path=Path(args.gold_labels),
        trace_path=Path(args.trace),
        snapshot_path=Path(args.snapshot) if args.snapshot else None,
        out_dir=Path(args.out_dir),
    )
    print(result)


if __name__ == "__main__":
    main()
