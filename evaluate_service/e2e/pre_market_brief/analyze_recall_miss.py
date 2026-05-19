#!/usr/bin/env python3
"""
Phase 4.6 – Recall Miss Attribution Report Generator

Reads the latest E2E100 output and produces:
  - recall_regression_attribution_report.jsonl
  - recall_regression_attribution_report.csv
  - recall_regression_summary.md

Usage:
  python analyze_recall_miss.py \
    --run-dir evaluate_service/output/pre_market_e2e/pm_e2e_phase4_6_stream_v2_full_100_20260515_001 \
    --out-dir evaluate_service/output/pre_market_e2e/pm_e2e_phase4_6_stream_v2_full_100_20260515_001/recall_attribution
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_input_news(run_dir: str) -> dict[str, str]:
    """Return {case_id: title} from input_news.jsonl."""
    news: dict[str, str] = {}
    path = Path(run_dir) / "input_news.jsonl"
    if not path.exists():
        print(f"[warn] missing {path}", file=sys.stderr)
        return news
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cid = obj.get("case_id", "")
            title = obj.get("title", "")
            if cid:
                news[cid] = title
    return news


def load_confusion_matrix(run_dir: str) -> list[dict[str, Any]]:
    """Parse confusion_matrix.csv into list of dicts."""
    rows: list[dict[str, Any]] = []
    path = Path(run_dir) / "confusion_matrix.csv"
    if not path.exists():
        print(f"[warn] missing {path}", file=sys.stderr)
        return rows
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def extract_top5_from_db_trace(run_dir: str) -> dict[str, list[dict[str, Any]]]:
    """Extract top5 candidates per event from db_trace_report.json decision entries."""
    top5: dict[str, list[dict[str, Any]]] = {}
    path = Path(run_dir) / "db_trace_report.json"
    if not path.exists():
        print(f"[warn] missing {path}", file=sys.stderr)
        return top5
    with open(path) as f:
        report = json.load(f)
    entries = report.get("redis_streams", {}).get("decision_entries", [])
    for entry in entries:
        decision_str = entry.get("decision", "")
        if not decision_str:
            continue
        try:
            decision = json.loads(decision_str)
        except (json.JSONDecodeError, TypeError):
            continue
        match_result = decision.get("match_result", {})
        event_id = str(decision.get("event_id", ""))
        candidates = match_result.get("audit", {}).get("top_candidates", [])[:5]
        top5[event_id] = candidates
    return top5


# ── Root cause classifier ──────────────────────────────────────────

def classify_root_cause(
    status: str,
    actual_primary: str,
    gold_theme: str,
    case_id: str,
    title: str,
    top5: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (root_cause, fix_action) for one recall-miss case."""

    # ── UNKNOWN cases (actual_primary is empty) ──
    if status == "unknown" and not actual_primary:
        # These went to pending
        return ("matcher_recall_gap", "review_dense_sparse_recall_for_subject")

    # ── HUMAN_REVIEW cases ──
    if status == "human_review":
        # Check if there's a strong anchor in title
        # Common patterns for reasonable HUMAN_REVIEW:
        # - Title mentions "XR" / "MR" but not "AR" → vague
        # - Title is about general industry stats → no specific anchor
        # - Title mentions a company but not the core product

        # Heuristic: if top5 candidates include gold-related subject, it's profile narrow
        gold_related_in_top5 = any(
            gold_theme.lower() in c.get("subject_name", "").lower()
            for c in top5
        )
        if gold_related_in_top5:
            return ("profile_v2_too_narrow", "expand_profile_v2_anchors_or_alias")
        # Check for role guard block
        for c in top5:
            evidence = c.get("evidence", {})
            if evidence.get("role_guard_blocked"):
                return ("role_guard_overstrict", "review_role_guard_threshold")
        return ("reasonable_human_review", "no_fix_missing_clear_anchor")

    # ── MATCH but recall@5 miss (has actual_primary but wrong theme) ──
    # Check if title contains gold_theme anchor words
    title_lower = title.lower()
    gold_lower = gold_theme.lower()

    # Check top5 for gold match
    gold_in_top5 = False
    related_in_top5 = False
    for c in top5:
        c_name = c.get("subject_name", "").lower()
        if gold_lower in c_name or c_name in gold_lower:
            gold_in_top5 = True
        # Check neighbor/alias
        evidence = c.get("evidence", {})
        if evidence.get("theme_name_direct_hit") or evidence.get("anchor_hits"):
            if any(kw in title_lower for kw in evidence.get("anchor_hits", [])):
                related_in_top5 = True

    if not gold_in_top5:
        # Gold not in candidates at all → profile/alias gap
        # Check if title has strong anchor words for gold
        # For AR glass: "AR", "智能眼镜", "增强现实"
        # For Space: "SpaceX", "火箭", "卫星"
        # For nuclear fusion: "核聚变", "托卡马克", "EAST", "BEST"
        # For photoresist: "光刻胶"
        if "光刻胶" in title:
            # Should have hit 光刻胶 profile, but maybe matched 半导体设备 instead
            return ("neighbor_map_incomplete", "strengthen_photoresist_profile_anchor_distinction")
        if any(kw in title for kw in ["稀土", "永磁", "中重稀土"]):
            return ("neighbor_map_incomplete", "strengthen_rare_earth_profile_anchors")
        if any(kw in title for kw in ["卫星互联网", "低轨", "卫星组网", "商业航天"]):
            return ("gold_alias_incomplete", "add_satellite_internet_gold_alias_to_profile")
        if any(kw in title for kw in ["SpaceX", "星舰", "星链", "商业火箭"]):
            return ("gold_alias_incomplete", "add_spacex_related_gold_alias")
        if any(kw in title for kw in ["核聚变", "托卡马克", "人造太阳", "EAST", "BEST", "聚变"]):
            return ("neighbor_map_incomplete", "strengthen_nuclear_fusion_profile_neighbor_map")
        if any(kw in title for kw in ["AR", "智能眼镜", "增强现实", "Ray-Ban", "Vision Pro", "XR"]):
            return ("profile_v2_too_narrow", "expand_ar_glass_v2_profile_anchors")
        if "对日" in title or "日本" in title:
            return ("gold_alias_incomplete", "add_japan_sanction_gold_alias")
        if "海洋" in title or "深海" in title:
            return ("neighbor_map_incomplete", "align_marine_economy_vs_deepsea_economy")
        if "液冷" in title or "冷却" in title or "散热" in title:
            return ("profile_v2_too_narrow", "expand_liquid_cooling_v2_profile")
        if "数据中心" in title and ("芯片" in title or "NVIDIA" in title or "英伟达" in title):
            return ("reasonable_human_review", "no_fix_no_cooling_anchor_in_chip_demand_news")

        return ("matcher_recall_gap", "investigate_why_gold_not_in_dense_or_sparse_recall")

    # Gold in top5 but not selected as primary → rerank/decision issue
    for c in top5:
        c_name = c.get("subject_name", "").lower()
        if gold_lower in c_name or c_name in gold_lower:
            evidence = c.get("evidence", {})
            if evidence.get("role_guard_blocked"):
                return ("role_guard_overstrict", "review_role_guard_for_this_subject")
            return ("matcher_recall_gap", "gold_in_top5_but_not_primary_investigate_rerank")

    return ("matcher_recall_gap", "manual_review_needed")


