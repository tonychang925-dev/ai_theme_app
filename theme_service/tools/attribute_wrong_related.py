from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theme_service.tools.compare_theme_profile_v1_v2 import ALIAS_MAP
from theme_service.tools.profile_quality_common import safe_str, unique, write_jsonl


ROOT_CAUSES = {
    "source_org_as_anchor",
    "location_as_anchor",
    "short_generic_theme",
    "broad_policy_profile",
    "profile_boundary_missing",
    "matcher_related_gate_too_loose",
    "eval_alias_error",
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "event_title",
        "gold_theme",
        "wrong_subject_key",
        "wrong_theme_name",
        "source_profile_version",
        "evidence_summary",
        "hit_terms",
        "hit_term_roles",
        "relation_assessment",
        "root_cause",
        "fix_action",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _gold_terms_for_case(gold_by_case: dict[str, Any], case_id: str) -> list[str]:
    value = gold_by_case.get(case_id)
    if isinstance(value, dict):
        raw = value.get("gold_theme_name") or value.get("gold_theme") or value.get("theme_name")
    else:
        raw = value
    if not raw:
        return []
    terms = [safe_str(raw)]
    terms.extend(ALIAS_MAP.get(safe_str(raw), []))
    return unique([term for term in terms if term])


def _matches_gold(name: str, gold_terms: list[str]) -> bool:
    name = safe_str(name)
    return any(term and name and (term in name or name in term) for term in gold_terms)


def _is_commercial_space_neighbor(gold_theme: str, primary_name: str, related_name: str) -> bool:
    if not gold_theme or not related_name:
        return False
    has_space_context = any(term in gold_theme or term in primary_name for term in COMMERCIAL_SPACE_TERMS)
    has_space_related = any(term in related_name for term in COMMERCIAL_SPACE_TERMS)
    return has_space_context and has_space_related


def _load_gold(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    return {safe_str(row.get("case_id")): row for row in _read_jsonl(path)}


def _load_input_news(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    return {safe_str(row.get("case_id")): row for row in _read_jsonl(path)}


def _loads_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _unwrap_evidence(value: Any) -> dict[str, Any]:
    obj = _loads_obj(value)
    if isinstance(obj.get("related_match"), dict):
        evidence = obj["related_match"].get("evidence")
        return evidence if isinstance(evidence, dict) else {}
    return obj


def _hit_terms(evidence: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in (
        "theme_name_hit_terms",
        "subject_name_hit_terms",
        "object_hits",
        "must_hits",
        "strong_hits",
        "should_hits",
        "entity_hits",
        "profile_anchor_hits",
        "support_hits",
    ):
        value = evidence.get(key) or []
        if isinstance(value, list):
            terms.extend(safe_str(item) for item in value)
    return unique([term for term in terms if term])


def _classify_root_cause(title: str, wrong_name: str, evidence: dict[str, Any]) -> tuple[str, str]:
    roles = evidence.get("hit_term_roles") if isinstance(evidence.get("hit_term_roles"), dict) else {}
    terms = _hit_terms(evidence)
    if wrong_name == "证券" or roles.get("证券") == "source_org" or "东方证券" in title:
        return "source_org_as_anchor", "add_source_org_role_guard_and_v2_no_anchor"
    if wrong_name == "深圳" or roles.get("深圳") == "location":
        return "location_as_anchor", "add_location_role_guard_and_v2_boundary"
    if wrong_name == "高温" or any(term in {"高温", "温升"} for term in terms):
        return "short_generic_theme", "add_short_generic_direct_hit_guard_and_high_temp_v2_boundary"
    if wrong_name == "一带一路":
        return "broad_policy_profile", "add_broad_policy_boundary_and_require_real_bri_anchor"
    if evidence.get("role_guard_blocked"):
        return "matcher_related_gate_too_loose", "block_related_when_all_hits_are_non_anchor_roles"
    return "profile_boundary_missing", "rebuild_profile_v2_with_negative_terms"


def _source_profile_version(subject_key: str, active_v2_keys: set[str]) -> str:
    return "v2" if safe_str(subject_key) in active_v2_keys else "v1_fallback"


def build_report(
    trace_report: dict[str, Any],
    gold_by_case: dict[str, Any],
    active_v2_keys: set[str],
    input_news_by_case: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    input_news_by_case = input_news_by_case or {}
    for trace_row in trace_report.get("rows") or []:
        case_id = safe_str(trace_row.get("case_id"))
        input_news = input_news_by_case.get(case_id) or {}
        title = safe_str(trace_row.get("title") or trace_row.get("event_title") or input_news.get("title") or input_news.get("content"))
        gold_terms = _gold_terms_for_case(gold_by_case, case_id)
        gold_theme = gold_terms[0] if gold_terms else safe_str(trace_row.get("gold_theme"))

        primary_name = safe_str(trace_row.get("primary_theme_name"))
        primary_key = safe_str(trace_row.get("primary_subject_key"))
        if primary_name and gold_terms and not _matches_gold(primary_name, gold_terms):
            evidence = _unwrap_evidence(trace_row.get("primary_evidence") or trace_row.get("best_evidence") or {})
            root_cause, fix_action = _classify_root_cause(title, primary_name, evidence)
            rows.append(
                {
                    "case_id": case_id,
                    "event_title": title,
                    "gold_theme": gold_theme,
                    "wrong_subject_key": primary_key,
                    "wrong_theme_name": primary_name,
                    "source_profile_version": _source_profile_version(primary_key, active_v2_keys),
                    "evidence_summary": json.dumps(evidence.get("evidence_summary") or {}, ensure_ascii=False),
                    "hit_terms": json.dumps(_hit_terms(evidence), ensure_ascii=False),
                    "hit_term_roles": json.dumps(evidence.get("hit_term_roles") or {}, ensure_ascii=False),
                    "relation_assessment": "wrong_primary",
                    "root_cause": root_cause if root_cause in ROOT_CAUSES else "profile_boundary_missing",
                    "fix_action": fix_action,
                }
            )

        for mapping in trace_row.get("related_mappings") or []:
            wrong_name = safe_str(mapping.get("theme_name") or mapping.get("subject_name"))
            wrong_key = safe_str(mapping.get("subject_key"))
            if not wrong_name or _matches_gold(wrong_name, gold_terms):
                continue
            evidence = _unwrap_evidence(mapping.get("evidence_json") or mapping.get("evidence") or {})
            root_cause, fix_action = _classify_root_cause(title, wrong_name, evidence)
            relation_assessment = "wrong_related"
            if _is_commercial_space_neighbor(gold_theme, primary_name, wrong_name):
                relation_assessment = "commercial_space_neighbor"
                root_cause = "eval_alias_error"
                fix_action = "classify_as_neighbor_or_limit_over_expansion"
            rows.append(
                {
                    "case_id": case_id,
                    "event_title": title,
                    "gold_theme": gold_theme,
                    "wrong_subject_key": wrong_key,
                    "wrong_theme_name": wrong_name,
                    "source_profile_version": _source_profile_version(wrong_key, active_v2_keys),
                    "evidence_summary": json.dumps(evidence.get("evidence_summary") or {}, ensure_ascii=False),
                    "hit_terms": json.dumps(_hit_terms(evidence), ensure_ascii=False),
                    "hit_term_roles": json.dumps(evidence.get("hit_term_roles") or {}, ensure_ascii=False),
                    "relation_assessment": relation_assessment,
                    "root_cause": root_cause if root_cause in ROOT_CAUSES else "profile_boundary_missing",
                    "fix_action": fix_action,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate wrong related attribution report from pre-market E2E trace.")
    parser.add_argument("--trace-report", required=True)
    parser.add_argument("--gold-labels")
    parser.add_argument("--input-news")
    parser.add_argument("--active-v2-keys", default="")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    trace_report = _read_json(Path(args.trace_report))
    gold_by_case = _load_gold(Path(args.gold_labels)) if args.gold_labels else {}
    input_news_by_case = _load_input_news(Path(args.input_news)) if args.input_news else {}
    active_v2_keys = {safe_str(item) for item in args.active_v2_keys.split(",") if safe_str(item)}
    rows = build_report(trace_report, gold_by_case, active_v2_keys, input_news_by_case)

    out_dir = Path(args.output_dir)
    write_jsonl(out_dir / "wrong_related_attribution_report.jsonl", rows)
    _write_csv(out_dir / "wrong_related_attribution_report.csv", rows)
    print(json.dumps({"wrong_related_attribution_count": len(rows), "output_dir": str(out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
