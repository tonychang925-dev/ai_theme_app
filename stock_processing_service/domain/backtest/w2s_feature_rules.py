"""Feature derivation rules for W2S backtest snapshots.

All functions operate on raw feature dicts (from existing DB tables).
No side effects, no database access.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def classify_leader_role_proxy(row: dict[str, Any]) -> str:
    """Classify leader role proxy from existing fields (v0.3 multi-field fallback).

    Priority: is_leader → rank_order → recent_limit_up → prior7 → watch_score → candidate_score

    Returns: leader / card / assist / strong_trend / potential_leader / unknown
    """
    is_leader = _bool(row.get("is_leader"))
    rank_order = _int(row.get("rank_order"), 999)
    recent_limit_up = _int(row.get("recent_limit_up_count"), 0)
    prior7_limitup = _int(row.get("prior7_limitup_days"), 0)
    prior7_strong = _int(row.get("prior7_strong_days"), 0)
    same_subject_limit_up = _int(row.get("same_subject_limit_up_count"), 0)
    watch_score = float(row.get("watch_score") or 0)
    candidate_score = float(row.get("candidate_score") or 0)

    # Tier 1: explicit leader signals
    if is_leader or (rank_order == 1 and recent_limit_up >= 1):
        return "leader"

    # Tier 2: card (rank 2 with some lead history)
    if rank_order == 2 and (recent_limit_up >= 1 or prior7_limitup >= 1):
        return "card"

    # Tier 3: assist (ranks 3-5 with board effect)
    if 3 <= rank_order <= 5 and (same_subject_limit_up >= 2 or prior7_limitup >= 2):
        return "assist"

    # Tier 4: strong trend (history-based, multi-field)
    if prior7_strong >= 2 and watch_score >= 70:
        return "strong_trend"

    # Tier 5: potential leader (candidate quality signals)
    if candidate_score >= 75 and prior7_limitup >= 1:
        return "potential_leader"

    # Tier 6: strong supplement (has history but lower rank)
    if prior7_limitup >= 2 or (prior7_strong >= 3 and rank_order <= 10):
        return "strong_trend"

    return "unknown"


# ── Weak type classification (single source of truth, from BuildWeakToStrongCandidateUseCase) ──

def classify_weak_type(
    *,
    pct_chg: float,
    prev_day_pct: float = 0.0,
    prev_day_limit_up: bool = False,
) -> str:
    """Classify weak type from daily bar data.

    Replicates BuildWeakToStrongCandidateUseCase.build_candidates() logic.
    This is the SINGLE SOURCE OF TRUTH — backfill services must import this,
    not re-implement.
    """
    if prev_day_limit_up and pct_chg < 0:
        return "bad_limit_up"
    if pct_chg <= -5.0:
        return "big_negative_line"
    if -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
        return "upper_shadow"
    if pct_chg <= -1.0:
        return "high_open_low_close"
    return "fake_break"


# ── Weak type quality scoring (v0.3) ──

WEAK_TYPE_QUALITY: dict[str, dict[str, Any]] = {
    "big_negative_line":   {"quality": "preferred", "score_bonus": Decimal("10")},
    "bad_limit_up":        {"quality": "preferred", "score_bonus": Decimal("8")},
    "upper_shadow":        {"quality": "neutral",   "score_bonus": Decimal("0")},
    "fake_break":          {"quality": "neutral",   "score_bonus": Decimal("0")},
    "high_open_low_close": {"quality": "danger",    "score_bonus": Decimal("-15")},
}


def classify_weak_type_quality(weak_type: str) -> str:
    """Classify weak type into preferred / neutral / danger."""
    return WEAK_TYPE_QUALITY.get(str(weak_type or "").strip().lower(), {}).get("quality", "unknown")


def weak_type_score_bonus(weak_type: str) -> Decimal:
    """Score adjustment based on weak type quality."""
    return WEAK_TYPE_QUALITY.get(str(weak_type or "").strip().lower(), {}).get("score_bonus", Decimal("0"))


def apply_weak_type_downgrade(
    *,
    weak_type: str,
    pool_entry_type: str,
    support_strength: Decimal | None = None,
    mainline_strength_score: Decimal | None = None,
    leader_role_proxy: str = "unknown",
) -> str:
    """v0.3: downgrade dangerous weak types unless supported by strong evidence.

    high_open_low_close → observe_only unless:
      - support_strength >= 70
      - mainline_strength_score >= 70
      - leader_role_proxy in {leader, card, strong_trend}
    """
    wt = str(weak_type or "").strip().lower()
    quality = classify_weak_type_quality(wt)

    if quality == "danger":
        # Only allow formal if all three safety conditions met
        ss = support_strength or Decimal("0")
        ms = mainline_strength_score or Decimal("0")
        if ss >= Decimal("70") and ms >= Decimal("70") and leader_role_proxy in {"leader", "card", "strong_trend"}:
            return "formal"
        return "observe_only"

    return pool_entry_type


def classify_board_type(stock_id: str) -> tuple[str, bool]:
    """Classify board type and 20cm flag from stock_id.

    Returns: (board_type, is_20cm)
    """
    sid = str(stock_id or "").strip().upper()
    if "." in sid:
        sid = sid.split(".", 1)[0]
    if sid.startswith("3"):
        return "chinext", True
    if sid.startswith("688"):
        return "star", True
    if sid.startswith(("8", "4")):
        return "beijing", False
    return "main_board", False


def compute_leader_score_proxy(row: dict[str, Any]) -> Decimal:
    """Proxy leader score from rank + recent_limit_up + is_leader."""
    score = Decimal("40")
    if _bool(row.get("is_leader")):
        score += Decimal("20")
    rank = _int(row.get("rank_order"), 999)
    if rank <= 3:
        score += Decimal(str((4 - rank) * 8))
    recent = _int(row.get("recent_limit_up_count"), 0)
    score += min(Decimal(str(recent)) * Decimal("5"), Decimal("15"))
    return min(score, Decimal("100"))


def compute_two_board_quality_score(row: dict[str, Any]) -> Decimal:
    """Estimate two-board quality from prior7 features + rank.

    Higher = better two-board candidate (e.g. first 2nd board in subject).
    """
    score = Decimal("30")
    prior7_limitup = _int(row.get("prior7_limitup_days"), 0)
    prior7_strong = _int(row.get("prior7_strong_days"), 0)
    rank = _int(row.get("rank_order"), 999)

    score += min(Decimal(str(prior7_limitup)) * Decimal("8"), Decimal("24"))
    score += min(Decimal(str(prior7_strong)) * Decimal("4"), Decimal("12"))
    if rank <= 2:
        score += Decimal("20")
    elif rank <= 5:
        score += Decimal("10")
    if _bool(row.get("is_leader")):
        score += Decimal("14")
    return min(score, Decimal("100"))


def compute_auction_score(
    open_strength: Decimal | None = None,
    amount_strength: Decimal | None = None,
    tail_strength: Decimal | None = None,
    stability_score: Decimal | None = None,
    last_minute_grab_score: Decimal | None = None,
    risk_penalty: Decimal | None = None,
) -> Decimal:
    """Compute auction score with weight re-normalization.

    Missing features are NOT treated as 0 — weights are re-normalized.
    """
    components: list[tuple[str, Decimal, Decimal]] = [
        ("open_strength", open_strength, Decimal("0.35")),
        ("amount_strength", amount_strength, Decimal("0.30")),
        ("tail_strength", tail_strength, Decimal("0.20")),
        ("stability_score", stability_score, Decimal("0.10")),
        ("last_minute_grab_score", last_minute_grab_score, Decimal("0.05")),
    ]

    available = [(name, score, w) for name, score, w in components if score is not None]

    if not available:
        return Decimal("0")

    weight_sum = sum(w for _, _, w in available)
    if weight_sum == Decimal("0"):
        return Decimal("0")

    raw_score = sum(score * w for _, score, w in available) / weight_sum

    if risk_penalty is not None:
        raw_score -= risk_penalty

    return max(Decimal("0"), min(raw_score, Decimal("100")))


def compute_confirm_level_from_score(score: Decimal, *, use_quantile: bool = False) -> str:
    """Derive confirm level from auction score.

    v0.1 (fixed thresholds): A>=75, B>=60, C>=40, else X
    v0.2 (quantile-based): calibrated via distribution

    For real auction data, returns A/B/C/X.
    For proxy data, caller should use classify_proxy_level() instead.
    """
    if use_quantile:
        return _quantile_level(score)
    if score >= Decimal("75"):
        return "A"
    if score >= Decimal("60"):
        return "B"
    if score >= Decimal("40"):
        return "C"
    return "X"


# ── v0.1 quantile thresholds (will be recalibrated from data) ──
_QUANTILE_THRESHOLDS: dict[str, Decimal] = {
    "A": Decimal("75"),
    "B": Decimal("60"),
    "C": Decimal("40"),
}


def _quantile_level(score: Decimal) -> str:
    for level in ("A", "B", "C"):
        if score >= _QUANTILE_THRESHOLDS[level]:
            return level
    return "X"


def set_quantile_thresholds(a: Decimal, b: Decimal, c: Decimal) -> None:
    """Set quantile-based thresholds dynamically (for calibration runs)."""
    _QUANTILE_THRESHOLDS["A"] = a
    _QUANTILE_THRESHOLDS["B"] = b
    _QUANTILE_THRESHOLDS["C"] = c


# ── Proxy level classification (fixed in v0.2) ──

def classify_proxy_level(
    *,
    auction_open_pct: Decimal | None = None,
    has_auction_snapshot: bool = False,
    open_vs_pre_close: Decimal | None = None,
    daily_pct_chg: Decimal | None = None,
) -> str:
    """Classify proxy confirm level for signals without real auction data.

    Levels:
      proxy_unconfirmed: no auction/bar data, truly unconfirmed
      proxy_positive_open: T+1 open >= pre_close, favorable
      proxy_negative_open: T+1 open < pre_close, unfavorable
      proxy_X: explicitly rejected by proxy condition (extreme gap down, etc.)
    """
    # No data at all → truly unconfirmed
    if auction_open_pct is None and daily_pct_chg is None:
        return "proxy_unconfirmed"

    # If we have auction snapshot (but not full series), use open_pct
    pct = auction_open_pct if auction_open_pct is not None else daily_pct_chg

    if pct is None:
        return "proxy_unconfirmed"

    # Explicit reject: extreme gap down (>5%)
    if pct <= Decimal("-5"):
        return "proxy_X"

    # Positive open
    if pct >= Decimal("0"):
        return "proxy_positive_open"

    # Negative but not extreme
    if pct < Decimal("0"):
        return "proxy_negative_open"

    return "proxy_unconfirmed"


def compute_proxy_confirm_score(
    *,
    auction_open_pct: Decimal | None = None,
    daily_pct_chg: Decimal | None = None,
    candidate_score: Decimal | None = None,
) -> Decimal:
    """Compute a simplified proxy confirmation score.

    Uses available proxy data to estimate confirmation strength.
    This is NOT a replacement for real auction scoring.
    """
    score = Decimal("50")  # neutral baseline
    pct = auction_open_pct if auction_open_pct is not None else daily_pct_chg

    if pct is not None:
        # +5 per 1% positive open, capped at +25
        if pct > Decimal("0"):
            score += min(pct * Decimal("5"), Decimal("25"))
        # -10 per 1% negative open, capped at -30
        elif pct < Decimal("0"):
            score += max(pct * Decimal("10"), Decimal("-30"))

    # Boost from candidate quality
    if candidate_score is not None:
        score += min((candidate_score - Decimal("50")) * Decimal("0.2"), Decimal("10"))

    return max(Decimal("0"), min(score, Decimal("100")))


def compute_bull_stock_score(
    gap_not_filled_score: Decimal | None = None,
    high_volume_not_broken_score: Decimal | None = None,
    double_volume_not_broken_score: Decimal | None = None,
    ma_alignment_score: Decimal | None = None,
    up_volume_down_shrink_score: Decimal | None = None,
) -> Decimal:
    """Compute bull stock composite score.

    Missing sub-scores are re-normalized, not treated as 0.
    """
    components: list[tuple[str, Decimal, Decimal]] = [
        ("gap_not_filled", gap_not_filled_score, Decimal("0.30")),
        ("high_volume_not_broken", high_volume_not_broken_score, Decimal("0.25")),
        ("double_volume_not_broken", double_volume_not_broken_score, Decimal("0.20")),
        ("ma_alignment", ma_alignment_score, Decimal("0.15")),
        ("up_volume_down_shrink", up_volume_down_shrink_score, Decimal("0.10")),
    ]

    available = [(name, score, w) for name, score, w in components if score is not None]

    if not available:
        return Decimal("0")

    weight_sum = sum(w for _, _, w in available)
    if weight_sum == Decimal("0"):
        return Decimal("0")

    return sum(score * w for _, score, w in available) / weight_sum


def determine_confirm_source(
    has_auction_snapshot: bool,
    has_auction_series: bool,
    has_daily_bar: bool,
) -> str:
    """Determine confirm_source from data availability.

    Priority: real_auction > auction_snapshot > daily_open_proxy > missing
    """
    if has_auction_series:
        return "real_auction"
    if has_auction_snapshot:
        return "auction_snapshot"
    if has_daily_bar:
        return "daily_open_proxy"
    return "missing"


def determine_auction_feature_mode(has_auction_series: bool) -> str:
    if has_auction_series:
        return "real_auction_series"
    return "auction_proxy"


def build_missing_features(
    has_auction_series: bool,
    has_auction_snapshot: bool,
    has_daily_bar: bool,
    has_mainline_data: bool,
    has_leader_data: bool,
) -> list[dict[str, str]]:
    """Build missing_features JSONB list."""
    missing: list[dict[str, str]] = []
    if not has_auction_series:
        missing.append({
            "feature": "auction_stability_score",
            "reason": "missing_auction_series",
            "severity": "degraded",
        })
        missing.append({
            "feature": "last_minute_grab_score",
            "reason": "missing_auction_series",
            "severity": "degraded",
        })
    if not has_auction_snapshot and not has_auction_series:
        missing.append({
            "feature": "auction_open_pct",
            "reason": "missing_auction_data",
            "severity": "degraded",
        })
        missing.append({
            "feature": "auction_amount",
            "reason": "missing_auction_data",
            "severity": "degraded",
        })
    if not has_daily_bar:
        missing.append({
            "feature": "daily_bar_data",
            "reason": "missing_daily_bar",
            "severity": "blocking",
        })
    if not has_mainline_data:
        missing.append({
            "feature": "mainline_strength_score",
            "reason": "missing_mainline_data",
            "severity": "degraded",
        })
    if not has_leader_data:
        missing.append({
            "feature": "leader_role_proxy",
            "reason": "missing_leader_identity_data",
            "severity": "degraded",
        })
    return missing


# ── Helpers ──

def _d(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
