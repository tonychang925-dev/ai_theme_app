"""Phase 4.4 — Calibration Dashboard / Report Export.

Generates a comprehensive calibration_dashboard.md from replay output.
Reads aggregate_report.json + daily/*.turing.json + daily/*.alignment.json.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


class CalibrationDashboard:
    """Generate calibration dashboard from replay output directory."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.daily_dir = self.output_dir / "daily"
        self._load()

    def _load(self):
        with open(self.output_dir / "aggregate_report.json") as f:
            self.agg = json.load(f)

        self.daily_turing: dict[str, dict] = {}
        self.daily_alignment: dict[str, dict] = {}
        for fpath in sorted(self.daily_dir.glob("*.turing.json")):
            td = fpath.stem.replace(".turing", "")
            self.daily_turing[td] = json.loads(fpath.read_text())
        for fpath in sorted(self.daily_dir.glob("*.alignment.json")):
            td = fpath.stem.replace(".alignment", "")
            self.daily_alignment[td] = json.loads(fpath.read_text())

    def generate(self) -> str:
        lines = [
            "# M8 Analyst Alignment — Calibration Dashboard",
            "",
            f"**Period**: {self.agg.get('start_date', '?')} ~ {self.agg.get('end_date', '?')}",
            f"**Trading days**: {self.agg.get('trading_days', 0)}",
            f"**Skipped**: {len(self.agg.get('skipped_days', []))}  |  "
            f"**Partial**: {len(self.agg.get('partial_days', []))}",
            "",
            "---",
            "",
            self._section_score_summary(),
            self._section_gap_classification(),
            self._section_daily_trend(),
            self._section_component_trend(),
            self._section_calibration_hints(),
            self._section_dnf_drilldown(),
            self._section_phase_timeline(),
        ]
        return "\n".join(lines)

    # ── Sections ──

    def _section_score_summary(self) -> str:
        s = self.agg["scores"]
        lines = [
            "## 1. Score Summary",
            "",
            "| Metric | Raw | Fair |",
            "|--------|----:|-----:|",
            f"| Average ATS | {s.get('average', 0):.3f} | {s.get('fair_average', s.get('average',0)):.3f} |",
            f"| Median ATS | {s.get('median', 0):.3f} | — |",
            f"| Min / Max | {s.get('min', 0):.3f} / {s.get('max', 0):.3f} | — |",
            "",
            "### Grade Distribution",
            "",
            "| Grade | Count | % |",
            "|-------|------:|--:|",
        ]
        grades = self.agg.get("grade_distribution", {})
        total = sum(grades.values()) or 1
        for g in ("A", "B", "C", "D", "F"):
            c = grades.get(g, 0)
            lines.append(f"| {g} | {c} | {c/total:.0%} |")
        lines.append("")
        return "\n".join(lines)

    def _section_gap_classification(self) -> str:
        gaps = self.agg.get("gap_days", {})
        if not gaps:
            return "## 2. Gap Classification\n\n_No gap data available._\n"

        lines = [
            "## 2. Gap Classification",
            "",
            "| Date | Gap Type | Raw | Fair | Excluded | Reason |",
            "|------|----------|----:|-----:|----------|--------|",
        ]
        for td, g in sorted(gaps.items()):
            if g.get("gap_type", "NONE") == "NONE":
                continue
            excl = "✓" if g.get("excluded_from_dnf") else ""
            lines.append(
                f"| {td} | {g['gap_type']} | {g['raw_score']:.3f} | "
                f"{g['fair_score']:.3f} | {excl} | {g.get('reason', '')[:60]} |"
            )

        if all(g.get("gap_type", "NONE") == "NONE" for g in gaps.values()):
            lines.append("| — | No gaps classified | — | — | — | — |")
        lines.append("")
        return "\n".join(lines)

    def _section_daily_trend(self) -> str:
        lines = [
            "## 3. Daily Score Trend",
            "",
            "| Date | Grade | ATS | Phase | Facts | Relay | Strategy | Th/Ld | Key Issue |",
            "|------|-------|----:|-------|------:|------:|---------:|------:|-----------|",
        ]
        for td in sorted(self.daily_turing):
            t = self.daily_turing[td]
            s = t["scores"]
            a = self.daily_alignment.get(td, {})

            # Phase detail
            phase_info = "—"
            for d in a.get("emotion_diffs", []):
                if "market_phase" in d.get("field_path", ""):
                    phase_info = f"{d.get('analyst_label','?')}={d.get('ai_label','?')}"

            # Key issue
            issues = []
            for d in a.get("fact_diffs", []) + a.get("relay_diffs", []):
                if not d.get("passed") and not d.get("excluded"):
                    issues.append(d["field_path"].split(".")[-1])
            key_issue = ", ".join(issues[:2]) if issues else "—"

            lines.append(
                f"| {td} | {t.get('grade','?')} | {s['overall']:.3f} | {phase_info} | "
                f"{s.get('facts',0):.3f} | {s.get('relay',0):.3f} | "
                f"{s.get('strategy',0):.3f} | {s.get('theme_leader',0):.3f} | "
                f"{key_issue} |"
            )
        lines.append("")
        return "\n".join(lines)

    def _section_component_trend(self) -> str:
        lines = [
            "## 4. Component Score Trend",
            "",
            "| Date | Phase | Risk | Facts | Relay | Strategy | Theme/Ld |",
            "|------|------:|-----:|------:|------:|---------:|---------:|",
        ]
        comps = self.agg.get("component_averages", {})
        lines.append(
            f"| **Avg** | **{comps.get('phase',0):.3f}** | **{comps.get('risk',0):.3f}** | "
            f"**{comps.get('facts',0):.3f}** | **{comps.get('relay',0):.3f}** | "
            f"**{comps.get('strategy',0):.3f}** | **{comps.get('theme_leader',0):.3f}** |"
        )
        lines.append("| | | | | | | |")

        for td in sorted(self.daily_turing):
            s = self.daily_turing[td]["scores"]
            lines.append(
                f"| {td} | {s.get('phase',0):.3f} | {s.get('risk',0):.3f} | "
                f"{s.get('facts',0):.3f} | {s.get('relay',0):.3f} | "
                f"{s.get('strategy',0):.3f} | {s.get('theme_leader',0):.3f} |"
            )
        lines.append("")
        return "\n".join(lines)

    def _section_calibration_hints(self) -> str:
        hints = self.agg.get("common_calibration_hints", {})
        lines = [
            "## 5. Calibration Hints Ranking",
            "",
        ]
        if not hints:
            lines.append("_No calibration hints generated._")
        else:
            lines.append("| Rank | Hint | Frequency |")
            lines.append("|-----:|------|----------:|")
            for i, (hint, count) in enumerate(
                sorted(hints.items(), key=lambda x: -x[1]), 1
            ):
                lines.append(f"| {i} | {hint} | {count} |")

        lines.append("")
        lines.append("### Hint Reference")
        lines.append("")
        lines.append("| Hint | Meaning | Action |")
        lines.append("|------|---------|--------|")
        refs = [
            ("PHASE_RULE_REVIEW", "Phase detection rules need recalibration", "Review phase ontology mappings"),
            ("FACT_SOURCE_REVIEW", "Fact-layer data sources may be stale", "Check M2.5 data pipeline"),
            ("RELAY_ECOLOGY_REVIEW", "Relay ecology metrics need calibration", "Review relay formula vs analyst"),
            ("STRATEGY_MAPPING_REVIEW", "Strategy mapping logic needs revision", "Upgrade intent matching / add intents"),
            ("THEME_LIFECYCLE_REVIEW", "Theme lifecycle detection needs improvement", "Check theme alias coverage"),
            ("RISK_GATE_REVIEW", "Risk gate thresholds may need adjustment", "Review risk confirmation rules"),
            ("DIRECTION_BIAS", "AI consistently over/under-estimates", "Check systemic bias direction"),
        ]
        for hint, meaning, action in refs:
            lines.append(f"| {hint} | {meaning} | {action} |")
        lines.append("")
        return "\n".join(lines)

    def _section_dnf_drilldown(self) -> str:
        lines = [
            "## 6. D/F Day Drilldown",
            "",
        ]
        dnf_days = []
        for td in sorted(self.daily_turing):
            t = self.daily_turing[td]
            if t.get("grade") in ("D", "F"):
                dnf_days.append((td, t))

        if not dnf_days:
            lines.append("_No D or F grade days._")
            lines.append("")
            return "\n".join(lines)

        for td, t in dnf_days:
            s = t["scores"]
            a = self.daily_alignment.get(td, {})
            gaps = self.agg.get("gap_days", {})
            gap_info = gaps.get(td, {})

            lines.append(f"### {td} — Grade {t.get('grade')}, ATS {s['overall']:.3f}")
            lines.append("")
            if gap_info.get("gap_type", "NONE") != "NONE":
                lines.append(f"- **Gap Type**: {gap_info['gap_type']}")
                lines.append(f"- **Reason**: {gap_info.get('reason', '—')}")
                lines.append(f"- **Fair Score**: {gap_info.get('fair_score', 0):.3f}")
                lines.append(f"- **Excluded from D/F**: {'Yes' if gap_info.get('excluded_from_dnf') else 'No'}")
            lines.append("")

            # Breakdown
            lines.append("| Category | Score | Status |")
            lines.append("|----------|------:|--------|")
            for cat in ("phase", "risk", "facts", "relay", "strategy", "theme_leader"):
                cat_score = s.get(cat, 0)
                status = "✓" if cat_score >= 0.7 else "⚠" if cat_score >= 0.5 else "✗"
                lines.append(f"| {cat} | {cat_score:.3f} | {status} |")
            lines.append("")

            # Key diffs
            diffs = a.get("fact_diffs", []) + a.get("relay_diffs", [])
            failed = [d for d in diffs if not d.get("passed") and not d.get("excluded")]
            if failed:
                lines.append("**Failed Fields:**")
                for d in failed[:5]:
                    lines.append(
                        f"- `{d['field_path']}`: analyst={d.get('analyst_value')} "
                        f"ai={d.get('ai_value')}"
                    )
            lines.append("")

        return "\n".join(lines)

    def _section_phase_timeline(self) -> str:
        lines = [
            "## 7. Phase Transition Timeline",
            "",
            "| Date | Analyst Phase | AI Phase | Match | Risk(A) | Risk(AI) |",
            "|------|--------------|----------|-------|---------|----------|",
        ]
        for td in sorted(self.daily_turing):
            a = self.daily_alignment.get(td, {})
            a_phase = "?"
            ai_phase = "?"
            match = "?"
            a_risk = "?"
            ai_risk = "?"
            for d in a.get("emotion_diffs", []):
                fp = d.get("field_path", "")
                if "market_phase" in fp:
                    a_phase = d.get("analyst_label", "?")
                    ai_phase = d.get("ai_label", "?")
                    match = d.get("match_type", "?")
                if "risk_level" in fp:
                    a_risk = d.get("analyst_label", "?")
                    ai_risk = d.get("ai_label", "?")
            lines.append(
                f"| {td} | {a_phase} | {ai_phase} | {match} | {a_risk} | {ai_risk} |"
            )
        lines.append("")
        return "\n".join(lines)


