"""Phase 4.2 T05 — Replay Runner.

Orchestrates the full alignment replay pipeline:
  AnalystReferenceStore → AIAdapter → AnalystComparator → AnalystTuringEvaluator → Report
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.application.services.analyst_reference.contracts import (
    AnalystReferenceRecord,
)
from stock_processing_service.application.services.analyst_reference.store import (
    AnalystReferenceStore,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
    AIAdapter,
)
from stock_processing_service.application.services.analyst_alignment.comparator import (
    AnalystComparator,
)
from stock_processing_service.application.services.analyst_alignment.contracts import (
    AnalystAlignmentReport,
)
from stock_processing_service.application.services.analyst_alignment.turing_score import (
    AnalystTuringEvaluator,
    AnalystTuringScore,
)


# ═══ Daily Result ═══

@dataclass(frozen=True)
class DailyReplayResult:
    trade_date: date
    alignment_report: AnalystAlignmentReport
    turing_score: AnalystTuringScore
    reference_hash: str | None = None
    ai_snapshot_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "alignment": self.alignment_report.to_dict(),
            "turing": self.turing_score.to_dict(),
            "reference_hash": self.reference_hash,
            "ai_snapshot_id": self.ai_snapshot_id,
        }


# ═══ Aggregate Report ═══

@dataclass(frozen=True)
class ReplayAggregateReport:
    start_date: date
    end_date: date
    trading_days: int
    skipped_days: list[str] = field(default_factory=list)
    skipped_reasons: dict[str, str] = field(default_factory=dict)

    average_score: float = 0.0
    median_score: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0
    grade_distribution: dict[str, int] = field(default_factory=dict)

    average_phase_score: float = 0.0
    average_risk_score: float = 0.0
    average_facts_score: float = 0.0
    average_relay_score: float = 0.0
    average_strategy_score: float = 0.0
    average_theme_leader_score: float = 0.0

    common_calibration_hints: dict[str, int] = field(default_factory=dict)
    major_drifts: list[str] = field(default_factory=list)
    weak_days: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "trading_days": self.trading_days,
            "skipped_days": self.skipped_days,
            "scores": {
                "average": round(self.average_score, 4),
                "median": round(self.median_score, 4),
                "min": round(self.min_score, 4),
                "max": round(self.max_score, 4),
            },
            "grade_distribution": self.grade_distribution,
            "component_averages": {
                "phase": round(self.average_phase_score, 4),
                "risk": round(self.average_risk_score, 4),
                "facts": round(self.average_facts_score, 4),
                "relay": round(self.average_relay_score, 4),
                "strategy": round(self.average_strategy_score, 4),
                "theme_leader": round(self.average_theme_leader_score, 4),
            },
            "common_calibration_hints": self.common_calibration_hints,
            "major_drifts": self.major_drifts,
            "weak_days": self.weak_days,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Analyst Alignment Replay Summary",
            "",
            "## Overall",
            f"- Trading days compared: {self.trading_days}",
            f"- Skipped: {len(self.skipped_days)} ({', '.join(self.skipped_days) if self.skipped_days else 'none'})",
            f"- Average ATS: {self.average_score:.3f}",
            f"- Median ATS: {self.median_score:.3f}",
            f"- Range: {self.min_score:.3f} — {self.max_score:.3f}",
            f"- Grade Distribution: {_format_grade_dist(self.grade_distribution)}",
            "",
            "## Component Averages",
            f"- Phase: {self.average_phase_score:.3f}",
            f"- Risk: {self.average_risk_score:.3f}",
            f"- Facts: {self.average_facts_score:.3f}",
            f"- Relay: {self.average_relay_score:.3f}",
            f"- Strategy: {self.average_strategy_score:.3f}",
            f"- Theme/Leader: {self.average_theme_leader_score:.3f}",
            "",
            "## Weak Days (grade D or F)",
        ]
        if self.weak_days:
            for wd in self.weak_days:
                lines.append(f"- {wd}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Top Calibration Hints")
        if self.common_calibration_hints:
            for hint, count in sorted(
                self.common_calibration_hints.items(), key=lambda x: -x[1]
            ):
                lines.append(f"- {hint}: {count}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Major Drifts")
        if self.major_drifts:
            for md in self.major_drifts[:20]:
                lines.append(f"- {md}")
        else:
            lines.append("- None")
        return "\n".join(lines)


def _format_grade_dist(d: dict[str, int]) -> str:
    return ", ".join(f"{g}={c}" for g, c in sorted(d.items()))


# ═══ Replay Runner ═══

class ReplayRunner:
    """Orchestrate analyst alignment replay across a date range."""

    def __init__(
        self,
        store: AnalystReferenceStore | None = None,
        adapter: AIAdapter | None = None,
        comparator: AnalystComparator | None = None,
        evaluator: AnalystTuringEvaluator | None = None,
    ):
        self.store = store or AnalystReferenceStore()
        self.adapter = adapter or AIAdapter()
        self.comparator = comparator or AnalystComparator()
        self.evaluator = evaluator or AnalystTuringEvaluator(self.comparator)

    def run(
        self,
        start_date: date,
        end_date: date,
        ai_views: dict[date, AIDiagnosisReferenceView] | None = None,
    ) -> tuple[list[DailyReplayResult], ReplayAggregateReport]:
        """Run replay across a date range.

        Args:
            start_date / end_date: inclusive date range.
            ai_views: pre-computed AI views keyed by date. If None, empty dict.

        Returns:
            (daily_results, aggregate_report)
        """
        ai_views = ai_views or {}
        daily_results: list[DailyReplayResult] = []
        skipped_days: list[str] = []
        skipped_reasons: dict[str, str] = {}

        all_scores: list[float] = []
        all_phases: list[float] = []
        all_risks: list[float] = []
        all_facts: list[float] = []
        all_relays: list[float] = []
        all_strategies: list[float] = []
        all_theme_leaders: list[float] = []
        grade_counts: dict[str, int] = {}
        hint_counter: Counter[str] = Counter()
        all_drifts: list[str] = []
        weak_days: list[str] = []

        # Iterate dates
        current = start_date
        while current <= end_date:
            analyst = self.store.get_by_date(current)
            if analyst is None:
                skipped_days.append(current.isoformat())
                skipped_reasons[current.isoformat()] = "No analyst reference found"
                current = _next_day(current)
                continue

            ai_view = ai_views.get(current)
            if ai_view is None:
                skipped_days.append(current.isoformat())
                skipped_reasons[current.isoformat()] = "No AI view available"
                current = _next_day(current)
                continue

            # Run pipeline
            ats = self.evaluator.evaluate(analyst, ai_view)
            report = self.comparator.compare(analyst, ai_view)

            daily_results.append(DailyReplayResult(
                trade_date=current,
                alignment_report=report,
                turing_score=ats,
                reference_hash=None,
                ai_snapshot_id=None,
            ))

            # Collect stats
            all_scores.append(ats.overall_score)
            all_phases.append(ats.phase_score)
            all_risks.append(ats.risk_score)
            all_facts.append(ats.facts_score)
            all_relays.append(ats.relay_score)
            all_strategies.append(ats.strategy_score)
            all_theme_leaders.append(ats.theme_leader_score)

            grade_counts[ats.grade] = grade_counts.get(ats.grade, 0) + 1

            for hint in ats.calibration_hints:
                hint_counter[hint.split(":")[0]] += 1

            all_drifts.extend(ats.major_penalties)

            if ats.grade in ("D", "F"):
                weak_days.append(f"{current.isoformat()}: score={ats.overall_score:.3f}, grade={ats.grade}")

            current = _next_day(current)

        # Aggregate
        n = len(all_scores) or 1
        sorted_scores = sorted(all_scores) if all_scores else [0.0]

        aggregate = ReplayAggregateReport(
            start_date=start_date,
            end_date=end_date,
            trading_days=len(daily_results),
            skipped_days=skipped_days,
            skipped_reasons=skipped_reasons,
            average_score=sum(all_scores) / n,
            median_score=sorted_scores[len(sorted_scores) // 2],
            min_score=min(all_scores) if all_scores else 0.0,
            max_score=max(all_scores) if all_scores else 0.0,
            grade_distribution=grade_counts,
            average_phase_score=sum(all_phases) / n,
            average_risk_score=sum(all_risks) / n,
            average_facts_score=sum(all_facts) / n,
            average_relay_score=sum(all_relays) / n,
            average_strategy_score=sum(all_strategies) / n,
            average_theme_leader_score=sum(all_theme_leaders) / n,
            common_calibration_hints=dict(hint_counter),
            major_drifts=all_drifts,
            weak_days=weak_days,
        )

        return daily_results, aggregate


def _next_day(d: date) -> date:
    from datetime import timedelta
    return d + timedelta(days=1)
