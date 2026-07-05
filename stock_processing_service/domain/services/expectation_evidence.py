"""M4d: Expectation Evidence — THS EPS forecast scoring.

Converts EPS forecast data into ExpectationEvidence with expectation_level.
Integrates with EvidenceFusionEngine as a new evidence source.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Expectation Level thresholds ────────────────────────────────

EPS_GROWTH_VERY_HIGH = 0.50   # 50%+ growth → Very High
EPS_GROWTH_HIGH = 0.20        # 20-50% growth → High
EPS_GROWTH_MEDIUM = 0.0       # 0-20% growth → Medium

ANALYST_COVERAGE_VERY_HIGH = 50  # 50+ analysts
ANALYST_COVERAGE_HIGH = 20      # 20+ analysts
ANALYST_COVERAGE_MEDIUM = 5     # 5+ analysts — base signal


@dataclass(frozen=True)
class ExpectationEvidence:
    """Per-stock EPS expectation evidence."""

    stock_code: str
    stock_name: str
    year: int
    eps_mean: float | None = None
    eps_min: float | None = None
    eps_max: float | None = None
    analyst_count: int = 0
    industry_avg_eps: float | None = None
    eps_growth: float | None = None       # YoY growth rate
    expectation_level: str = "Medium"     # Very High | High | Medium | Low
    expectation_score: float = 0.0        # 0.0 — 1.0
    confidence: float = 0.0
    source_name: str = "ths"
    source_trace_id: str = ""


def compute_expectation(
    eps_mean: float | None,
    analyst_count: int,
    eps_growth: float | None = None,
    prev_eps: float | None = None,
) -> tuple[float, str]:
    """Compute expectation score and level from EPS data.

    Returns (score 0.0-1.0, level string).
    """
    score = 0.0

    # EPS growth scoring
    if eps_growth is not None:
        if eps_growth > EPS_GROWTH_VERY_HIGH:
            score += 0.70
        elif eps_growth > EPS_GROWTH_HIGH:
            score += 0.50
        elif eps_growth > EPS_GROWTH_MEDIUM:
            score += 0.30
    elif eps_mean is not None and prev_eps is not None and prev_eps > 0:
        growth = (eps_mean - prev_eps) / prev_eps
        if growth > EPS_GROWTH_VERY_HIGH:
            score += 0.70
        elif growth > EPS_GROWTH_HIGH:
            score += 0.50
        elif growth > EPS_GROWTH_MEDIUM:
            score += 0.30

    # Analyst coverage bonus (coverage itself is a signal)
    if analyst_count > ANALYST_COVERAGE_VERY_HIGH:
        score += 0.30
    elif analyst_count > ANALYST_COVERAGE_HIGH:
        score += 0.25
    elif analyst_count >= ANALYST_COVERAGE_MEDIUM:
        score += 0.15

    # EPS positive (profitable) is a base signal
    if eps_mean is not None and eps_mean > 0:
        score += 0.10

    # Cap at 1.0
    score = min(score, 1.0)

    # Level
    if score >= 0.80:
        level = "Very High"
    elif score >= 0.50:
        level = "High"
    elif score >= 0.25:
        level = "Medium"
    else:
        level = "Low"

    return round(score, 2), level


def build_expectation_evidence(
    stock_code: str,
    stock_name: str,
    year: int,
    eps_mean: float | None,
    analyst_count: int,
    industry_avg_eps: float | None = None,
    eps_min: float | None = None,
    eps_max: float | None = None,
    eps_growth: float | None = None,
    trade_date: str = "",
) -> ExpectationEvidence:
    """Build ExpectationEvidence from raw THS EPS forecast data."""
    score, level = compute_expectation(eps_mean, analyst_count, eps_growth)

    return ExpectationEvidence(
        stock_code=stock_code,
        stock_name=stock_name,
        year=year,
        eps_mean=eps_mean,
        eps_min=eps_min,
        eps_max=eps_max,
        analyst_count=analyst_count,
        industry_avg_eps=industry_avg_eps,
        eps_growth=eps_growth,
        expectation_level=level,
        expectation_score=score,
        confidence=min(0.9, analyst_count / 30) if analyst_count > 0 else 0.3,
        source_trace_id=f"ths_eps:{stock_code}:{year}:{trade_date}",
    )
