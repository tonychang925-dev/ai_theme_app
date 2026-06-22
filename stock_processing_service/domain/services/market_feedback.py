"""M7b + M7c: Prediction vs Reality + Weight Auto-Calibration.

M7b: Error Engine — compares M6 predictions to market reality.
M7c: Calibration Engine — auto-adjusts source weights from errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# M6 source weights (current baseline)
DEFAULT_SOURCE_WEIGHTS = {
    "ths": 1.00,
    "cninfo": 0.80,
    "eps": 0.70,
    "research": 0.55,
    "eastmoney": 0.45,
    "jyhf": 0.35,
}

# Calibration constraints
MAX_DELTA_PER_CYCLE = 0.03
MIN_WEIGHT = 0.10
MAX_WEIGHT = 1.00
ERROR_THRESHOLD = 0.15  # ±0.15 → over/under
BIAS_THRESHOLD = 0.10   # source bias threshold for adjustment


# ── M7b: Error Types ────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionError:
    theme_name: str
    predicted_strength: float
    actual_strength: float
    strength_error: float
    abs_strength_error: float
    predicted_rank: int
    actual_rank: int
    rank_error: int
    error_bucket: str       # "overestimate" | "underestimate" | "correct"
    stability_score: float = 0.0
    anchor_score: float = 0.0


@dataclass(frozen=True)
class ErrorReport:
    trade_date: str
    errors: list[PredictionError] = field(default_factory=list)
    overestimated: list[str] = field(default_factory=list)
    underestimated: list[str] = field(default_factory=list)
    correct: list[str] = field(default_factory=list)
    source_bias: dict[str, float] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationResult:
    trade_date: str
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    deltas: dict[str, float]
    reasons: dict[str, str] = field(default_factory=dict)


# ── M7b: Error Engine ───────────────────────────────────────────


class PredictionVsRealityEngine:
    """Compare M6 predictions to market truth, classify errors."""

    def compute(
        self,
        trade_date: date,
        predicted: dict[str, dict[str, Any]],   # {theme: {strength, rank, stability, anchor}}
        actual: dict[str, dict[str, Any]],      # {theme: {strength, rank}}
    ) -> ErrorReport:
        td_str = trade_date.isoformat()
        errors: list[PredictionError] = []
        over: list[str] = []
        under: list[str] = []
        correct: list[str] = []
        source_bias_accum: dict[str, list[float]] = {}

        for theme, pred in predicted.items():
            act = actual.get(theme, {})
            pred_s = float(pred.get("strength", 0))
            act_s = float(act.get("strength", pred_s))  # default to prediction if no actual
            pred_r = int(pred.get("rank", 0))
            act_r = int(act.get("rank", pred_r))

            str_err = round(pred_s - act_s, 4)
            abs_err = round(abs(str_err), 4)
            rank_err = pred_r - act_r

            if str_err > ERROR_THRESHOLD:
                bucket = "overestimate"
                over.append(theme)
            elif str_err < -ERROR_THRESHOLD:
                bucket = "underestimate"
                under.append(theme)
            else:
                bucket = "correct"
                correct.append(theme)

            errors.append(PredictionError(
                theme_name=theme,
                predicted_strength=pred_s,
                actual_strength=act_s,
                strength_error=str_err,
                abs_strength_error=abs_err,
                predicted_rank=pred_r,
                actual_rank=act_r,
                rank_error=rank_err,
                error_bucket=bucket,
                stability_score=float(pred.get("stability", 0)),
                anchor_score=float(pred.get("anchor", 0)),
            ))

            # Source bias tracking
            sources = pred.get("sources", [])
            for src in sources:
                source_bias_accum.setdefault(src, []).append(str_err)

        # Aggregate source bias
        source_bias: dict[str, float] = {}
        for src, errs in source_bias_accum.items():
            source_bias[src] = round(sum(errs) / len(errs), 4)

        # Summary
        n = len(errors)
        summary = {
            "total_themes": n,
            "overestimated_count": len(over),
            "underestimated_count": len(under),
            "correct_count": len(correct),
            "mean_abs_error": round(sum(e.abs_strength_error for e in errors) / max(n, 1), 4),
            "top_overestimated": over[:3],
            "top_underestimated": under[:3],
        }

        return ErrorReport(
            trade_date=td_str,
            errors=errors,
            overestimated=over,
            underestimated=under,
            correct=correct,
            source_bias=source_bias,
            summary=summary,
        )


# ── M7c: Calibration Engine ─────────────────────────────────────


class WeightCalibrationEngine:
    """Auto-adjust source weights based on M7b error report."""

    def __init__(self, initial_weights: dict[str, float] | None = None):
        self._weights = dict(initial_weights or DEFAULT_SOURCE_WEIGHTS)

    def calibrate(
        self, trade_date: date, error_report: ErrorReport,
    ) -> CalibrationResult:
        old = dict(self._weights)
        new = dict(self._weights)
        deltas: dict[str, float] = {}
        reasons: dict[str, str] = {}

        # ① Source weight calibration from source_bias
        for src, bias in error_report.source_bias.items():
            if src not in new:
                continue
            if abs(bias) < BIAS_THRESHOLD:
                continue

            delta = -0.02 if bias > 0 else 0.02
            delta = max(-MAX_DELTA_PER_CYCLE, min(MAX_DELTA_PER_CYCLE, delta))

            candidate = new[src] + delta
            candidate = max(MIN_WEIGHT, min(MAX_WEIGHT, candidate))

            if candidate != new[src]:
                deltas[src] = round(candidate - new[src], 4)
                reasons[src] = (
                    f"source_bias={bias:.3f} → "
                    f"{'overweight' if bias > 0 else 'underweight'}"
                )
                new[src] = round(candidate, 4)

        # ② Theme-level feedback
        over_themes = set(error_report.overestimated)
        under_themes = set(error_report.underestimated)
        if over_themes:
            for src in ["eps", "research"]:
                if src in new and src not in deltas:
                    new[src] = round(max(MIN_WEIGHT, new[src] - 0.01), 4)
                    deltas[src] = round(new[src] - old[src], 4)
                    reasons[src] = f"{len(over_themes)} themes overestimated"

        if under_themes:
            for src in ["eastmoney", "jyhf"]:
                if src in new and src not in deltas:
                    new[src] = round(min(MAX_WEIGHT, new[src] + 0.01), 4)
                    deltas[src] = round(new[src] - old[src], 4)
                    reasons[src] = f"{len(under_themes)} themes underestimated"

        # ③ Apply constraints
        self._weights = self._enforce_constraints(new, old)

        # Recompute deltas after constraint enforcement
        final_deltas = {
            k: round(self._weights[k] - old[k], 4)
            for k in self._weights
            if round(self._weights[k] - old[k], 4) != 0
        }

        return CalibrationResult(
            trade_date=trade_date.isoformat(),
            old_weights=old,
            new_weights=self._weights,
            deltas=final_deltas,
            reasons=reasons,
        )

    @property
    def current_weights(self) -> dict[str, float]:
        return dict(self._weights)

    @staticmethod
    def _enforce_constraints(
        new: dict[str, float], old: dict[str, float],
    ) -> dict[str, float]:
        """Enforce calibration constraints to prevent divergence."""
        result = dict(new)

        # EPS + research combined delta cap
        eps_delta = result.get("eps", 0) - old.get("eps", 0)
        research_delta = result.get("research", 0) - old.get("research", 0)
        if eps_delta + research_delta < -0.03:
            excess = -(eps_delta + research_delta + 0.03)
            result["eps"] = old.get("eps", 0) + max(-0.02, eps_delta + excess * 0.5)
            result["research"] = old.get("research", 0) + max(-0.02, research_delta + excess * 0.5)

        # Anchor weight floor
        for key in ["anchor", "stability"]:
            if key in result and result[key] < 0.15:
                result[key] = 0.15

        # Clamp all to [MIN, MAX]
        for key in result:
            result[key] = round(max(MIN_WEIGHT, min(MAX_WEIGHT, result[key])), 4)

        return result
