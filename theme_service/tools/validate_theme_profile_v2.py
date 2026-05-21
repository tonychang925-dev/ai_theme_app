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
from theme_service.services.theme_match_types import ThemeProfile
from theme_service.tools.profile_eval_common import (
    disable_llm_for_engine,
    hard_negative_row,
    request_from_hard_negative,
    result_subject_keys,
    result_theme_names,
)
from theme_service.tools.profile_quality_common import (
    add_db_args,
    connect,
    default_output_dir,
    is_generic_term,
    load_json,
    normalize_list,
    read_jsonl,
    run_async,
    safe_str,
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


def _profile_to_theme_profile(data: dict[str, Any]) -> ThemeProfile:
    anchors = unique(
        normalize_list(data.get("entity_anchors"))
        + normalize_list(data.get("domain_anchors"))
        + normalize_list(data.get("product_anchors"))
        + normalize_list(data.get("technology_anchors"))
    )
    return ThemeProfile(
        subject_key=safe_str(data.get("subject_key")),
        subject_name=safe_str(data.get("subject_name")),
        theme_master_id=None,
        concept=safe_str(data.get("subject_name")),
        semantic_type="profile_v2",
        strategy_type="event_driven",
        ontology_json={},
        gate_json={
            "profile_version": "v2",
            "support_terms": normalize_list(data.get("support_terms")),
            "weak_terms": normalize_list(data.get("weak_terms")),
            "no_anchor_terms": normalize_list(data.get("no_anchor_terms")),
            "boundary_rules": load_json(data.get("boundary_rules"), {}),
            "eval_metrics": data.get("eval_metrics") or {},
        },
        must_terms=normalize_list(data.get("must_terms")),
        should_terms=normalize_list(data.get("should_terms")),
        not_terms=[],
        strong_terms=normalize_list(data.get("strong_terms")),
        weak_terms=normalize_list(data.get("weak_terms")),
        negative_terms=normalize_list(data.get("negative_terms")),
        search_text=" ".join(anchors + normalize_list(data.get("should_terms"))),
        quality="v2",
        rerank_text=" ".join(anchors + normalize_list(data.get("must_terms")) + normalize_list(data.get("strong_terms"))),
        aliases=normalize_list(data.get("aliases")),
        entity_hints=normalize_list(data.get("entity_anchors")),
        core_objects=anchors,
    )


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    subject_key = safe_str(profile.get("subject_key"))
    subject_name = safe_str(profile.get("subject_name"))
    must_terms = normalize_list(profile.get("must_terms"))
    strong_terms = normalize_list(profile.get("strong_terms"))
    aliases = normalize_list(profile.get("aliases"))
    anchors = unique(
        normalize_list(profile.get("entity_anchors"))
        + normalize_list(profile.get("domain_anchors"))
        + normalize_list(profile.get("product_anchors"))
        + normalize_list(profile.get("technology_anchors"))
    )
    negative_terms = normalize_list(profile.get("negative_terms"))
    confusion_subject_keys = normalize_list(profile.get("confusion_subject_keys"))
    quality_score = float(profile.get("quality_score") or 0)
    eval_metrics = profile.get("eval_metrics") if isinstance(profile.get("eval_metrics"), dict) else {}
    nearby_overlap_score = float(eval_metrics.get("nearby_overlap_score") or 0)
    hard_negative_reject_rate = eval_metrics.get("hard_negative_reject_rate")

    must_generic = [term for term in must_terms if is_generic_term(term)]
    strong_generic = [term for term in strong_terms if is_generic_term(term)]
    alias_generic = [term for term in aliases if is_generic_term(term)]
    strong_generic_ratio = len(strong_generic) / max(1, len(strong_terms))
    failures: list[str] = []
    if not subject_name:
        failures.append("subject_name_empty")
    if subject_name and subject_name == subject_key:
        failures.append("subject_name_equals_subject_key")
    if subject_name and subject_name.isdigit():
        failures.append("subject_name_numeric")
    if aliases and all(alias.isdigit() or alias == subject_key for alias in aliases):
        failures.append("aliases_only_numeric_subject_key")
    if must_generic:
        failures.append("must_terms_contain_generic")
    if strong_generic_ratio >= 0.10:
        failures.append("strong_terms_generic_ratio_gte_10pct")
    if alias_generic:
        failures.append("aliases_contain_generic")
    if len(anchors) < 3:
        failures.append("anchor_count_lt_3")
    if not negative_terms and not confusion_subject_keys:
        failures.append("missing_negative_or_confusion")
    if quality_score < 80:
        failures.append("quality_score_lt_80")
    if nearby_overlap_score > 0.75:
        failures.append("nearby_overlap_score_gt_0_75")
    if hard_negative_reject_rate is not None:
        try:
            if float(hard_negative_reject_rate) < 0.80:
                failures.append("hard_negative_reject_rate_lt_0_80")
        except Exception:
            failures.append("hard_negative_reject_rate_invalid")
    if not profile.get("evidence_refs"):
        failures.append("missing_evidence_refs")
    return {
        "subject_key": subject_key,
        "subject_name": subject_name,
        "passed": not failures,
        "failures": failures,
        "must_generic_terms": must_generic,
        "strong_generic_ratio": round(strong_generic_ratio, 4),
        "alias_generic_terms": alias_generic,
        "anchor_count": len(anchors),
        "negative_terms_count": len(negative_terms),
        "confusion_subject_key_count": len(confusion_subject_keys),
        "quality_score": quality_score,
        "nearby_overlap_score": nearby_overlap_score,
        "hard_negative_reject_rate": hard_negative_reject_rate,
        "hard_negative_reject_rate_checked": hard_negative_reject_rate is not None,
    }


async def _evaluate_hard_negatives(
    profiles: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    *,
    gate_only: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    theme_profiles = [_profile_to_theme_profile(profile) for profile in profiles]
    engine = ThemeMatchEngine(_StaticRepo(theme_profiles))
    disable_llm_for_engine(engine, gate_only=gate_only)
    profile_index = {safe_str(profile.get("subject_key")): profile for profile in profiles}
    metrics = {
        key: {
            "hard_negative_case_count": 0,
            "hard_negative_reject_count": 0,
            "failed_hard_negative_cases": [],
        }
        for key in profile_index
    }
    case_rows: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        result = await engine.match_event(request_from_hard_negative(case, idx))
        result_keys = set(result_subject_keys(result))
        result_names = result_theme_names(result)
        must_not_keys = set(normalize_list(case.get("must_not_subject_keys")))
        must_not_names = normalize_list(case.get("must_not_theme_names"))
        applicable_keys = {key for key in must_not_keys if key in profile_index}
        for key, profile in profile_index.items():
            name = safe_str(profile.get("subject_name"))
            if any(blocked and blocked == name for blocked in must_not_names):
                applicable_keys.add(key)
        wrong_keys = result_keys & applicable_keys
        wrong_names = [
            name
            for name in result_names
            if any(blocked and (blocked == name or blocked in name or name in blocked) for blocked in must_not_names)
        ]
        for key in applicable_keys:
            metrics[key]["hard_negative_case_count"] += 1
            profile_name = safe_str(profile_index[key].get("subject_name"))
            failed = key in result_keys or any(name and name == profile_name for name in result_names)
            if failed:
                metrics[key]["failed_hard_negative_cases"].append(safe_str(case.get("case_id")))
            else:
                metrics[key]["hard_negative_reject_count"] += 1
        case_rows.append(
            {
                "case_id": safe_str(case.get("case_id")),
                "tags": normalize_list(case.get("tags")),
                "positive_subject_keys": normalize_list(case.get("positive_subject_keys")),
                "must_not_subject_keys": normalize_list(case.get("must_not_subject_keys")),
                "must_not_theme_names": normalize_list(case.get("must_not_theme_names")),
                **hard_negative_row(case, result, "v2"),
            }
        )
    for key, metric in metrics.items():
        total = int(metric["hard_negative_case_count"])
        if total > 0:
            metric["hard_negative_reject_rate"] = round(int(metric["hard_negative_reject_count"]) / total, 4)
        else:
            metric["hard_negative_reject_rate"] = None
    return metrics, case_rows


async def _load_db_profiles(db_name: str, status: str | None) -> list[dict[str, Any]]:
    conn = await connect(db_name)
    try:
        where = "WHERE status = $1" if status else ""
        args = [status] if status else []
        rows = await conn.fetch(f"SELECT * FROM theme_profile_v2 {where} ORDER BY subject_key", *args)
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated theme_profile_v2 rows.")
    add_db_args(parser)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--status")
    parser.add_argument("--hard-negative-file", type=Path)
    parser.add_argument("--gate-only", action="store_true", help="Skip dense/rerank embeddings for quick local gate checks.")
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_v2_validate_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    out_dir = args.output_dir or default_output_dir(args.run_id)
    if args.input:
        profiles = read_jsonl(args.input)
    else:
        profiles = await _load_db_profiles(args.write_db_name, args.status)
    hard_negative_case_rows: list[dict[str, Any]] = []
    if args.hard_negative_file:
        cases = read_jsonl(args.hard_negative_file)
        hard_negative_metrics, hard_negative_case_rows = await _evaluate_hard_negatives(profiles, cases, gate_only=args.gate_only)
        for profile in profiles:
            key = safe_str(profile.get("subject_key"))
            metrics = profile.get("eval_metrics") if isinstance(profile.get("eval_metrics"), dict) else {}
            metrics.update(hard_negative_metrics.get(key, {}))
            profile["eval_metrics"] = metrics
    rows = [validate_profile(profile) for profile in profiles]
    hard_negative_by_key = {
        safe_str(profile.get("subject_key")): profile.get("eval_metrics", {})
        for profile in profiles
        if isinstance(profile.get("eval_metrics"), dict)
    }
    for row in rows:
        metrics = hard_negative_by_key.get(row["subject_key"], {})
        row["hard_negative_case_count"] = metrics.get("hard_negative_case_count", 0)
        row["hard_negative_reject_count"] = metrics.get("hard_negative_reject_count", 0)
        row["failed_hard_negative_cases"] = metrics.get("failed_hard_negative_cases", [])
    pass_count = sum(1 for row in rows if row["passed"])
    summary = {
        "total": len(rows),
        "passed": pass_count,
        "pass_rate": round(pass_count / max(1, len(rows)), 4),
        "threshold_passed": pass_count / max(1, len(rows)) >= 0.80,
        "hard_negative_case_count": len(hard_negative_case_rows),
        "hard_negative_checked_profiles": sum(1 for row in rows if row.get("hard_negative_case_count", 0) > 0),
    }
    write_jsonl(out_dir / "theme_profile_v2_validation.jsonl", rows)
    write_csv(out_dir / "theme_profile_v2_validation.csv", rows)
    if hard_negative_case_rows:
        write_jsonl(out_dir / "hard_negative_eval_report.jsonl", hard_negative_case_rows)
        write_csv(out_dir / "hard_negative_eval_report.csv", hard_negative_case_rows)
    (out_dir / "theme_profile_v2_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print({**summary, "out_dir": str(out_dir)})


if __name__ == "__main__":
    run_async(main())
