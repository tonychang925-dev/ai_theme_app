from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT_CAUSE_HINTS = {
    "9030207": ("bad_gate_boundary", "remove satellite-warning generic missile anchors and add space warning boundary"),
    "9054404": ("generic_direct_hit", "remove generic energy/finance/communication anchors from collection theme"),
    "9064082": ("bad_gate_boundary", "block photoresist material news from Low-DK electronic cloth"),
    "9062142": ("bad_gate_boundary", "require Blue Arrow IPO action instead of company/rocket entity alone"),
    "9059490": ("bad_gate_boundary", "block recoverable-rocket events from space-computing profile"),
    "9063080": ("generic_direct_hit", "replace commercial-space generic anchors with space-tourism anchors"),
    "9015387": ("generic_direct_hit", "demote OLED-only display-panel hit when glasses-specific evidence exists"),
    "9048607": ("bad_gate_boundary", "block rare-earth policy events from fentanyl cooperation theme"),
    "9034859": ("broad_theme_hijack", "demote generic AI-agent profile when Manus-specific profile is present"),
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _candidate_rank(row: dict[str, Any], subject_key: str) -> int | None:
    for idx, item in enumerate(row.get("top_candidates") or [], start=1):
        if str(item.get("subject_key") or "") == subject_key:
            return idx
    return None


def _candidate_evidence(row: dict[str, Any], subject_key: str) -> dict[str, Any]:
    for item in row.get("top_candidates") or []:
        if str(item.get("subject_key") or "") == subject_key:
            return item.get("evidence") or {}
    return {}


def _top_candidate_summary(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "subject_key": item.get("subject_key"),
            "subject_name": item.get("subject_name"),
            "rerank_score": item.get("rerank_score"),
            "evidence_summary": (item.get("evidence") or {}).get("evidence_summary") or {},
        }
        for item in row.get("top_candidates") or []
    ]


def _root_cause(row: dict[str, Any]) -> tuple[str, str]:
    matched = str(row.get("matched_subject_key") or "")
    if matched in ROOT_CAUSE_HINTS:
        return ROOT_CAUSE_HINTS[matched]
    if row.get("runtime_profile_source") == "v1_fallback":
        return "v1_fallback_pollution", "add active v2 coverage or repair fallback boundary"
    return "llm_accept_without_enough_evidence", "add regression and tighten matched/expected gate evidence"


def build(args: argparse.Namespace) -> dict[str, int]:
    rows = _read_jsonl(args.detail)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    wrong_rows: list[dict[str, Any]] = []
    broad_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("error_type") == "obvious_wrong_match":
            root_cause, proposed_fix = _root_cause(row)
            wrong_rows.append(
                {
                    "event_id": row.get("event_id"),
                    "title": row.get("title"),
                    "expected_subject_key": row.get("expected_subject_key"),
                    "expected_theme_name": row.get("expected_theme_name"),
                    "matched_subject_key": row.get("matched_subject_key"),
                    "matched_theme_name": row.get("matched_theme_name"),
                    "confidence": row.get("confidence"),
                    "reason_code": row.get("reason_code"),
                    "runtime_profile_source": row.get("runtime_profile_source"),
                    "matched_gate_risk_level": row.get("matched_gate_risk_level"),
                    "matched_gate_risk_flags": row.get("matched_gate_risk_flags") or [],
                    "best_evidence": row.get("best_evidence") or {},
                    "top_candidates": _top_candidate_summary(row),
                    "root_cause": root_cause,
                    "proposed_fix": proposed_fix,
                }
            )
        if row.get("error_type") == "broad_theme_hijack":
            expected = str(row.get("expected_subject_key") or "")
            rank = _candidate_rank(row, expected)
            problem_stage = "ranking_problem" if rank else "recall_problem"
            if rank == 1:
                problem_stage = "final_decision_problem"
            broad_rows.append(
                {
                    "event_id": row.get("event_id"),
                    "title": row.get("title"),
                    "broad_matched_subject_key": row.get("matched_subject_key"),
                    "broad_matched_theme_name": row.get("matched_theme_name"),
                    "expected_specific_subject_key": row.get("expected_subject_key"),
                    "expected_specific_theme_name": row.get("expected_theme_name"),
                    "specific_candidate_rank": rank,
                    "specific_in_top5": rank is not None and rank <= 5,
                    "broad_evidence": _candidate_evidence(row, str(row.get("matched_subject_key") or "")),
                    "specific_evidence": _candidate_evidence(row, expected),
                    "problem_stage": problem_stage,
                    "proposed_fix": (
                        "strengthen_specific_gate"
                        if problem_stage == "recall_problem"
                        else "demote_broad_generic_hit+add_positive_rank_case"
                    ),
                }
            )
    _write_jsonl(args.out_dir / "obvious_wrong_match_cases.jsonl", wrong_rows)
    _write_jsonl(args.out_dir / "broad_theme_hijack_cases.jsonl", broad_rows)
    wrong_lines = ["# Phase 5 Obvious Wrong Match Cases", ""]
    wrong_lines.extend(
        f"- event_id={row['event_id']} expected={row['expected_subject_key']} {row['expected_theme_name']} "
        f"matched={row['matched_subject_key']} {row['matched_theme_name']} root_cause={row['root_cause']} "
        f"fix={row['proposed_fix']} title={row['title']}"
        for row in wrong_rows
    )
    broad_lines = ["# Phase 5 Broad Theme Hijack Cases", ""]
    broad_lines.extend(
        f"- event_id={row['event_id']} broad={row['broad_matched_subject_key']} {row['broad_matched_theme_name']} "
        f"specific={row['expected_specific_subject_key']} {row['expected_specific_theme_name']} "
        f"rank={row['specific_candidate_rank']} stage={row['problem_stage']} fix={row['proposed_fix']}"
        for row in broad_rows
    )
    (args.out_dir / "obvious_wrong_match_cases.md").write_text("\n".join(wrong_lines) + "\n", encoding="utf-8")
    (args.out_dir / "broad_theme_hijack_cases.md").write_text("\n".join(broad_lines) + "\n", encoding="utf-8")
    return {"obvious_wrong_match_count": len(wrong_rows), "broad_theme_hijack_count": len(broad_rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 5 delta reports from E2E100 attribution detail.")
    parser.add_argument("--detail", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/e2e100_phase5"))
    print(json.dumps(build(parser.parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
