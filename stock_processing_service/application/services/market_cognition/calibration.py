"""M8 Phase 1 T04 — Calibration Metrics Service.

Computes Binary Accuracy, Brier Score, Expected Calibration Error (ECE),
and Timing Offset from eligible Ground Truth Validation Records.

Constraints (ADR-M8-009):
- Only YES/NO records enter Brier and ECE computation.
- PARTIAL and UNVERIFIABLE are excluded from probability-based metrics.
- quality_score is NEVER used as prediction_probability.
- Narrative/Observation/Assessment records must not appear in input.
- All inputs must have passed Eligibility Gate.
"""

from __future__ import annotations

import dataclasses
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from stock_processing_service.contracts.market_thesis_validation import (
    MarketThesisValidationRecord,
    VerificationLabel,
)


# ── metric output contracts ──

@dataclass(frozen=True, slots=True)
class BinaryAccuracyResult:
    correct: int
    total: int
    accuracy: float
    yes_correct: int = 0
    yes_total: int = 0
    no_correct: int = 0
    no_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "total": self.total,
            "accuracy": round(self.accuracy, 4),
            "yes_correct": self.yes_correct,
            "yes_total": self.yes_total,
            "no_correct": self.no_correct,
            "no_total": self.no_total,
        }


@dataclass(frozen=True, slots=True)
class BrierScoreResult:
    score: float
    sample_count: int
    baseline_score: float | None = None  # climatological baseline
    skill_score: float | None = None     # 1 - score/baseline, positive = better than baseline

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "brier_score": round(self.score, 6),
            "sample_count": self.sample_count,
        }
        if self.baseline_score is not None:
            result["baseline_score"] = round(self.baseline_score, 6)
        if self.skill_score is not None:
            result["skill_score"] = round(self.skill_score, 4)
        return result


@dataclass(frozen=True, slots=True)
class ECEResult:
    ece: float                          # Expected Calibration Error
    bin_count: int
    bins: tuple[dict[str, Any], ...]    # {bin_range, count, avg_prob, accuracy}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ece": round(self.ece, 6),
            "bin_count": self.bin_count,
            "bins": [
                {
                    "range": b["range"],
                    "count": b["count"],
                    "avg_probability": round(b["avg_probability"], 4),
                    "accuracy": round(b["accuracy"], 4),
                    "gap": round(b["gap"], 4),
                }
                for b in self.bins
            ],
        }


@dataclass(frozen=True, slots=True)
class TimingOffsetResult:
    offsets: dict[int, int]             # {trading_days_offset: count}
    mean_offset: float | None
    median_offset: float | None
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "offsets": {str(k): v for k, v in sorted(self.offsets.items())},
            "mean_offset": round(self.mean_offset, 2) if self.mean_offset is not None else None,
            "median_offset": round(self.median_offset, 2) if self.median_offset is not None else None,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    generated_at: str
    schema_version: str = "calibration_report.v1"

    binary_accuracy: BinaryAccuracyResult | None = None
    brier_score: BrierScoreResult | None = None
    ece: ECEResult | None = None
    timing_offset: TimingOffsetResult | None = None

    # Diagnostics
    total_records: int = 0
    eligible_for_probability_metrics: int = 0   # YES + NO count
    excluded_partial: int = 0
    excluded_unverifiable: int = 0
    excluded_other: int = 0
    warnings: tuple[str, ...] = ()
    policy_versions_observed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "total_records": self.total_records,
            "eligible_for_probability_metrics": self.eligible_for_probability_metrics,
            "excluded_partial": self.excluded_partial,
            "excluded_unverifiable": self.excluded_unverifiable,
            "excluded_other": self.excluded_other,
        }
        if self.binary_accuracy is not None:
            result["binary_accuracy"] = self.binary_accuracy.to_dict()
        if self.brier_score is not None:
            result["brier_score"] = self.brier_score.to_dict()
        if self.ece is not None:
            result["ece"] = self.ece.to_dict()
        if self.timing_offset is not None:
            result["timing_offset"] = self.timing_offset.to_dict()
        if self.warnings:
            result["warnings"] = list(self.warnings)
        if self.policy_versions_observed:
            result["policy_versions_observed"] = list(self.policy_versions_observed)
        return result


# ── metric computation ──

