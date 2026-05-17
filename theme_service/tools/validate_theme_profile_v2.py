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

from theme_service.tools.profile_quality_common import (
    add_db_args,
    connect,
    default_output_dir,
    is_generic_term,
    normalize_list,
    read_jsonl,
    run_async,
    safe_str,
    unique,
    write_csv,
    write_jsonl,
)


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
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
        "subject_key": safe_str(profile.get("subject_key")),
        "subject_name": safe_str(profile.get("subject_name")),
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
    parser.add_argument("--run-id", default=datetime.now().strftime("profile_v2_validate_%Y%m%d_%H%M%S"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    out_dir = args.output_dir or default_output_dir(args.run_id)
    if args.input:
        profiles = read_jsonl(args.input)
    else:
        profiles = await _load_db_profiles(args.write_db_name, args.status)
    rows = [validate_profile(profile) for profile in profiles]
    pass_count = sum(1 for row in rows if row["passed"])
    summary = {
        "total": len(rows),
        "passed": pass_count,
        "pass_rate": round(pass_count / max(1, len(rows)), 4),
        "threshold_passed": pass_count / max(1, len(rows)) >= 0.80,
    }
    write_jsonl(out_dir / "theme_profile_v2_validation.jsonl", rows)
    write_csv(out_dir / "theme_profile_v2_validation.csv", rows)
    (out_dir / "theme_profile_v2_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print({**summary, "out_dir": str(out_dir)})


if __name__ == "__main__":
    run_async(main())
