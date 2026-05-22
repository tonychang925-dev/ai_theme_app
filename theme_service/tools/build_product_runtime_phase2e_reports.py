from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _md(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")[:240]


def _root_cause(row: dict[str, Any]) -> tuple[str, str]:
    subject_key = str(row.get("new_subject_key") or "")
    title = str(row.get("title") or "")
    evidence = row.get("best_evidence") if isinstance(row.get("best_evidence"), dict) else {}
    terms = evidence.get("hit_terms") or evidence.get("anchor_hits") or []
    if subject_key == "9011554":
        return "low_value_financial_report_direct_hit", "block ordinary earnings reports unless game catalyst terms are present"
    if subject_key == "9014347":
        return "low_value_clarification_industry_direct_hit", "block clarification/risk-warning notices from matching industry theme by company attribute"
    if subject_key == "9063773":
        return "bad_v2_anchor_pollution", f"remove weak anchor terms from 字节Seedance profile: {terms}"
    if subject_key == "9041906":
        return "bad_v1_fallback_generic_ai_anchor", "add accepted v2 profile and move AI/model-review terms to no_anchor/negative"
    return "replay_residual_match", "manual review and add precise hard negative if confirmed wrong"


def build(args: argparse.Namespace) -> dict[str, int]:
    rows = _read_jsonl(args.replay_detail)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("quarantine_matches") or row.get("new_decision") != "MATCH":
            continue
        root_cause, proposed_fix = _root_cause(row)
        old = row.get("quarantine_matches")[0] if row.get("quarantine_matches") else {}
        cases.append(
            {
                "event_id": row.get("event_id"),
                "title": row.get("title"),
                "old_subject_key": old.get("subject_key") or row.get("old_subject_key"),
                "old_theme_name": old.get("subject_name") or row.get("old_theme_name"),
                "new_subject_key": row.get("new_subject_key"),
                "new_theme_name": row.get("new_theme_name"),
                "new_reason_code": row.get("new_reason_code"),
                "new_match_reason": row.get("new_match_reason"),
                "runtime_source": row.get("runtime_source"),
                "best_evidence": row.get("best_evidence") or {},
                "accepted_anchor_hits": row.get("accepted_anchor_hits") or [],
                "direct_hit_terms": row.get("direct_hit_terms") or [],
                "root_cause": root_cause,
                "proposed_fix": proposed_fix,
            }
        )
    _write_jsonl(args.out_dir / "quarantine_still_match_cases.jsonl", cases)
    lines = [
        "# Phase 2E Quarantine Still MATCH Cases",
        "",
        f"- count: {len(cases)}",
        "",
        "| event_id | title | old | new | reason | source | root_cause | proposed_fix |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in cases:
        lines.append(
            f"| {row['event_id']} | {_md(row['title'])} | "
            f"{row.get('old_subject_key')} {_md(row.get('old_theme_name'))} | "
            f"{row.get('new_subject_key')} {_md(row.get('new_theme_name'))} | "
            f"{row.get('new_reason_code')} | {row.get('runtime_source')} | "
            f"{row.get('root_cause')} | {_md(row.get('proposed_fix'))} |"
        )
    (args.out_dir / "quarantine_still_match_cases.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"quarantine_still_match_count": len(cases)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Product Runtime Phase 2E residual replay reports.")
    parser.add_argument("--replay-detail", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/product_runtime_0522_phase2e"))
    print(json.dumps(build(parser.parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
