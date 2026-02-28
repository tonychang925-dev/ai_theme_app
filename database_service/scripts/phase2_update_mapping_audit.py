"""
Phase2 update-theme mapping audit report.

Usage:
  /opt/miniconda3/envs/theme_matcher_env/bin/python database_service/scripts/phase2_update_mapping_audit.py \
      --sample-size 24 \
      --out tmp/phase2_update_mapping_audit.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SERVICE_DIR)

from database_service.scripts.test_theme_processor import RealIntegrationTester


EQUIVALENT_TOPIC_CLUSTERS = [
    # SpaceX/太空军事在当前业务中属于同题材簇（同源提取的不同事件）
    {"spacex", "太空军事", "导弹预警卫星", "星链", "商业航天", "卫星"},
    {"核聚变", "可控核聚变", "聚变能", "聚变"},
    {"对日", "中日", "靖国神社", "两用物项", "外交军事紧张"},
]


def _text_tokens(text: str) -> set[str]:
    raw = str(text or "").strip().lower()
    if not raw:
        return set()
    tokens = set()
    for part in [raw, raw.replace(" ", ""), raw.replace("相关新闻", "")]:
        if part:
            tokens.add(part)
    return tokens


def _hits_cluster(event_text: str, theme_text: str) -> bool:
    event_tokens = _text_tokens(event_text)
    theme_tokens = _text_tokens(theme_text)
    if not event_tokens or not theme_tokens:
        return False

    for cluster in EQUIVALENT_TOPIC_CLUSTERS:
        cluster_tokens = {str(x).strip().lower() for x in cluster if str(x).strip()}
        if any(any(c in e for c in cluster_tokens) for e in event_tokens) and any(
            any(c in t for c in cluster_tokens) for t in theme_tokens
        ):
            return True
    return False


def _is_mapping_accurate(detail: Dict[str, Any]) -> bool:
    overlap_count = int(detail.get("guardrail_overlap_count", 0) or 0)
    if overlap_count > 0:
        return True

    core = str(detail.get("event_core_concept") or "").strip().lower()
    theme = str(
        detail.get("matched_theme_name")
        or detail.get("best_theme_name")
        or ""
    ).strip().lower()
    if core and theme and (core in theme or theme in core):
        return True

    title = str(detail.get("event_title") or "").strip()
    event_context = " ".join([title, core]).strip()
    if _hits_cluster(event_context, theme):
        return True

    return False


def _build_mapping_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for d in result.get("decision_details", []) or []:
        if not isinstance(d, dict):
            continue
        if d.get("action") != "update_theme":
            continue

        row = {
            "event_id": d.get("event_id"),
            "event_title": d.get("event_title"),
            "event_core_concept": d.get("event_core_concept"),
            "decision_type": d.get("decision_type"),
            "matched_theme_id": d.get("best_theme_id"),
            "matched_theme_name": d.get("best_theme_name"),
            "match_confidence": d.get("best_theme_confidence"),
            "matched_keywords": d.get("best_theme_matched_keywords", []),
            "guardrail_passed": d.get("guardrail_passed"),
            "guardrail_overlap_count": d.get("guardrail_overlap_count", 0),
            "guardrail_overlap_keywords": d.get("guardrail_overlap_keywords", []),
            "rejected_best_theme_name": d.get("rejected_best_theme_name"),
            "rejected_best_theme_confidence": d.get("rejected_best_theme_confidence"),
            "algorithm_used": d.get("algorithm_used"),
            "match_reason": d.get("match_reason"),
        }
        row["accuracy_rule_passed"] = _is_mapping_accurate(row)
        rows.append(row)

    return rows


async def run(sample_size: int) -> Dict[str, Any]:
    tester = RealIntegrationTester()
    setup_ok = await tester.setup()
    if not setup_ok:
        return {"success": False, "error": "setup_failed"}

    try:
        result = await tester.test_new_architecture_with_dataset(
            sample_size=sample_size, return_details=True
        )
        if not isinstance(result, dict):
            return {"success": False, "error": "unexpected_result_type", "result": str(result)}

        mapping_rows = _build_mapping_rows(result)
        total_updates = len(mapping_rows)
        accurate_updates = sum(1 for r in mapping_rows if r["accuracy_rule_passed"])
        accuracy = (accurate_updates / total_updates) if total_updates else 0.0

        create_details = result.get("create_new_theme_details", []) or []
        create_count = len(create_details)
        create_upstream = sum(
            1 for d in create_details if isinstance(d, dict) and d.get("classification_source") == "upstream"
        )
        create_ai = sum(
            1
            for d in create_details
            if isinstance(d, dict) and d.get("classification_source") == "created_from_ai_keywords"
        )

        return {
            "success": bool(result.get("success", False)),
            "sample_size": sample_size,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_decisions": len(result.get("decision_details", []) or []),
                "update_theme_decisions": total_updates,
                "create_new_theme_decisions": create_count,
                "create_source_upstream_count": create_upstream,
                "create_source_ai_keywords_count": create_ai,
                "update_mapping_accuracy_rule": round(accuracy, 4),
                "update_mapping_accurate_count": accurate_updates,
                "update_mapping_total_count": total_updates,
            },
            "stream_stats": result.get("stream_stats", {}),
            "success_criteria": result.get("success_criteria", {}),
            "t03_validation": result.get("t03_validation", {}),
            "t04_validation": result.get("t04_validation", {}),
            "update_theme_mappings": mapping_rows,
            "create_new_theme_details": create_details,
        }
    finally:
        await tester.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=24)
    parser.add_argument(
        "--out",
        type=str,
        default="tmp/phase2_update_mapping_audit.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(sample_size=args.sample_size))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report.get("summary", {})
    print("report=", str(out_path))
    print("success=", report.get("success"))
    print("update_theme_decisions=", summary.get("update_theme_decisions"))
    print("create_new_theme_decisions=", summary.get("create_new_theme_decisions"))
    print("update_mapping_accuracy_rule=", summary.get("update_mapping_accuracy_rule"))


if __name__ == "__main__":
    main()
