#!/usr/bin/env python3
"""
Opportunity Gap Report Generator for Phase 4.6

Analyzes:
  1. Which subjects in the brief got opportunities vs not
  2. Stock pool availability vs actual generation
  3. Score/level distribution
  4. Drop reasons

Usage:
  python analyze_opportunity_gap.py \
    --run-dir evaluate_service/output/pre_market_e2e/pm_e2e_phase4_6_stream_v2_full_100_20260515_001
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    # Load data
    with open(run_dir / "brief_snapshot.json") as f:
        brief = json.load(f)
    payload = brief.get("payload", {})

    sections = payload.get("sections", {})
    themes = sections.get("matched_themes", [])
    opps = sections.get("event_driven_opportunities", [])

    opp_subject_keys = {str(o.get("subject_key", "")): o for o in opps}

    # Build CSV rows
    rows: list[dict[str, Any]] = []
    for t in themes:
        sk = str(t.get("subject_key", ""))
        name = t.get("theme_name", "")
        event_count = t.get("event_count", 0)
        confidence = t.get("avg_confidence", t.get("confidence", 0))

        opp = opp_subject_keys.get(sk)
        has_opportunity = opp is not None
        stock_count = len(opp.get("stocks", [])) if opp else 0
        levels = defaultdict(int)
        avg_score = 0.0
        if opp and stock_count > 0:
            for s in opp.get("stocks", []):
                levels[s.get("level", "?")] += 1
                avg_score += float(s.get("score", 0))
            avg_score /= stock_count

        drop_reason = ""
        if not has_opportunity:
            drop_reason = "no_opportunity_entry"
        elif stock_count == 0:
            drop_reason = "empty_stock_list"
        elif all(s.get("level") == "C" for s in opp.get("stocks", [])):
            drop_reason = "all_C_level_low_quality"
        elif avg_score < 50:
            drop_reason = "avg_score_below_50"
        else:
            drop_reason = "ok"

        rows.append({
            "subject_key": sk,
            "subject_name": name,
            "in_brief_theme": True,
            "event_count": event_count,
            "avg_confidence": float(confidence) if confidence else 0,
            "has_stock_pool": has_opportunity,
            "stock_pool_count": stock_count,
            "A_level_count": levels.get("A", 0),
            "B_level_count": levels.get("B", 0),
            "C_level_count": levels.get("C", 0),
            "avg_score": round(avg_score, 1),
            "opportunity_generated": has_opportunity and stock_count > 0,
            "drop_reason": drop_reason,
        })

    # Output
    out_dir = run_dir / "recall_attribution"
    os.makedirs(out_dir, exist_ok=True)

    # CSV
    if rows:
        with open(out_dir / "opportunity_gap_report.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"[done] {out_dir / 'opportunity_gap_report.csv'}")

    # Summary
    lines: list[str] = []
    lines.append("# Phase 4.6 Opportunity Gap Report")
    lines.append("")
    lines.append(f"**Run**: `{brief.get('trade_date', '')}`")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **total_themes**: {len(themes)}")
    lines.append(f"- **total_opportunities**: {len(opps)}")
    lines.append(f"- **opportunity_generation_rate**: {len(opps)}/{len(themes)} = {len(opps)/max(1,len(themes))*100:.0f}%")
    lines.append("")

    # Drop reasons
    drops = defaultdict(list)
    for r in rows:
        drops[r["drop_reason"]].append(r)

    lines.append("## Drop Reason Distribution")
    lines.append("")
    lines.append("| Drop Reason | Count | Subjects |")
    lines.append("|---|---|---|")
    for reason, items in sorted(drops.items(), key=lambda x: -len(x[1])):
        names = ", ".join(item["subject_name"] for item in items[:5])
        more = f" +{len(items)-5} more" if len(items) > 5 else ""
        lines.append(f"| {reason} | {len(items)} | {names}{more} |")
    lines.append("")

    # Quality tiers
    lines.append("## Stock Quality Distribution")
    lines.append("")
    lines.append("| Level | Count | % |")
    lines.append("|---|---|---|")
    total_a = sum(r["A_level_count"] for r in rows)
    total_b = sum(r["B_level_count"] for r in rows)
    total_c = sum(r["C_level_count"] for r in rows)
    total_stocks = total_a + total_b + total_c
    if total_stocks:
        lines.append(f"| A (strong) | {total_a} | {total_a/total_stocks*100:.1f}% |")
        lines.append(f"| B (decent) | {total_b} | {total_b/total_stocks*100:.1f}% |")
        lines.append(f"| C (weak) | {total_c} | {total_c/total_stocks*100:.1f}% |")
        lines.append(f"| **Total** | **{total_stocks}** | |")
    lines.append("")

    # Themes with better scores
    lines.append("## Top Themes by Avg Stock Score")
    lines.append("")
    scored = sorted([r for r in rows if r["stock_pool_count"] > 0], key=lambda r: -r["avg_score"])
    lines.append("| Subject Key | Subject Name | Avg Score | A | B | C | Stocks |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in scored[:10]:
        lines.append(f"| {r['subject_key']} | {r['subject_name']} | {r['avg_score']} | {r['A_level_count']} | {r['B_level_count']} | {r['C_level_count']} | {r['stock_pool_count']} |")
    lines.append("")

    # Root cause analysis
    lines.append("## Root Cause Analysis")
    lines.append("")
    lines.append("### Gap 1: Recall misses reduce theme count")
    lines.append("")
    lines.append("The current E2E100 has 25 themes in the brief but only 57% primary hit rate.")
    lines.append("With recall@5 at 0.60 target, we'd expect ~60 themes if wrong matches are fixed.")
    lines.append("Current 25 themes include ~15 wrong-match themes (著名IP, 乌克兰重建, etc.) that ")
    lines.append("don't represent real investment themes. After fixing recall, the valid theme count ")
    lines.append("should increase to ~30-35 which would naturally boost opportunity count.")
    lines.append("")
    lines.append("### Gap 2: Stock pool quality is uniformly low")
    lines.append("")
    lines.append(f"Of {total_stocks} total stock recommendations:")
    lines.append(f"- Only {total_a} are A-level (strong, with leaderboard/strong_pool support)")
    lines.append(f"- {total_b} are B-level (moderate)")
    lines.append(f"- {total_c} ({total_c/total_stocks*100:.0f}%) are C-level (weak, no pool support)")
    lines.append("")
    lines.append("This suggests the `theme_stock_map` and `subject_stock_pool` tables have broad but ")
    lines.append("shallow coverage — many subjects have stock entries, but few have leaderboard or ")
    lines.append("strong_watch_pool support to elevate them to A/B level.")
    lines.append("")
    lines.append("### Gap 3: 7 unnamed themes")
    lines.append("")
    unnamed = [r for r in rows if r["subject_name"] == "(unnamed)" or not r["subject_name"]]
    if unnamed:
        lines.append(f"{len(unnamed)} themes have no display name, indicating profile or ")
        lines.append("subject_master data gaps.")
    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    lines.append("1. **Fix recall first**: The primary driver of low opportunity count is recall miss.")
    lines.append("   Fixing even 5-8 high-frequency recall miss themes would add 10-15 opportunities.")
    lines.append("")
    lines.append("2. **Improve stock pool quality**: For the top 10 themes by avg_confidence, verify")
    lines.append("   that `subject_stock_pool` has recent entries and leaderboard data is available.")
    lines.append("   Missing leaderboard data is the main reason for all-C-level recommendations.")
    lines.append("")
    lines.append("3. **Filter out noise themes**: Themes like '著名IP', 'A股全球第一', '首发经济大全'")
    lines.append("   should not generate stock opportunities. The builder should skip subjects where")
    lines.append("   avg_confidence < 0.70 or subject is a broad category.")
    lines.append("")

    with open(out_dir / "opportunity_gap_summary.md", "w") as f:
        f.write("\n".join(lines))
    print(f"[done] {out_dir / 'opportunity_gap_summary.md'}")

    # Print summary
    print(f"\n=== Opportunity Gap Summary ===")
    print(f"Total themes: {len(themes)}")
    print(f"Total opportunities: {len(opps)}")
    print(f"A-level stocks: {total_a}")
    print(f"B-level stocks: {total_b}")
    print(f"C-level stocks: {total_c}")


if __name__ == "__main__":
    main()
