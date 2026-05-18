"""Feature derivation rules for W2S backtest snapshots.

All functions operate on raw feature dicts (from existing DB tables).
No side effects, no database access.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def classify_leader_role_proxy(row: dict[str, Any]) -> str:
    """Classify leader role proxy from existing fields.

    Returns: leader / card / assist / supplement / unknown
    """
    is_leader = _bool(row.get("is_leader"))
    rank_order = _int(row.get("rank_order"), 999)
    recent_limit_up = _int(row.get("recent_limit_up_count"), 0)
    same_subject_limit_up = _int(row.get("same_subject_limit_up_count"), 0)

    if is_leader and recent_limit_up >= 2:
        return "leader"
    if rank_order == 2 and recent_limit_up >= 1:
        return "card"
    if 3 <= rank_order <= 5 and same_subject_limit_up >= 2:
        return "assist"
    if recent_limit_up == 0 and same_subject_limit_up >= 1:
        return "supplement"
    return "unknown"


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


def compute_confirm_level_from_score(score: Decimal) -> str:
    """Derive confirm level from auction score."""
    if score >= Decimal("75"):
        return "A"
    if score >= Decimal("60"):
        return "B"
    if score >= Decimal("40"):
        return "C"
    return "X"


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