class CalibrationMetricsService:
    """Compute calibration metrics from eligible Ground Truth records.

    All metrics follow the contract: YES/NO records only for probability
    metrics. PARTIAL/UNVERIFIABLE are counted but excluded from Brier/ECE.
    quality_score is tracked separately and never enters probability computation.
    """

    ECE_BINS = 5  # default: 5 equal-width probability bins

    def __init__(self, *, ece_bins: int = ECE_BINS) -> None:
        if ece_bins < 2:
            raise ValueError("ece_bins must be at least 2")
        self._ece_bins = ece_bins

    def compute(self, records: list[MarketThesisValidationRecord]) -> CalibrationReport:
        """Compute all metrics from a list of validation records.

        Records are NOT filtered by this service — the caller is responsible
        for providing only eligible Ground Truth records. Records with
        invalid labels are counted as excluded_other and trigger a warning.
        """
        if not records:
            return CalibrationReport(
                generated_at=datetime.now().isoformat(),
                total_records=0,
                warnings=("no_records",),
            )

        # Partition by label
        yes_no: list[MarketThesisValidationRecord] = []
        partial: list[MarketThesisValidationRecord] = []
        unverifiable: list[MarketThesisValidationRecord] = []
        other: list[MarketThesisValidationRecord] = []

        for record in records:
            if record.label is VerificationLabel.YES:
                yes_no.append(record)
            elif record.label is VerificationLabel.NO:
                yes_no.append(record)
            elif record.label is VerificationLabel.PARTIAL:
                partial.append(record)
            elif record.label is VerificationLabel.UNVERIFIABLE:
                unverifiable.append(record)
            else:
                other.append(record)

        warnings: list[str] = []
        if other:
            warnings.append(f"{len(other)} records with unexpected label excluded")
        if len(yes_no) == 0:
            warnings.append("no_eligible_yes_no_records")
            return CalibrationReport(
                generated_at=datetime.now().isoformat(),
                total_records=len(records),
                eligible_for_probability_metrics=0,
                excluded_partial=len(partial),
                excluded_unverifiable=len(unverifiable),
                excluded_other=len(other),
                warnings=tuple(warnings),
                policy_versions_observed=tuple(sorted({
                    r.source_policy_version for r in records
                })),
            )

        # Compute all metrics
        binary_accuracy = self._binary_accuracy(yes_no)
        brier_score = self._brier_score(yes_no)
        ece = self._ece(yes_no)
        timing_offset = self._timing_offset(records)

        # Quality check: narrative calibration sample
        for record in records:
            if _is_narrative_confidence_suspect(record):
                warnings.append(
                    f"WARNING: record {record.record_id} has prediction_probability "
                    f"close to source_quality_score — possible narrative contamination"
                )
                break

        if len(yes_no) < 10:
            warnings.append(
                f"low_sample: only {len(yes_no)} YES/NO records; "
                "metrics are indicative, not reliable"
            )

        return CalibrationReport(
            generated_at=datetime.now().isoformat(),
            total_records=len(records),
            eligible_for_probability_metrics=len(yes_no),
            excluded_partial=len(partial),
            excluded_unverifiable=len(unverifiable),
            excluded_other=len(other),
            binary_accuracy=binary_accuracy,
            brier_score=brier_score,
            ece=ece,
            timing_offset=timing_offset,
            warnings=tuple(warnings),
            policy_versions_observed=tuple(sorted({
                r.source_policy_version for r in records
            })),
        )

    # ── individual metrics ──

    @staticmethod
    def _binary_accuracy(
        records: list[MarketThesisValidationRecord],
    ) -> BinaryAccuracyResult:
        yes_correct = 0
        yes_total = 0
        no_correct = 0
        no_total = 0

        for record in records:
            if record.label is VerificationLabel.YES:
                yes_total += 1
                if _is_yes_correct(record):
                    yes_correct += 1
            elif record.label is VerificationLabel.NO:
                no_total += 1
                if _is_no_correct(record):
                    no_correct += 1

        correct = yes_correct + no_correct
        total = yes_total + no_total
        return BinaryAccuracyResult(
            correct=correct,
            total=total,
            accuracy=correct / total if total > 0 else 0.0,
            yes_correct=yes_correct,
            yes_total=yes_total,
            no_correct=no_correct,
            no_total=no_total,
        )

    @staticmethod
    def _brier_score(
        records: list[MarketThesisValidationRecord],
    ) -> BrierScoreResult:
        """Brier Score = mean((p_i - o_i)^2) where o_i = 1 for YES, 0 for NO.

        Lower is better. 0 = perfect, 0.25 = unskilled (always 0.5).
        """
        squared_errors: list[float] = []
        for record in records:
            outcome = 1.0 if record.label is VerificationLabel.YES else 0.0
            prob = record.prediction_probability
            squared_errors.append((prob - outcome) ** 2)

        if not squared_errors:
            return BrierScoreResult(score=0.0, sample_count=0)

        score = sum(squared_errors) / len(squared_errors)
        # Climatological baseline: always predict base_rate
        yes_ratio = sum(1 for r in records if r.label is VerificationLabel.YES) / len(records)
        baseline = yes_ratio * (1 - yes_ratio)  # simplified; full baseline can be added later
        skill = 1.0 - (score / baseline) if baseline > 0 else None

        return BrierScoreResult(
            score=score,
            sample_count=len(squared_errors),
            baseline_score=baseline,
            skill_score=skill,
        )

    def _ece(
        self, records: list[MarketThesisValidationRecord]
    ) -> ECEResult:
        """Expected Calibration Error: partition probabilities into bins,
        compute |avg_prob - accuracy| weighted by bin size.
        """
        bins = _partition_into_bins(records, self._ece_bins)
        ece = 0.0
        bin_results: list[dict[str, Any]] = []
        total = len(records)

        for bin_records in bins:
            if not bin_records:
                continue
            count = len(bin_records)
            avg_prob = sum(r.prediction_probability for r in bin_records) / count
            accuracy = sum(
                1 for r in bin_records if r.label is VerificationLabel.YES
            ) / count
            gap = abs(avg_prob - accuracy)
            ece += (count / total) * gap

            bin_results.append({
                "range": _bin_range(bin_records),
                "count": count,
                "avg_probability": avg_prob,
                "accuracy": accuracy,
                "gap": gap,
            })

        return ECEResult(ece=ece, bin_count=self._ece_bins, bins=tuple(bin_results))

    @staticmethod
    def _timing_offset(
        records: list[MarketThesisValidationRecord],
    ) -> TimingOffsetResult:
        """Compute trading-day offset between thesis_trade_date and verification_trade_date."""
        offsets: dict[int, int] = defaultdict(int)
        offset_values: list[int] = []

        for record in records:
            try:
                thesis_date = date.fromisoformat(record.thesis_trade_date)
                verify_date = date.fromisoformat(record.verification_trade_date)
            except ValueError:
                continue
            offset = (verify_date - thesis_date).days
            offsets[offset] += 1
            offset_values.append(offset)

        if not offset_values:
            return TimingOffsetResult(
                offsets=dict(offsets), mean_offset=None, median_offset=None, sample_count=0,
            )

        offset_values.sort()
        mean = sum(offset_values) / len(offset_values)
        mid = len(offset_values) // 2
        if len(offset_values) % 2 == 0:
            median = (offset_values[mid - 1] + offset_values[mid]) / 2
        else:
            median = float(offset_values[mid])

        return TimingOffsetResult(
            offsets=dict(offsets),
            mean_offset=mean,
            median_offset=median,
            sample_count=len(offset_values),
        )