# ── Output ─────────────────────────────────────────────────────────

def output_jsonl(rows: list[dict[str, Any]], out_dir: Path) -> None:
    path = out_dir / "recall_regression_attribution_report.jsonl"
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[done] {path}")


def output_csv(rows: list[dict[str, Any]], out_dir: Path) -> None:
    # Flatten top5 candidates for CSV
    flat_rows = []
    for row in rows:
        flat = dict(row)
        del flat["top5_candidates"]
        for i, c in enumerate(row.get("top5_candidates", [])[:5]):
            flat[f"candidate_{i+1}_name"] = c.get("subject_name", "")
            flat[f"candidate_{i+1}_key"] = str(c.get("subject_key", ""))
            flat[f"candidate_{i+1}_rerank_score"] = c.get("rerank_score", "")
        flat_rows.append(flat)

    if not flat_rows:
        return
    path = out_dir / "recall_regression_attribution_report.csv"
    fieldnames = list(flat_rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in flat_rows:
            writer.writerow(row)
    print(f"[done] {path}")


def output_md(rows: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> None:
    lines: list[str] = []
    lines.append("# Phase 4.6 Recall Miss Attribution Report")
    lines.append("")
    lines.append(f"**Run**: `pm_e2e_phase4_6_stream_v2_full_100_20260515_001`")
    lines.append(f"**Date**: 2026-05-19")
    lines.append(f"**Total events**: 100")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Primary hits**: {summary['primary_hits']}")
    lines.append(f"- **HUMAN_REVIEW**: {summary['human_review_count']}")
    lines.append(f"- **UNKNOWN decisions**: {summary['unknown_count']}")
    lines.append(f"- **MATCH but recall@5 miss**: {summary['match_but_miss']}")
    lines.append(f"- **Total recall miss samples**: {summary['total_miss']}")
    lines.append("")
    lines.append("## Root Cause Distribution")
    lines.append("")
    lines.append("| Root Cause | Count | % |")
    lines.append("|---|---|---|")
    for rc, cnt in summary["root_cause_dist"].most_common():
        pct = f"{cnt / summary['total_miss'] * 100:.1f}%"
        lines.append(f"| {rc} | {cnt} | {pct} |")
    lines.append("")

    # By gold theme
    lines.append("## Recall Miss by Gold Theme")
    lines.append("")
    theme_misses = defaultdict(list)
    for row in rows:
        theme_misses[row["gold_subject"]].append(row)
    lines.append("| Gold Theme | Miss Count | HUMAN_REVIEW | UNKNOWN | MATCH but miss |")
    lines.append("|---|---|---|---|---|")
    for theme, cases in sorted(theme_misses.items(), key=lambda x: -len(x[1])):
        hr = sum(1 for c in cases if c["actual_decision"] == "HUMAN_REVIEW")
        uk = sum(1 for c in cases if c["actual_decision"] == "UNKNOWN")
        mb = sum(1 for c in cases if c["actual_decision"] == "MATCH")
        lines.append(f"| {theme} | {len(cases)} | {hr} | {uk} | {mb} |")
    lines.append("")

    # High-frequency miss themes (≥2)
    high_freq = [(t, cs) for t, cs in theme_misses.items() if len(cs) >= 2]
    if high_freq:
        lines.append("## High-Frequency Recall Miss Themes (≥2)")
        lines.append("")
        for theme, cases in sorted(high_freq, key=lambda x: -len(x[1])):
            lines.append(f"### {theme} ({len(cases)} misses)")
            lines.append("")
            for c in cases:
                rt = "HUMAN_REVIEW" if c["actual_decision"] == "HUMAN_REVIEW" else (
                    "UNKNOWN" if c["actual_decision"] == "UNKNOWN" else "WRONG_MATCH"
                )
                lines.append(f"- `{rt}` | {c['actual_primary']} | {c['root_cause']} | {c['event_title'][:80]}...")
            lines.append("")

    # Actionable items (excluding reasonable_human_review)
    actionable = [r for r in rows if r["root_cause"] != "reasonable_human_review"]
    if actionable:
        lines.append("## Actionable Fix Items")
        lines.append("")
        lines.append(f"Total actionable: {len(actionable)}")
        lines.append("")
        by_fix = defaultdict(list)
        for r in actionable:
            by_fix[r["fix_action"]].append(r)
        for fix, cases in sorted(by_fix.items(), key=lambda x: -len(x[1])):
            lines.append(f"### {fix} ({len(cases)} cases)")
            lines.append("")
            for c in cases:
                lines.append(f"- `{c['case_id']}`: {c['event_title'][:100]}... → **{c['root_cause']}**")
            lines.append("")

    path = out_dir / "recall_regression_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"[done] {path}")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate recall miss attribution report")
    parser.add_argument("--run-dir", required=True, help="Path to E2E run output directory")
    parser.add_argument("--out-dir", default=None, help="Output directory (default: run-dir/recall_attribution)")
    args = parser.parse_args()

    run_dir = args.run_dir
    out_dir = Path(args.out_dir) if args.out_dir else Path(run_dir) / "recall_attribution"
    os.makedirs(out_dir, exist_ok=True)

    news = load_input_news(run_dir)
    matrix = load_confusion_matrix(run_dir)
    top5_map = extract_top5_from_db_trace(run_dir)

    # Build event_id → case_id map from input news (reverse lookup via decision entries)
    # We'll just map from the confusion matrix which has case_id -> decision status
    # For top5 we need event_id, but confusion matrix has case_id
    # Load the db_trace to get case_id <-> event_id mapping
    event_to_case: dict[str, str] = {}
    path = Path(run_dir) / "db_trace_report.json"
    if path.exists():
        with open(path) as f:
            report = json.load(f)
        entries = report.get("redis_streams", {}).get("decision_entries", [])
        for entry in entries:
            decision_str = entry.get("decision", "")
            if not decision_str:
                continue
            try:
                decision = json.loads(decision_str)
            except (json.JSONDecodeError, TypeError):
                continue
            eid = str(decision.get("event_id", ""))
            cid = decision.get("case_id", "")
            if eid and cid:
                event_to_case[eid] = cid

    # Classify each recall-miss case
    recall_rows: list[dict[str, Any]] = []
    primary_hits = 0
    human_review_count = 0
    unknown_count = 0

    for row in matrix:
        case_id = row.get("case_id", "")
        gold = row.get("gold_theme_name", "")
        primary = row.get("primary_theme_name", "")
        related = row.get("related_theme_names", "")
        status = row.get("status", "")

        if status == "exact_or_alias_primary":
            primary_hits += 1
            continue

        title = news.get(case_id, f"(missing title for {case_id})")

        # Get top5 for this case via event_id mapping
        top5: list[dict[str, Any]] = []
        # Search db_trace entries with matching case_id in decision JSON
        # We parse from db_trace already
        # Map case_id -> top5 candidates
        path = Path(run_dir) / "db_trace_report.json"
        if path.exists():
            with open(path) as f:
                report = json.load(f)
            entries = report.get("redis_streams", {}).get("decision_entries", [])
            for entry in entries:
                decision_str = entry.get("decision", "")
                if not decision_str:
                    continue
                try:
                    decision = json.loads(decision_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                if decision.get("case_id") == case_id:
                    top5 = decision.get("match_result", {}).get("audit", {}).get("top_candidates", [])[:5]
                    break

        actual_decision = "UNKNOWN" if (status == "unknown" and not primary) else (
            "HUMAN_REVIEW" if status == "human_review" else "MATCH"
        )

        if actual_decision == "HUMAN_REVIEW":
            human_review_count += 1
        elif actual_decision == "UNKNOWN":
            unknown_count += 1

        root_cause, fix_action = classify_root_cause(
            status, primary, gold, case_id, title, top5
        )

        recall_rows.append({
            "case_id": case_id,
            "event_title": title,
            "gold_subject": gold,
            "actual_decision": actual_decision,
            "actual_primary": primary or "(none)",
            "actual_related": related or "(none)",
            "top5_candidates": [
                {
                    "name": c.get("subject_name", ""),
                    "key": str(c.get("subject_key", "")),
                    "rerank_score": c.get("rerank_score", ""),
                    "role_guard_blocked": c.get("evidence", {}).get("role_guard_blocked", False),
                }
                for c in top5
            ],
            "miss_type": status,
            "root_cause": root_cause,
            "fix_action": fix_action,
        })

    match_but_miss = sum(1 for r in recall_rows if r["actual_decision"] == "MATCH")
    total_miss = len(recall_rows)

    rc_dist = Counter(r["root_cause"] for r in recall_rows)

    summary = {
        "primary_hits": primary_hits,
        "human_review_count": human_review_count,
        "unknown_count": unknown_count,
        "match_but_miss": match_but_miss,
        "total_miss": total_miss,
        "root_cause_dist": rc_dist,
    }

    output_jsonl(recall_rows, out_dir)
    output_csv(recall_rows, out_dir)
    output_md(recall_rows, summary, out_dir)

    # Print summary to stdout
    print(f"\n=== Recall Miss Summary ===")
    print(f"Primary hits: {primary_hits}")
    print(f"HUMAN_REVIEW: {human_review_count}")
    print(f"UNKNOWN: {unknown_count}")
    print(f"MATCH but recall@5 miss: {match_but_miss}")
    print(f"Total recall miss: {total_miss}")
    print(f"\nRoot Cause Distribution:")
    for rc, cnt in rc_dist.most_common():
        print(f"  {rc}: {cnt}")


if __name__ == "__main__":
    main()
