"""Phase 4.3.1 — Evaluation Gap Classifier.

Distinguishes AI failures that are genuine cognitive errors from
those caused by forward-vs-hindsight timing, data source gaps,
or counting policy differences.

This prevents the scoring system from penalizing AI for
things it could not have known at the time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


# ═══ Gap Types ═══

class EvaluationGapType:
    NONE = "NONE"
    FORWARD_VS_HINDSIGHT = "FORWARD_VS_HINDSIGHT"    # AI used same-day data, analyst wrote after the fact
    DATA_SOURCE_GAP = "DATA_SOURCE_GAP"               # missing source data (e.g. EM board pool gap)
    COUNTING_POLICY_GAP = "COUNTING_POLICY_GAP"       # different counting methodology
    SEMANTIC_MAPPING_GAP = "SEMANTIC_MAPPING_GAP"     # label vocabulary mismatch (being resolved)
    WEEKEND_TRANSITION = "WEEKEND_TRANSITION"         # gap in trading days caused phase drift
    UNKNOWN = "UNKNOWN"


# ═══ Gap Classification Result ═══

@dataclass
class GapClassification:
    """Classifies why a given trading day may have low ATS."""
    trade_date: str

    gap_type: str = EvaluationGapType.NONE
    reason: str = ""
    fair_score_penalty_reduction: float = 0.0    # how much to reduce the penalty in fair scoring
    should_exclude_from_dnf: bool = False         # exclude from D/F failure count

    extra: dict[str, Any] = field(default_factory=dict)


# ═══ Gap Classifier ═══

class EvaluationGapClassifier:
    """Determine if a low ATS day is a genuine AI failure or a methodological gap."""

    def classify(
        self,
        trade_date: date,
        raw_score: float,
        analyst_phase: str,
        ai_phase: str,
        analyst_facts: dict[str, Any] | None = None,
        ai_view: Any = None,
        prev_trade_date: date | None = None,
    ) -> GapClassification:
        """Classify evaluation gap for a single trading day."""
        ts = trade_date.isoformat()
        days_gap = self._trading_day_gap(trade_date, prev_trade_date)

        # ── Forward vs Hindsight ──
        # Criteria: phase mismatch where analyst labeled a turning point
        # that was only visible in hindsight (after the fact).
        # Key signal: AI sees continuation (ACCELERATION/强势) but
        # analyst labels a turn (FADE/DISTRIBUTION).
        if self._is_forward_vs_hindsight(analyst_phase, ai_phase, trade_date):
            return GapClassification(
                trade_date=ts,
                gap_type=EvaluationGapType.FORWARD_VS_HINDSIGHT,
                reason=f"AI saw {ai_phase} from same-day data; analyst labeled {analyst_phase} with hindsight",
                fair_score_penalty_reduction=0.6,
                should_exclude_from_dnf=True,
            )

        # ── Weekend Transition ──
        if days_gap >= 3 and raw_score < 0.65:
            return GapClassification(
                trade_date=ts,
                gap_type=EvaluationGapType.WEEKEND_TRANSITION,
                reason=f"{days_gap}-day trading gap before {ts}; phase transition likely accelerated",
                fair_score_penalty_reduction=0.3,
                should_exclude_from_dnf=False,
            )

        return GapClassification(trade_date=ts)

    def classify_batch(
        self,
        daily_scores: list[dict[str, Any]],
    ) -> dict[str, GapClassification]:
        """Classify all days in a batch."""
        results: dict[str, GapClassification] = {}
        prev_date: date | None = None
        sorted_scores = sorted(daily_scores, key=lambda d: d.get("trade_date", ""))

        for entry in sorted_scores:
            td = date.fromisoformat(entry["trade_date"])
            gc = self.classify(
                trade_date=td,
                raw_score=entry.get("raw_score", 0),
                analyst_phase=entry.get("analyst_phase", ""),
                ai_phase=entry.get("ai_phase", ""),
                prev_trade_date=prev_date,
            )
            results[td.isoformat()] = gc
            prev_date = td

        return results

    # ── Helpers ──

    def _is_forward_vs_hindsight(
        self, analyst_phase: str, ai_phase: str, trade_date: date
    ) -> bool:
        """Detect forward-vs-hindsight gap.

        Pattern: AI sees positive momentum (ACCELERATION/强势/情绪正常),
        but analyst labels a turn (FADE/DISTRIBUTION/FIRST_DIVERGENCE).
        This happens when the analyst, writing days later, knows this
        was the start of a decline that wasn't visible intraday.
        """
        continuation_phases = {"ACCELERATION", "CLIMAX", "REBOUND"}
        turn_phases = {"FADE", "DISTRIBUTION", "FIRST_DIVERGENCE"}

        if ai_phase in continuation_phases and analyst_phase in turn_phases:
            return True
        return False

    def _trading_day_gap(
        self, td: date, prev: date | None
    ) -> int:
        """Days since the last trading day (excludes weekends)."""
        if prev is None:
            return 1
        return (td - prev).days


# ═══ Fair Score Computation ═══

def compute_fair_scores(
    daily_results: list[Any],
) -> tuple[float, float, dict[str, Any]]:
    """Compute both raw and fair average ATS.

    Returns (raw_avg, fair_avg, gap_details).
    """
    from .evaluation_gap import EvaluationGapClassifier

    classifier = EvaluationGapClassifier()
    raw_scores: list[float] = []
    fair_scores: list[float] = []
    gaps: dict[str, dict] = {}
    prev_date: date | None = None

    for dr in daily_results:
        td = dr.trade_date
        ts = td.isoformat()

        # Get AI view from the alignment report
        ai_phase = ""
        analyst_phase = ""
        raw = getattr(dr, 'turing_score', None)
        if raw is None:
            continue
        raw_score = float(raw.overall_score)

        # Extract phases from alignment report
        report = getattr(dr, 'alignment_report', None)
        if report is not None:
            for d in getattr(report, 'emotion_diffs', ()):
                if hasattr(d, 'field_path') and 'market_phase' in d.field_path:
                    analyst_phase = getattr(d, 'analyst_label', '')
                    ai_phase = getattr(d, 'ai_label', '')

        gc = classifier.classify(
            trade_date=td,
            raw_score=raw_score,
            analyst_phase=analyst_phase,
            ai_phase=ai_phase,
            prev_trade_date=prev_date,
        )

        # Fair score: reduce penalty for classified gaps
        # Penalty = 1.0 - raw_score, reduction = gap reduction factor
        penalty = max(0, 1.0 - raw_score)
        fair_score = raw_score + penalty * gc.fair_score_penalty_reduction

        raw_scores.append(raw_score)
        fair_scores.append(fair_score)
        gaps[ts] = {
            "gap_type": gc.gap_type,
            "reason": gc.reason,
            "raw_score": round(raw_score, 3),
            "fair_score": round(fair_score, 3),
            "excluded_from_dnf": gc.should_exclude_from_dnf,
        }
        prev_date = td

    raw_avg = sum(raw_scores) / max(len(raw_scores), 1)
    fair_avg = sum(fair_scores) / max(len(fair_scores), 1)

    return raw_avg, fair_avg, gaps
