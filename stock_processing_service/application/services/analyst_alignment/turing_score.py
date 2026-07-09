"""Phase 4.2 T04 — Analyst Turing Score.

Upgrades the T03 temp formula to the formal Analyst Turing Score (ATS v1).

Formula:
  25% Phase Agreement
+ 20% Risk Agreement
+ 20% Facts Accuracy
+ 15% Relay Accuracy
+ 10% Strategy Alignment
+ 10% Theme / Leader Alignment  (0.5 theme + 0.5 leader)

Includes: A-F grading, confidence adjustment, calibration hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.application.services.analyst_alignment.comparator import (
    AnalystComparator,
)
from stock_processing_service.application.services.analyst_alignment.contracts import (
    AnalystAlignmentReport,
    DiffType,
    MatchType,
    MetricDiff,
    SemanticDiff,
)
from stock_processing_service.application.services.analyst_reference.contracts import (
    AnalystReferenceRecord,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
)


FORMULA_VERSION = "ats_v1"


@dataclass(frozen=True)
class AnalystTuringScore:
    """Formal AI↔Analyst alignment score for one trading day.

    This is the calibrated output of Phase 4.2 — designed to be consumed
    by CalibrationEngine for automatic weight proposal.
    """

    trade_date: date

    # Per-component scores (0.0–1.0)
    phase_score: float
    risk_score: float
    facts_score: float
    relay_score: float
    strategy_score: float
    theme_leader_score: float

    overall_score: float

    # Grade
    grade: str             # A / B / C / D / F

    # Quality
    confidence: float      # adjusted by excluded ratio
    excluded_fields: tuple[str, ...]
    major_penalties: tuple[str, ...]

    # Calibration
    calibration_hints: tuple[str, ...]

    # Meta
    formula_version: str = FORMULA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "scores": {
                "phase": round(self.phase_score, 3),
                "risk": round(self.risk_score, 3),
                "facts": round(self.facts_score, 3),
                "relay": round(self.relay_score, 3),
                "strategy": round(self.strategy_score, 3),
                "theme_leader": round(self.theme_leader_score, 3),
                "overall": round(self.overall_score, 3),
            },
            "grade": self.grade,
            "confidence": round(self.confidence, 3),
            "excluded_fields": list(self.excluded_fields),
            "major_penalties": list(self.major_penalties),
            "calibration_hints": list(self.calibration_hints),
            "formula_version": self.formula_version,
        }


# ═══ AnalystTuringEvaluator ═══

class AnalystTuringEvaluator:
    """Compute Analyst Turing Score from an AnalystAlignmentReport.

    Usage:
        evaluator = AnalystTuringEvaluator()
        ats = evaluator.evaluate(report)
        print(f"Turing Score: {ats.overall_score:.2f} ({ats.grade})")
    """

    def __init__(self, comparator: AnalystComparator | None = None):
        self._comparator = comparator or AnalystComparator()

    def evaluate(
        self,
        analyst: AnalystReferenceRecord,
        ai: AIDiagnosisReferenceView,
    ) -> AnalystTuringScore:
        """Produce full Turing Score from analyst reference and AI view."""
        report = self._comparator.compare(analyst, ai)
        return self.evaluate_from_report(report)

    def evaluate_from_report(
        self, report: AnalystAlignmentReport
    ) -> AnalystTuringScore:
        """Compute Turing Score from an existing alignment report."""
        # Extract per-component scores
        phase_score = self._find_semantic_score(report.emotion_diffs, "market_phase")
        risk_score = self._find_semantic_score(report.emotion_diffs, "risk_level")

        facts_score = report.facts_score
        relay_score = report.relay_score
        strategy_score = report.strategy_score

        # Theme + Leader combined (0.5 each for short-term trading)
        theme_leader_score = 0.5 * report.theme_score + 0.5 * report.leader_score

        # ── ATS v1 formula ──
        overall_score = (
            0.25 * phase_score
            + 0.20 * risk_score
            + 0.20 * facts_score
            + 0.15 * relay_score
            + 0.10 * strategy_score
            + 0.10 * theme_leader_score
        )

        # ── Grade ──
        grade = self._compute_grade(overall_score)

        # ── Confidence ──
        total_fields = self._count_compared_fields(report)
        excluded_ratio = (
            len(report.excluded_fields) / max(total_fields, 1)
        )
        confidence = min(
            report.analyst_quality,
            report.ai_quality,
            1.0 - excluded_ratio * 0.3,
        )

        # ── Calibration hints ──
        hints = self._derive_calibration_hints(
            phase_score, risk_score, facts_score, relay_score,
            strategy_score, report.theme_score, report,
        )

        # ── Major penalties ──
        penalties = self._collect_major_penalties(report)

        return AnalystTuringScore(
            trade_date=report.trade_date,
            phase_score=phase_score,
            risk_score=risk_score,
            facts_score=facts_score,
            relay_score=relay_score,
            strategy_score=strategy_score,
            theme_leader_score=theme_leader_score,
            overall_score=round(overall_score, 4),
            grade=grade,
            confidence=round(confidence, 4),
            excluded_fields=report.excluded_fields,
            major_penalties=tuple(penalties),
            calibration_hints=tuple(hints),
            formula_version=FORMULA_VERSION,
        )

    # ── Helpers ──

    def _find_semantic_score(
        self, diffs: tuple[SemanticDiff | MetricDiff, ...], field_path_pattern: str
    ) -> float:
        """Find the score for a specific field in a diff tuple."""
        for d in diffs:
            if hasattr(d, "field_path") and field_path_pattern in d.field_path:
                return d.score
        return 0.0

    def _compute_grade(self, overall: float) -> str:
        if overall >= 0.85:
            return "A"
        if overall >= 0.75:
            return "B"
        if overall >= 0.60:
            return "C"
        if overall >= 0.45:
            return "D"
        return "F"

    def _count_compared_fields(self, report: AnalystAlignmentReport) -> int:
        return (
            len(report.fact_diffs)
            + len(report.relay_diffs)
            + len(report.emotion_diffs)
            + len(report.strategy_diffs)
            + len(report.theme_diffs)
            + len(report.leader_diffs)
        )

    def _derive_calibration_hints(
        self,
        phase_score: float,
        risk_score: float,
        facts_score: float,
        relay_score: float,
        strategy_score: float,
        theme_score: float,
        report: AnalystAlignmentReport,
    ) -> list[str]:
        hints: list[str] = []

        if phase_score < 0.5:
            hints.append("PHASE_RULE_REVIEW: phase detection rules may need recalibration")
        if risk_score < 0.5:
            hints.append("RISK_GATE_REVIEW: risk gate thresholds may need adjustment")
        if facts_score < 0.7:
            hints.append("FACT_SOURCE_REVIEW: fact-layer data sources may be stale or incorrect")
        if relay_score < 0.7:
            hints.append("RELAY_ECOLOGY_REVIEW: relay ecology metrics may need calibration")
        if strategy_score < 0.5:
            hints.append("STRATEGY_MAPPING_REVIEW: strategy mapping logic may need revision")
        if theme_score < 0.5:
            hints.append("THEME_LIFECYCLE_REVIEW: theme lifecycle detection may need improvement")

        # Check for systemic direction bias in facts
        over_estimates = 0
        under_estimates = 0
        for d in report.fact_diffs + report.relay_diffs:
            if isinstance(d, MetricDiff) and d.absolute_diff is not None and d.absolute_diff > 0:
                try:
                    if float(d.ai_value) > float(d.analyst_value):  # type: ignore[arg-type]
                        over_estimates += 1
                    else:
                        under_estimates += 1
                except (TypeError, ValueError):
                    pass
        if over_estimates > under_estimates * 3 and over_estimates >= 3:
            hints.append("DIRECTION_BIAS: AI consistently OVER-estimates vs analyst")
        if under_estimates > over_estimates * 3 and under_estimates >= 3:
            hints.append("DIRECTION_BIAS: AI consistently UNDER-estimates vs analyst")

        return hints

    def _collect_major_penalties(self, report: AnalystAlignmentReport) -> list[str]:
        penalties: list[str] = []
        for d in report.fact_diffs + report.relay_diffs:
            if isinstance(d, MetricDiff) and not d.excluded_from_score and not d.passed:
                if d.absolute_diff is not None and d.tolerance > 0 and d.absolute_diff > d.tolerance * 2:
                    penalties.append(f"{d.field_path}: {d.absolute_diff:.1f} off")
        for d in report.emotion_diffs:
            if isinstance(d, SemanticDiff) and d.match_type == MatchType.OPPOSITE:
                penalties.append(f"{d.field_path}: {d.analyst_label} vs {d.ai_label}")
        return penalties