def generate_dashboard(output_dir: str | Path) -> str:
    """Generate calibration_dashboard.md from replay output directory."""
    dashboard = CalibrationDashboard(output_dir)
    md = dashboard.generate()
    out_path = Path(output_dir) / "calibration_dashboard.md"
    out_path.write_text(md)
    return str(out_path)


def generate_action_plan(output_dir: str | Path) -> str:
    """Generate calibration_action_plan.md from replay output.

    Converts calibration hints + gap classifications into prioritized,
    executable tasks with verification steps.
    """
    dashboard = CalibrationDashboard(output_dir)
    hints = dashboard.agg.get("common_calibration_hints", {})
    gaps = dashboard.agg.get("gap_days", {})
    scores = dashboard.agg.get("scores", {})

    lines = [
        "# M8 Calibration Action Plan",
        "",
        f"**Period**: {dashboard.agg.get('start_date', '?')} ~ {dashboard.agg.get('end_date', '?')}",
        f"**Raw ATS**: {scores.get('average', 0):.3f}  |  **Fair ATS**: {scores.get('fair_average', scores.get('average',0)):.3f}",
        f"**Gaps classified**: {sum(1 for g in gaps.values() if g.get('gap_type','NONE')!='NONE')}",
        "",
        "---",
        "",
        "## Priority 1 — Critical (score impact > 0.05)",
        "",
    ]

    # Sort hints by frequency, assign priority
    sorted_hints = sorted(hints.items(), key=lambda x: -x[1])
    p1_hints = [(h, c) for h, c in sorted_hints if c >= 5]
    p2_hints = [(h, c) for h, c in sorted_hints if 2 <= c < 5]
    p3_hints = [(h, c) for h, c in sorted_hints if c < 2]

    action_map = {
        "STRATEGY_MAPPING_REVIEW": {
            "task": "Upgrade StrategyIntentMatcher",
            "detail": "Expand intent alias map. Add emotion.strategy_bias enrichment for metrics-only mode.",
            "expected_impact": "strategy_score from 0.65→0.75 (currently 0.654 avg)",
            "verify": "Re-run 7-day batch; verify strategy_score avg >= 0.70",
        },
        "THEME_LIFECYCLE_REVIEW": {
            "task": "Upgrade ThemeAliasResolver + lifecycle matching",
            "detail": "Add state matching (启动/调整/退潮) not just name matching. Expand alias coverage for AI direction names.",
            "expected_impact": "theme_leader from 0.34→0.45",
            "verify": "Re-run 7-day batch; verify theme_leader avg >= 0.40",
        },
        "FACT_SOURCE_REVIEW": {
            "task": "Fix M2.5 data pipeline gaps",
            "detail": "Ensure loss_effect_ratio in all chart JSONs. Fix chain_board_count counting methodology. Investigate max_board_height data source gap (EM board pool).",
            "expected_impact": "facts_score from 0.68→0.78",
            "verify": "Re-run batch; verify facts_score avg >= 0.75; loss_effect_ratio not missing",
        },
        "PHASE_RULE_REVIEW": {
            "task": "Extend PhaseOntology coverage",
            "detail": "Add missing label mappings for early-period chart labels. Improve CHAOS handling.",
            "expected_impact": "phase_score from 0.72→0.80",
            "verify": "Verify 7/2 CHAOS→FIRST_DIVERGENCE score >= 0.65",
        },
        "RELAY_ECOLOGY_REVIEW": {
            "task": "Calibrate relay feedback formula",
            "detail": "Compare AI relay scores vs analyst relay table data. Investigate promotion rate deviations.",
            "expected_impact": "relay_score from 0.89→0.92",
            "verify": "Check per-day relay diffs; max deviation < 0.05 for promotion rates",
        },
        "RISK_GATE_REVIEW": {
            "task": "Review risk confirmation thresholds",
            "detail": "Check risk gate rules for rebound/repair transitions. Reduce false LOW assignments.",
            "expected_impact": "risk_score maintain >= 0.75",
            "verify": "Verify no false LOW risk during REBOUND day 1-2",
        },
    }

    for hint, count in p1_hints:
        action = action_map.get(hint, {})
        lines.append(f"### {hint} (×{count})")
        lines.append("")
        lines.append(f"**Task**: {action.get('task', 'Investigate')}")
        lines.append(f"**Detail**: {action.get('detail', '—')}")
        lines.append(f"**Expected Impact**: {action.get('expected_impact', '—')}")
        lines.append(f"**Verify**: `{action.get('verify', '—')}`")
        lines.append("")

    if p2_hints:
        lines.append("## Priority 2 — Important (score impact 0.02–0.05)")
        lines.append("")
        for hint, count in p2_hints:
            action = action_map.get(hint, {})
            lines.append(f"- **{hint}** (×{count}): {action.get('task', 'Investigate')}")
        lines.append("")

    if p3_hints:
        lines.append("## Priority 3 — Monitor")
        lines.append("")
        for hint, count in p3_hints:
            lines.append(f"- **{hint}** (×{count})")
        lines.append("")

    # Gap classification summary
    gap_types = {}
    for g in gaps.values():
        gt = g.get("gap_type", "NONE")
        if gt != "NONE":
            gap_types[gt] = gap_types.get(gt, 0) + 1

    if gap_types:
        lines.append("## Gap Resolution Plan")
        lines.append("")
        lines.append("| Gap Type | Count | Resolution |")
        lines.append("|----------|------:|------------|")
        gap_resolutions = {
            "FORWARD_VS_HINDSIGHT": "Acknowledge. Do NOT penalize AI. Flag for fair scoring.",
            "WEEKEND_TRANSITION": "Add weekend/gap-day context. Check if AI phase drift is expected.",
            "DATA_SOURCE_GAP": "Fix M2.5 pipeline to include missing field (e.g. loss_effect_ratio).",
            "COUNTING_POLICY_GAP": "Align counting methodology. Define effective_chain_board_count spec.",
            "SEMANTIC_MAPPING_GAP": "Extend PhaseOntology zh_map. Add missing label aliases.",
        }
        for gt, count in sorted(gap_types.items()):
            lines.append(f"| {gt} | {count} | {gap_resolutions.get(gt, 'Investigate')} |")
        lines.append("")

    lines.append("## Execution Order")
    lines.append("")
    lines.append("1. Fix DATA_SOURCE_GAP items first (pipeline fix, no model change)")
    lines.append("2. Apply COUNTING_POLICY_GAP alignment (definition change)")
    lines.append("3. Extend SEMANTIC_MAPPING_GAP coverage (PhaseOntology labels)")
    lines.append("4. Upgrade STRATEGY_MAPPING (intent alias map)")
    lines.append("5. Upgrade THEME_LIFECYCLE (alias + state matching)")
    lines.append("6. Re-run 7-day batch → verify Fair ATS ≥ 0.80")
    lines.append("")

    out_path = Path(output_dir) / "calibration_action_plan.md"
    out_path.write_text("\n".join(lines))
    return str(out_path)

