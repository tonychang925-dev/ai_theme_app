"""Phase 4.2 T03 — Comparator Contracts.

MetricDiff: numeric comparisons with tolerances and missing/conflict handling.
SemanticDiff: label comparisons (phase, risk, strategy) with compatibility matrices.
AnalystAlignmentReport: aggregate comparison output for a single trading day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ═══ Diff Types ═══

class DiffType:
    EXACT_MATCH = "EXACT_MATCH"
    NUMERIC_DIFF = "NUMERIC_DIFF"
    LABEL_DIFF = "LABEL_DIFF"
    MISSING_ANALYST = "MISSING_ANALYST"
    MISSING_AI = "MISSING_AI"
    BOTH_MISSING = "BOTH_MISSING"
    REFERENCE_CONFLICT = "REFERENCE_CONFLICT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class MatchType:
    EXACT = "EXACT"
    COMPATIBLE = "COMPATIBLE"
    NEAR_MISS = "NEAR_MISS"
    OPPOSITE = "OPPOSITE"
    MISSING = "MISSING"


# ═══ Error Types ═══

class ErrorType:
    DATA_ERROR = "DATA_ERROR"             # AI fact layer wrong
    SEMANTIC_ERROR = "SEMANTIC_ERROR"     # AI fact correct but phase wrong
    TIMING_ERROR = "TIMING_ERROR"         # Too early/late on repair/decline
    STRATEGY_ERROR = "STRATEGY_ERROR"     # Judgment close but action wrong
    REFERENCE_WEAK = "REFERENCE_WEAK"     # Analyst reference low-confidence/missing


# ═══ MetricDiff ═══

@dataclass(frozen=True)
class MetricDiff:
    """A single numeric/metric comparison between analyst and AI."""

    field_path: str                       # "market_facts.limit_up_count"
    analyst_value: object | None          # from AnalystReferenceRecord
    ai_value: object | None               # from AIDiagnosisReferenceView

    diff_type: str = ""                   # DiffType
    absolute_diff: float | None = None
    relative_diff: float | None = None

    passed: bool = False
    score: float = 0.0                    # 0.0–1.0

    tolerance: float = 0.0                # allowed absolute deviation
    tolerance_pct: float = 0.0            # allowed relative deviation

    analyst_confidence: float = 1.0
    ai_confidence: float = 1.0
    weight: float = 1.0
    excluded_from_score: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "analyst_value": self.analyst_value,
            "ai_value": self.ai_value,
            "diff_type": self.diff_type,
            "absolute_diff": self.absolute_diff,
            "relative_diff": self.relative_diff,
            "passed": self.passed,
            "score": self.score,
            "excluded": self.excluded_from_score,
            "reason": self.reason,
        }


# ═══ SemanticDiff ═══

@dataclass(frozen=True)
class SemanticDiff:
    """A label/semantic comparison (phase, risk, strategy, theme, leader)."""

    field_path: str
    analyst_label: str
    ai_label: str

    match_type: str = ""                  # MatchType
    score: float = 0.0                    # 0.0–1.0
    reason: str = ""

    diff_type: str = ""                   # DiffType for missing/conflict
    excluded_from_score: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "analyst_label": self.analyst_label,
            "ai_label": self.ai_label,
            "match_type": self.match_type,
            "score": self.score,
            "reason": self.reason,
            "excluded": self.excluded_from_score,
        }


# ═══ AnalystAlignmentReport ═══

@dataclass(frozen=True)
class AnalystAlignmentReport:
    """Full comparison output for one trading day."""

    trade_date: date

    fact_diffs: tuple[MetricDiff, ...] = ()
    relay_diffs: tuple[MetricDiff, ...] = ()
    emotion_diffs: tuple[SemanticDiff | MetricDiff, ...] = ()
    strategy_diffs: tuple[SemanticDiff, ...] = ()
    theme_diffs: tuple[SemanticDiff, ...] = ()
    leader_diffs: tuple[SemanticDiff, ...] = ()

    # Per-category scores
    facts_score: float = 0.0
    relay_score: float = 0.0
    emotion_score: float = 0.0
    strategy_score: float = 0.0
    theme_score: float = 0.0
    leader_score: float = 0.0

    overall_score: float = 0.0

    # Quality / diagnostics
    error_types: tuple[str, ...] = ()
    excluded_fields: tuple[str, ...] = ()
    major_drifts: tuple[str, ...] = ()

    analyst_quality: float = 1.0          # reference coverage
    ai_quality: float = 1.0               # AI adapter source_quality

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "scores": {
                "facts": round(self.facts_score, 3),
                "relay": round(self.relay_score, 3),
                "emotion": round(self.emotion_score, 3),
                "strategy": round(self.strategy_score, 3),
                "theme": round(self.theme_score, 3),
                "leader": round(self.leader_score, 3),
                "overall": round(self.overall_score, 3),
            },
            "fact_diffs": [d.to_dict() for d in self.fact_diffs],
            "relay_diffs": [d.to_dict() for d in self.relay_diffs],
            "emotion_diffs": [d.to_dict() for d in self.emotion_diffs],
            "strategy_diffs": [d.to_dict() for d in self.strategy_diffs],
            "theme_diffs": [d.to_dict() for d in self.theme_diffs],
            "leader_diffs": [d.to_dict() for d in self.leader_diffs],
            "error_types": list(self.error_types),
            "excluded_fields": list(self.excluded_fields),
            "major_drifts": list(self.major_drifts),
            "analyst_quality": self.analyst_quality,
            "ai_quality": self.ai_quality,
        }
