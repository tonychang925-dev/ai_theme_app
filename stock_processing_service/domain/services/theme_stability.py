"""M6: Stability & Market Anchor Layer.

Adds three guards on top of M4-M5 without modifying existing code:

1. ThemeStabilityScore — cross-day persistence + source consistency
2. MarketConfirmationAnchor — limit-up chains, flow share, concentration
3. ThemeDriftDetector — alias/semantic drift detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from stock_processing_service.domain.services.theme_strength import ThemeStrength
from stock_processing_service.domain.services.leader_scoring import LeaderScore


# ── ① Theme Stability Score ─────────────────────────────────────

W_OVERLAP = 0.35
W_PERSISTENCE = 0.30
W_CROSS_SOURCE = 0.35
STABILITY_THRESHOLD = 0.50  # below this → unstable


@dataclass(frozen=True)
class ThemeStabilityResult:
    theme_name: str
    stability_score: float          # 0.0 — 1.0
    overlap_3day: float             # how much theme overlap vs yesterday
    leader_persistence: float       # how many leaders persisted
    cross_source_consistency: float # source agreement across days
    is_stable: bool
    warnings: list[str] = field(default_factory=list)


def compute_theme_stability(
    current: ThemeStrength,
    previous_leaders: dict[str, set[str]] | None = None,
    previous_sources: dict[str, set[str]] | None = None,
) -> ThemeStabilityResult:
    """Compute stability for one theme.

    Args:
        current: current day's theme strength
        previous_leaders: {theme_name: {stock_codes}} from previous day
        previous_sources: {theme_name: {source_names}} from previous day
    """
    prev_leaders = (previous_leaders or {}).get(current.theme_name, set())
    prev_sources = (previous_sources or {}).get(current.theme_name, set())
    curr_sources = set(current.evidence_sources)

    # 1) Overlap: how many leaders persisted from yesterday
    curr_leaders = {s["stock_code"] for s in current.top_stocks}
    overlap = (
        len(curr_leaders & prev_leaders) / max(len(curr_leaders | prev_leaders), 1)
        if prev_leaders else 0.50  # first day → neutral
    )

    # 2) Leader persistence: fraction of top_stocks that are consistent
    persistence = (
        len(curr_leaders & prev_leaders) / max(len(curr_leaders), 1)
        if prev_leaders else 0.50
    )

    # 3) Cross-source consistency: source overlap between days
    consistency = (
        len(curr_sources & prev_sources) / max(len(curr_sources | prev_sources), 1)
        if prev_sources else 0.50
    )

    score = (
        overlap * W_OVERLAP
        + persistence * W_PERSISTENCE
        + consistency * W_CROSS_SOURCE
    )
    score = round(min(score, 1.0), 4)

    warnings: list[str] = []
    if overlap < 0.30:
        warnings.append("主题成分股3日重叠低")
    if persistence < 0.30:
        warnings.append("龙头持续性弱")
    if consistency < 0.30:
        warnings.append("证据源跨日不一致")

    return ThemeStabilityResult(
        theme_name=current.theme_name,
        stability_score=score,
        overlap_3day=round(overlap, 4),
        leader_persistence=round(persistence, 4),
        cross_source_consistency=round(consistency, 4),
        is_stable=score >= STABILITY_THRESHOLD,
        warnings=warnings,
    )


# ── ② Market Confirmation Anchor ───────────────────────────────

W_LIMIT_CHAIN = 0.40
W_FLOW_SHARE = 0.30
W_CONCENTRATION = 0.30
ANCHOR_THRESHOLD = 0.40


@dataclass(frozen=True)
class MarketAnchor:
    theme_name: str
    anchor_score: float
    limit_up_continuity: float    # 0.0-1.0, strength of limit-up chains
    sector_flow_share: float       # 0.0-1.0, % of market flow in this theme
    leader_concentration: float    # 0.0-1.0, top3 concentration
    is_confirmed: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)


def compute_market_anchor(
    theme: ThemeStrength,
    *,
    limit_up_chain_count: int = 0,
    total_market_limit_ups: int = 100,
    total_sector_amount: float = 1.0,
    theme_amount: float = 0.0,
    top3_stock_amount: float = 1.0,
) -> MarketAnchor:
    """Compute market confirmation anchor for a theme.

    Args:
        theme: theme strength from M4f
        limit_up_chain_count: stocks with 2+ consecutive boards in theme
        total_market_limit_ups: total limit-ups market-wide
        total_sector_amount: total market amount (or sector benchmark)
        theme_amount: aggregate amount of theme's stocks
        top3_stock_amount: amount of top3 leaders
    """
    # 1) Limit-up chain continuity
    chain_score = min(1.0, limit_up_chain_count / max(theme.stock_count, 1) * 2)

    # 2) Sector flow share
    flow_share = theme_amount / max(total_sector_amount, 1)
    flow_score = min(1.0, flow_share * 50)  # 2% share → 1.0

    # 3) Leader concentration
    concentration = top3_stock_amount / max(theme_amount, 1)
    # Optimal ~0.4-0.6 (not too concentrated, not too diffuse)
    if 0.35 <= concentration <= 0.65:
        conc_score = 1.0
    elif concentration < 0.35:
        conc_score = concentration / 0.35
    else:
        conc_score = max(0.0, 1.0 - (concentration - 0.65) / 0.35)

    score = (
        chain_score * W_LIMIT_CHAIN
        + flow_score * W_FLOW_SHARE
        + conc_score * W_CONCENTRATION
    )
    score = round(min(score, 1.0), 4)

    return MarketAnchor(
        theme_name=theme.theme_name,
        anchor_score=score,
        limit_up_continuity=round(chain_score, 4),
        sector_flow_share=round(flow_score, 4),
        leader_concentration=round(conc_score, 4),
        is_confirmed=score >= ANCHOR_THRESHOLD,
        diagnostics={
            "limit_up_chain_count": limit_up_chain_count,
            "theme_stock_count": theme.stock_count,
            "flow_share_pct": round(flow_share * 100, 2),
            "top3_concentration_pct": round(concentration * 100, 1),
        },
    )


# ── ③ Theme Drift Detector ──────────────────────────────────────

DRIFT_THRESHOLD = 0.30  # alias change rate above this → unstable


@dataclass(frozen=True)
class DriftReport:
    theme_name: str
    drift_score: float          # 0.0 (stable) — 1.0 (full drift)
    prev_aliases: list[str]
    curr_aliases: list[str]
    alias_change_rate: float    # fraction of aliases that changed
    is_drifting: bool
    note: str = ""


def detect_theme_drift(
    theme_name: str,
    prev_aliases: list[str] | None = None,
    curr_aliases: list[str] | None = None,
) -> DriftReport:
    """Detect theme semantic drift by comparing alias sets between days.

    Args:
        theme_name: current theme name
        prev_aliases: previous day's merged/display aliases
        curr_aliases: current day's merged/display aliases
    """
    prev = set(prev_aliases or [])
    curr = set(curr_aliases or [theme_name])

    if not prev:
        return DriftReport(
            theme_name=theme_name,
            drift_score=0.0,
            prev_aliases=[],
            curr_aliases=list(curr),
            alias_change_rate=0.0,
            is_drifting=False,
            note="first_day_no_baseline",
        )

    # Compute Jaccard distance (1 - similarity)
    intersection = len(prev & curr)
    union = len(prev | curr)
    similarity = intersection / max(union, 1)
    change_rate = 1.0 - similarity

    return DriftReport(
        theme_name=theme_name,
        drift_score=round(change_rate, 4),
        prev_aliases=sorted(prev),
        curr_aliases=sorted(curr),
        alias_change_rate=round(change_rate, 4),
        is_drifting=change_rate > DRIFT_THRESHOLD,
        note=(
            "theme_aliases_stable"
            if change_rate <= DRIFT_THRESHOLD
            else f"alias drift detected: {change_rate:.0%} change"
        ),
    )