# ── helpers ──

def _is_yes_correct(record: MarketThesisValidationRecord) -> bool:
    """YES is 'correct' when prediction_probability >= 0.5.
    This is the standard threshold for binary classification from a probability."""
    return record.prediction_probability >= 0.5


def _is_no_correct(record: MarketThesisValidationRecord) -> bool:
    """NO is 'correct' when prediction_probability < 0.5."""
    return record.prediction_probability < 0.5


def _is_narrative_confidence_suspect(record: MarketThesisValidationRecord) -> bool:
    """Flag records where prediction_probability appears to be copied from quality_score.

    This is a heuristic: if |prediction_probability - source_quality_score| < 0.01,
    the record may be using quality_score as a substitute for prediction probability.
    """
    return abs(record.prediction_probability - record.source_quality_score) < 0.01


def _partition_into_bins(
    records: list[MarketThesisValidationRecord], bin_count: int
) -> list[list[MarketThesisValidationRecord]]:
    """Partition records into equal-width probability bins."""
    bins: list[list[MarketThesisValidationRecord]] = [[] for _ in range(bin_count)]
    for record in records:
        prob = record.prediction_probability
        # Clamp to [0, 1) for binning; 1.0 goes into the last bin
        bin_idx = min(int(prob * bin_count), bin_count - 1)
        bins[bin_idx].append(record)
    return bins


def _bin_range(bin_records: list[MarketThesisValidationRecord]) -> str:
    if not bin_records:
        return "[0.0, 0.0]"
    probs = [r.prediction_probability for r in bin_records]
    return f"[{min(probs):.2f}, {max(probs):.2f}]"


