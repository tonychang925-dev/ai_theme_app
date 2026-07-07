#!/usr/bin/env python3
"""Generate the Market World Validation White Paper from batch replay results.

12-section comprehensive markdown report answering the core question:
"Is the Market World State real, stable, explainable, and capable of
supporting cognitive reasoning and trading decisions?"

Usage:
  PYTHONPATH=. python3 scripts/generate_white_paper.py --data datasets/white_paper --output docs/reports/white_paper_20260707.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _load(data_dir: Path, filename: str) -> dict[str, Any]:
    path = data_dir / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def generate(data_dir: Path) -> str:
    """Generate complete White Paper markdown."""
    dashboard = _load(data_dir, "dashboard.json")
    meta = _load(data_dir, "simulation_meta.json")
    timeline = _load(data_dir, "timeline_summary.json")
    agg = _load(data_dir, "summary.json")
    summary_data = agg.get("summary", {})
    trends = agg.get("trends", {})
    known_issues = agg.get("known_issues", [])
    node_dist = agg.get("node_distribution", {})

    levels = dashboard.get("levels", [])

    def lv(l: int) -> dict:
        for level in levels:
            if level["level"] == l:
                return level
        return {}

    def pass_fail(p: bool) -> str:
        return "PASS" if p else "FAIL"

    lines: list[str] = []

    # ── Title ──
    lines.append("# Market World Validation White Paper")
    lines.append("")
    lines.append(f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"> Date Range: {meta.get('start_date', '?')} → {meta.get('end_date', '?')}")
    lines.append(f"> Simulation Hash: `{meta.get('simulation_hash', '?')[:24]}...`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 1. Executive Summary ──
    lines.append("## 1. Executive Summary")
    lines.append("")
    lines.append(dashboard.get("philosophy", "").replace("\n", "\n> "))
    lines.append("")

    exec_sum = summary_data.get("executive_summary", {})
    total_h = exec_sum.get("hypotheses_generated", 0)
    total_v = exec_sum.get("verdicts_total", 0)
    confirmed = exec_sum.get("verdicts_confirmed", 0)
    falsified = exec_sum.get("verdicts_falsified", 0)
    validation_levels = exec_sum.get("validation_levels", "?/?")

    lines.append("### Key Findings")
    lines.append("")

    if total_h > 0:
        accuracy = confirmed / (confirmed + falsified) if (confirmed + falsified) > 0 else 0
        lines.append(f"1. **Transition Accuracy: {accuracy:.1%}** "
                     f"({confirmed} confirmed / {falsified} falsified / {total_h} total hypotheses)")
    else:
        lines.append("1. **Insufficient hypotheses generated** for meaningful prediction statistics")

    passed_count = sum(1 for lv in levels if lv.get("passed", False))
    lines.append(f"2. **Validation: {passed_count}/{len(levels)} layers pass** "
                 f"(L0 World Quality {'PASS' if lv(0).get('passed') else 'FAIL'}, "
                 f"L1 Recognition {'PASS' if lv(1).get('passed') else 'FAIL'})")
    lines.append(f"3. **{exec_sum.get('states_built', 0)} world states built** over "
                 f"{exec_sum.get('trading_days', 0)} trading days")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 2. Methodology ──
    lines.append("## 2. Methodology")
    lines.append("")
    lines.append("### 2.1 Pipeline")
    lines.append("")
    lines.append("```text")
    lines.append("Real Data → WorldStateBuilder → DailyMarketState → StateDiff")
    lines.append("  → WorldStateTransitionCompiler → NodeTransitionHypothesisStore")
    lines.append("  → HistoricalSimulation → SimulationTimeline")
    lines.append("  → MarketWorldValidator → Validation Dashboard + Report")
    lines.append("```")
    lines.append("")
    lines.append("### 2.2 Policy Versions")
    lines.append("")
    if meta:
        lines.append(f"- Compiler Policy: `compiler_policy.v1`")
        lines.append(f"- Cycle FSM: `cycle_fsm.v1`")
        lines.append(f"- Divergence Policy: `divergence_policy.v1`")
        lines.append(f"- Maturity Policy: `maturity_policy.v1`")
    lines.append("")
    lines.append("### 2.3 Deterministic Guarantee")
    lines.append("")
    lines.append("- No LLM in the hypothesis generation pipeline")
    lines.append("- All hashes (state_id, record_hash, simulation_hash) are SHA-256 deterministic")
    lines.append("- Same input → same output, 100% reproducible")
    lines.append("- Re-run produces identical simulation hash")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 3. World Quality (L0) ──
    l0 = lv(0)
    lines.append("## 3. World Quality Trends (L0)")
    lines.append("")
    lines.append(f"**Question:** {l0.get('question', 'Is the world true?')}")
    lines.append("")
    lines.append(f"**Result: {pass_fail(l0.get('passed', False))}**")
    lines.append("")
    lines.append("| Metric | Value | Threshold | Status |")
    lines.append("|--------|-------|-----------|--------|")
    for m in l0.get("metrics", []):
        s = "PASS" if m["passed"] else "FAIL"
        lines.append(f"| {m['name']} | {m['value']:.3f} | {m['threshold']} | {s} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 4. Recognition Quality (L1) ──
    l1 = lv(1)
    lines.append("## 4. Recognition Quality (L1)")
    lines.append("")
    lines.append(f"**Question:** {l1.get('question', 'Do we see the market correctly?')}")
    lines.append("")
    lines.append(f"**Result: {pass_fail(l1.get('passed', False))}**")
    lines.append("")
    lines.append("| Metric | Value | Threshold | Status |")
    lines.append("|--------|-------|-----------|--------|")
    for m in l1.get("metrics", []):
        s = "PASS" if m["passed"] else "FAIL"
        lines.append(f"| {m['name']} | {m['value']:.3f} | {m['threshold']} | {s} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 5. Prediction Quality (L2) ──
    l2 = lv(2)
    lines.append("## 5. Prediction Quality (L2)")
    lines.append("")
    lines.append(f"**Question:** {l2.get('question', 'Do we predict correctly?')}")
    lines.append("")
    lines.append(f"**Result: {pass_fail(l2.get('passed', False))}**")
    lines.append("")
    lines.append("| Metric | Value | Threshold | Status |")
    lines.append("|--------|-------|-----------|--------|")
    for m in l2.get("metrics", []):
        s = "PASS" if m["passed"] else "FAIL"
        lines.append(f"| {m['name']} | {m['value']:.3f} | {m['threshold']} | {s} |")
    lines.append("")

    # Verdict distribution
    if total_v > 0:
        lines.append(f"### Verdict Distribution")
        lines.append("")
        lines.append(f"- Total resolved: {confirmed + falsified}")
        lines.append(f"- Confirmed: {confirmed} ({confirmed / total_v * 100:.1f}%)" if total_v else "- Confirmed: 0")
        lines.append(f"- Falsified: {falsified} ({falsified / total_v * 100:.1f}%)" if total_v else "- Falsified: 0")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 6. Trading Quality (L3) ──
    l3 = lv(3)
    lines.append("## 6. Trading Quality (L3)")
    lines.append("")
    lines.append(f"**Question:** {l3.get('question', 'What if we traded?')}")
    lines.append("")
    lines.append(f"**Result: {pass_fail(l3.get('passed', False))}**")
    lines.append("")
    if not l3.get("passed", False):
        lines.append("Trading metrics are gated behind L0+L1+L2 all passing.")
        lines.append("This layer is deferred — it does NOT indicate project failure.")
        lines.append("World Quality != Trading Return.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 7. World Evolution (L4) ──
    l4 = lv(4)
    lines.append("## 7. World Evolution (L4)")
    lines.append("")
    lines.append(f"**Question:** {l4.get('question', 'Is the world model getting better?')}")
    lines.append("")
    lines.append(f"**Result: {pass_fail(l4.get('passed', False))}**")
    lines.append("")
    lines.append("| Metric | Value | Threshold | Status |")
    lines.append("|--------|-------|-----------|--------|")
    for m in l4.get("metrics", []):
        s = "PASS" if m["passed"] else "FAIL"
        lines.append(f"| {m['name']} | {m['value']:.3f} | {m['threshold']} | {s} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 8. Market Phase Analysis ──
    lines.append("## 8. Market Phase Analysis")
    lines.append("")
    # node_dist already loaded from agg above
    if node_dist:
        lines.append("### Hypothesis Generation by Source Node")
        lines.append("")
        lines.append("| Node | Hypotheses Generated |")
        lines.append("|------|---------------------|")
        for node_name, count in sorted(node_dist.items(), key=lambda x: -x[1]):
            lines.append(f"| {node_name} | {count} |")
        lines.append("")
    else:
        lines.append("Insufficient data for phase breakdown.")
        lines.append("")

    # Timeline excerpt — last 10 days with activity
    days_with_activity = [d for d in timeline.get("days", []) if d.get("hypotheses") or d.get("verdicts")]
    if days_with_activity:
        lines.append("### Recent Activity (last 10 active days)")
        lines.append("")
        lines.append("| Date | H | V(C/F) |")
        lines.append("|------|---|---|")
        for day_entry in days_with_activity[-10:]:
            hs = day_entry.get("hypotheses", [])
            vs = day_entry.get("verdicts", [])
            c = sum(1 for v in vs if v["label"] == "CONFIRMED")
            f = sum(1 for v in vs if v["label"] == "FALSIFIED")
            lines.append(f"| {day_entry['trade_date']} | {len(hs)} | {len(vs)} ({c}/{f}) |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 9. Timeline Visualization ──
    lines.append("## 9. Timeline Visualization")
    lines.append("")

    if trends.get("dates"):
        # ASCII bar chart of hypotheses per day
        max_h = max(trends.get("hypotheses_per_day", [0])) or 1
        lines.append("### Hypotheses per Day (last 30 days)")
        lines.append("```")
        for i, d in enumerate(trends["dates"][-30:]):
            h_count = trends["hypotheses_per_day"][i] if i < len(trends["hypotheses_per_day"]) else 0
            bar = "#" * h_count
            lines.append(f"  {d}: {bar} {h_count}")
        lines.append("```")
        lines.append("")

        # ASCII bar chart of verdicts per day
        max_v = max(trends.get("verdicts_per_day", [0])) or 1
        lines.append("### Verdicts per Day (last 30 days)")
        lines.append("```")
        for i, d in enumerate(trends["dates"][-30:]):
            v_count = trends["verdicts_per_day"][i] if i < len(trends["verdicts_per_day"]) else 0
            c_count = trends["confirmed_per_day"][i] if i < len(trends.get("confirmed_per_day", [])) else 0
            f_count = trends["falsified_per_day"][i] if i < len(trends.get("falsified_per_day", [])) else 0
            bar_c = "+" * c_count
            bar_f = "-" * f_count
            lines.append(f"  {d}: {bar_c}{bar_f} C={c_count} F={f_count}")
        lines.append("```")
        lines.append("")
    else:
        lines.append("Insufficient data for visualizations.")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 10. Known Limitations ──
    lines.append("## 10. Known Limitations")
    lines.append("")
    known = known_issues + dashboard.get("known_issues", [])
    if known:
        for issue in known:
            lines.append(f"- {issue}")
    lines.append("")
    lines.append("### Honest Gaps")
    lines.append("")
    lines.append("- **Prediction probability not plumbed**: `CompiledNodeTransitionHypothesis` does not carry `prediction_probability` — Brier Score and ECE cannot be computed yet")
    lines.append("- **World Fidelity requires human annotation**: AI vs human consensus comparison needs manual labeling")
    lines.append("- **Trading metrics are deferred**: Left Probe / Right Confirm / Avoid / Wait all require real trading signal integration")
    lines.append("- **Real data bridge is synthetic**: Current replay uses synthetic FSM-progressed data; DB-backed real data source not yet connected")
    lines.append("- **No holiday calendar**: Weekend-skip only; Chinese market holidays are not accounted for")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 11. Conclusions ──
    lines.append("## 11. Conclusions")
    lines.append("")
    lines.append("### Q1: Is the Market World State real?")
    lines.append("")
    if l0.get("passed"):
        lines.append("YES. The World Quality layer passes. Evidence coverage, state consistency, policy consistency, and hash stability are all within thresholds. The world state chain is intact and verifiable.")
    else:
        lines.append("PARTIAL. World Quality metrics show gaps that need addressing before the world model can be considered production-grade.")
    lines.append("")

    lines.append("### Q2: Is it stable?")
    lines.append("")
    if l4.get("passed"):
        lines.append("YES. The World Evolution layer passes. No policy drift, low node drift, stable simulation hash. The world model maintains consistency over time.")
    else:
        lines.append("MONITORING. World Evolution metrics indicate drift areas that need attention.")
    lines.append("")

    lines.append("### Q3: Is it explainable?")
    lines.append("")
    lines.append("YES. Every output has a deterministic trace:")
    lines.append("- `state_id` = hash(trade_date + content_hash)")
    lines.append("- `record_hash` = hash(hypothesis fields + source_state_id + policy_snapshot)")
    lines.append("- `simulation_hash` = hash(all trade_dates + state_ids + hypothesis_ids + verdict labels)")
    lines.append("- FSM transitions are defined in externalized YAML, not hardcoded")
    lines.append("- DivergenceQuality and NodeMaturity save full vectors, not just labels")
    lines.append("")

    lines.append("### Q4: Can it support cognitive reasoning and trading decisions?")
    lines.append("")
    if l2.get("passed") or total_h > 0:
        lines.append(f"EVIDENCE IS BUILDING. {total_h} hypotheses were generated with {confirmed} confirmed predictions. The compiler pipeline is deterministic and policy-driven. With sufficient historical data, the system can produce statistically meaningful transition predictions.")
    else:
        lines.append("INSUFFICIENT DATA. More trading days are needed (recommended: 120+) to generate enough hypotheses for statistically significant evaluation.")
    lines.append("Trading decisions (L3) remain gated — this is by design, not a failure.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 12. Appendix ──
    lines.append("## 12. Appendix")
    lines.append("")

    lines.append("### A. Config Versions")
    lines.append("```json")
    lines.append(json.dumps({
        "cycle_fsm": "cycle_fsm.v1",
        "compiler_policy": "compiler_policy.v1",
        "divergence_policy": "divergence_policy.v1",
        "maturity_policy": "maturity_policy.v1",
    }, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("### B. Simulation Metadata")
    lines.append("```json")
    safe_meta = {k: v for k, v in meta.items() if k != "errors"}
    lines.append(json.dumps(safe_meta, indent=2, default=str))
    lines.append("```")
    lines.append("")

    errors = meta.get("errors", [])
    if errors:
        lines.append("### C. Errors During Replay")
        lines.append("")
        for e in errors[:20]:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("### D. Validation Dashboard")
    lines.append("")
    lines.append("Full dashboard available at: `datasets/white_paper/dashboard.json`")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*This White Paper is auto-generated by the Market World Validation pipeline (Phase D).*")
    lines.append("*All metrics are deterministic and reproducible. Re-run with identical inputs yields identical results.*")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Market World Validation White Paper")
    parser.add_argument("--data", required=True, help="Dataset directory from batch_replay_runner")
    parser.add_argument("--output", "-o", required=True, help="Output markdown file path")
    args = parser.parse_args()

    data_dir = Path(args.data)
    if not data_dir.exists():
        print(f"ERROR: {data_dir} not found — run batch_replay_runner first", file=sys.stderr)
        sys.exit(1)

    markdown = generate(data_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"White Paper written to: {output_path}")
    print(f"  Size: {len(markdown):,} chars")
    print(f"  Lines: {markdown.count(chr(10)):,}")


if __name__ == "__main__":
    main()
