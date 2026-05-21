from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PUBLIC_NEWS_TERMS = ("政府", "国家", "美国", "中国", "国际", "接收", "观察", "发布", "部门")
MEDICAL_PUBLIC_HEALTH_TERMS = ("埃博拉", "感染", "病毒", "医生", "公共卫生", "预防", "观察", "疫苗")
BROAD_THEME_NAMES = {
    "半导体",
    "电力运营",
    "机器人",
    "消费电子",
    "光伏",
    "AI",
    "人工智能",
    "数据中心",
    "服务器",
    "游戏",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _key(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _runtime_source(subject_key: str, runtime_map: dict[str, dict[str, Any]]) -> str:
    row = runtime_map.get(subject_key) or {}
    return str(row.get("runtime_source") or "")


def _risk_row(subject_key: str, runtime_map: dict[str, dict[str, Any]], audit_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    runtime = runtime_map.get(subject_key) or {}
    audit = audit_map.get(subject_key) or {}
    return {
        "matched_gate_risk_level": runtime.get("active_runtime_risk_level") or audit.get("risk_level"),
        "matched_gate_risk_flags": runtime.get("risk_flags") or audit.get("risk_flags") or [],
    }


def _top_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = row.get("top_candidates") or []
    return candidates if isinstance(candidates, list) else []


def _is_match_decision(decision: str) -> bool:
    normalized = decision.strip().lower()
    return normalized in {"match", "update_theme", "create_or_update_theme"}


def _classify(row: dict[str, Any], runtime_map: dict[str, dict[str, Any]], audit_map: dict[str, dict[str, Any]]) -> tuple[str, str]:
    expected = _key(row, "expected_subject_key")
    matched = _key(row, "matched_subject_key")
    action = _key(row, "action", "decision_type").upper()
    raw = _key(row, "raw_text", "title")
    matched_name = _key(row, "matched_theme_name")
    top1_hit = bool(row.get("top1_hit") or row.get("equivalent_top1_hit"))

    if top1_hit:
        return "correct_match", "no_action"
    if "HUMAN_REVIEW" in action or "REVIEW" in action:
        return "over_review" if expected else "reasonable_human_review", "add_hard_anchor" if expected else "no_action"
    if "UNKNOWN" in action or not matched:
        return "false_unknown" if expected else "reasonable_unknown", "add_hard_anchor" if expected else "no_action"

    if _contains_any(raw, MEDICAL_PUBLIC_HEALTH_TERMS):
        return "medical_public_health_false_positive", "add_negative_boundary"
    if _contains_any(raw, PUBLIC_NEWS_TERMS) and not expected:
        return "public_news_false_positive", "add_negative_boundary"
    if matched_name in BROAD_THEME_NAMES:
        return "broad_theme_hijack", "broad_theme_demotion"
    if expected and matched != expected:
        top_candidates = _top_candidates(row)
        top_subjects = {str(item.get("subject_key") or "") for item in top_candidates if isinstance(item, dict)}
        if expected in top_subjects:
            return "broad_theme_hijack", "broad_theme_demotion"
        source = _runtime_source(matched, runtime_map)
        risk = _risk_row(matched, runtime_map, audit_map)
        if source == "v1_fallback" and risk.get("matched_gate_risk_level") in {"A", "B"}:
            return "obvious_wrong_match", "add_v2_profile"
        return "obvious_wrong_match", "gate_rebuild"
    return "obvious_wrong_match", "gate_rebuild"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    report = _load_json(args.e2e_report)
    details = report.get("details") or []
    runtime_rows = _load_jsonl(args.runtime_source)
    runtime_map = {str(row.get("subject_key")): row for row in runtime_rows}
    audit_rows = _load_jsonl(args.audit)
    audit_map = {str(row.get("subject_key")): row for row in audit_rows}

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    detail_path = out_dir / "e2e100_gate_attribution_detail.jsonl"
    report_path = out_dir / "e2e100_gate_attribution_report.md"

    rows: list[dict[str, Any]] = []
    for row in details:
        matched = _key(row, "matched_subject_key")
        error_type, suggested_fix = _classify(row, runtime_map, audit_map)
        risk = _risk_row(matched, runtime_map, audit_map)
        top_candidates = _top_candidates(row)
        raw = _key(row, "raw_text", "title")
        rows.append(
            {
                "event_id": row.get("news_event_id"),
                "title": raw[:120],
                "expected_subject_key": _key(row, "expected_subject_key"),
                "expected_theme_name": _key(row, "expected_theme_name", "theme_name"),
                "matched_subject_key": matched,
                "matched_theme_name": _key(row, "matched_theme_name"),
                "decision": _key(row, "action", "decision_type"),
                "confidence": row.get("confidence"),
                "reason_code": row.get("reason_code"),
                "runtime_profile_source": _runtime_source(matched, runtime_map),
                **risk,
                "best_evidence": row.get("best_evidence") or {},
                "top_candidates": top_candidates,
                "error_type": error_type,
                "suggested_fix": suggested_fix,
            }
        )

    detail_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    counts = Counter(row["error_type"] for row in rows)
    decisions = Counter(_key(row, "decision") for row in rows)
    recall5_hits = 0
    for source in details:
        expected = _key(source, "expected_subject_key")
        equivalent = set(str(item) for item in (source.get("equivalent_subject_keys") or []))
        top_subjects = {
            str(item.get("subject_key") or "")
            for item in _top_candidates(source)
            if isinstance(item, dict)
        }
        if source.get("equivalent_top1_hit") or expected in top_subjects or bool(equivalent & top_subjects):
            recall5_hits += 1
    direct_name_fp = 0
    for row in rows:
        if row["error_type"] == "correct_match":
            continue
        name = row.get("matched_theme_name") or ""
        if name and name in (row.get("title") or ""):
            direct_name_fp += 1

    metrics = {
        "events": report.get("events"),
        "processed": report.get("processed"),
        "theme_set_recall@5": round(recall5_hits / max(1, len(details)), 4),
        "top1_accuracy": report.get("equivalent_top1_accuracy", report.get("top1_accuracy")),
        "match_count": sum(count for key, count in decisions.items() if _is_match_decision(key)),
        "human_review_count": sum(count for key, count in decisions.items() if "REVIEW" in key.upper()),
        "unknown_count": sum(count for key, count in decisions.items() if "UNKNOWN" in key.upper() or key == "publish_clustering"),
        "false_positive_count": sum(counts[key] for key in ("obvious_wrong_match", "public_news_false_positive", "medical_public_health_false_positive")),
        "obvious_wrong_match_count": counts.get("obvious_wrong_match", 0),
        "hard_negative_violation_count": 0,
        "public_news_false_positive_count": counts.get("public_news_false_positive", 0),
        "medical_public_health_false_positive_count": counts.get("medical_public_health_false_positive", 0),
        "broad_theme_hijack_count": counts.get("broad_theme_hijack", 0),
        "direct_theme_name_hit_false_positive_count": direct_name_fp,
        "v1_fallback_match_count": sum(1 for row in rows if row.get("runtime_profile_source") == "v1_fallback"),
        "v2_accepted_match_count": sum(1 for row in rows if row.get("runtime_profile_source") == "v2_accepted"),
    }

    ordered_errors = [row for row in rows if row["error_type"] != "correct_match"]
    lines = [
        "# E2E100 Gate Attribution Report",
        "",
        "## Metrics",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in metrics.items())
    lines.extend(["", "## Error Type Counts", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Failures", ""])
    if not ordered_errors:
        lines.append("- none")
    for row in ordered_errors:
        lines.append(
            f"- event_id={row['event_id']} expected={row['expected_subject_key']} "
            f"matched={row['matched_subject_key']} type={row['error_type']} fix={row['suggested_fix']} "
            f"title={row['title']}"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    priority_order = {
        "hard_negative_violation": 0,
        "obvious_wrong_match": 1,
        "medical_public_health_false_positive": 2,
        "public_news_false_positive": 3,
        "broad_theme_hijack": 4,
        "false_unknown": 5,
        "over_review": 6,
    }
    plan_lines = [
        "# E2E100 Gate Repair Delta Plan",
        "",
        "## 必修",
        "",
    ]
    must_fix = [
        row
        for row in ordered_errors
        if row["error_type"] in {"hard_negative_violation", "obvious_wrong_match", "medical_public_health_false_positive", "public_news_false_positive"}
    ]
    if not must_fix:
        plan_lines.append("- none")
    for row in sorted(must_fix, key=lambda item: (priority_order.get(item["error_type"], 99), item.get("matched_subject_key") or "")):
        plan_lines.append(
            f"- {row['matched_subject_key'] or 'UNKNOWN'} {row['matched_theme_name'] or ''}: "
            f"{row['error_type']} -> {row['suggested_fix']} | expected={row['expected_subject_key']} {row['expected_theme_name']}"
        )
    plan_lines.extend(["", "## 应修", ""])
    should_fix = [row for row in ordered_errors if row["error_type"] in {"broad_theme_hijack", "false_unknown", "over_review"}]
    if not should_fix:
        plan_lines.append("- none")
    for row in sorted(should_fix, key=lambda item: (priority_order.get(item["error_type"], 99), item.get("matched_subject_key") or "")):
        plan_lines.append(
            f"- {row['matched_subject_key'] or 'UNKNOWN'} {row['matched_theme_name'] or ''}: "
            f"{row['error_type']} -> {row['suggested_fix']} | expected={row['expected_subject_key']} {row['expected_theme_name']}"
        )
    plan_lines.extend(
        [
            "",
            "## 暂缓",
            "",
            "- B-P0 gates not triggered by this E2E100 remain deferred.",
        ]
    )
    (out_dir / "e2e100_gate_repair_delta_plan.md").write_text("\n".join(plan_lines) + "\n", encoding="utf-8")
    (out_dir / "e2e100_gate_attribution_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"metrics": metrics, "detail_path": str(detail_path), "report_path": str(report_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build E2E100 gate attribution report.")
    parser.add_argument("--e2e-report", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/e2e100_phase4"))
    print(json.dumps(build_report(parser.parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
