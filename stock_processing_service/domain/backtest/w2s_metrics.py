"""Performance metrics computation for W2S backtest signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class ValidationMetrics:
    sample_count: int
    win_rate_1d: Decimal
    win_rate_3d: Decimal
    win_rate_5d: Decimal
    avg_return_3d: Decimal
    avg_return_5d: Decimal
    max_drawdown_5d: Decimal
    hit_limit_up_pct: Decimal
    loss_over_5pct_pct: Decimal


def compute_validation_metrics(rows: list[dict[str, Any]]) -> ValidationMetrics:
    """Compute aggregate metrics from a list of validation rows."""
    count = len(rows)
    if count == 0:
        return ValidationMetrics(
            sample_count=0,
            win_rate_1d=Decimal("0"),
            win_rate_3d=Decimal("0"),
            win_rate_5d=Decimal("0"),
            avg_return_3d=Decimal("0"),
            avg_return_5d=Decimal("0"),
            max_drawdown_5d=Decimal("0"),
            hit_limit_up_pct=Decimal("0"),
            loss_over_5pct_pct=Decimal("0"),
        )

    win_1d = sum(1 for r in rows if _bool(r.get("is_win_1d")))
    win_3d = sum(1 for r in rows if _bool(r.get("is_win_3d")))
    win_5d = sum(1 for r in rows if _bool(r.get("is_win_5d")))
    hit_limit_5d = sum(1 for r in rows if _bool(r.get("hit_limit_up_5d")))
    loss_over_5 = sum(1 for r in rows if _bool(r.get("loss_over_5pct")))

    ret_3d = [_d(r.get("next_3d_return"), "0") for r in rows]
    ret_5d = [_d(r.get("next_5d_return"), "0") for r in rows]
    dd_5d = [_d(r.get("max_drawdown_5d"), "0") for r in rows]

    avg_ret_3d = sum(ret_3d) / count  # type: ignore[arg-type]
    avg_ret_5d = sum(ret_5d) / count  # type: ignore[arg-type]
    max_dd_5d = min(dd_5d)  # type: ignore[type-var]

    return ValidationMetrics(
        sample_count=count,
        win_rate_1d=Decimal(str(win_1d)) / Decimal(str(count)),
        win_rate_3d=Decimal(str(win_3d)) / Decimal(str(count)),
        win_rate_5d=Decimal(str(win_5d)) / Decimal(str(count)),
        avg_return_3d=avg_ret_3d.quantize(Decimal("0.000001")),  # type: ignore[union-attr]
        avg_return_5d=avg_ret_5d.quantize(Decimal("0.000001")),  # type: ignore[union-attr]
        max_drawdown_5d=max_dd_5d.quantize(Decimal("0.000001")),  # type: ignore[union-attr]
        hit_limit_up_pct=Decimal(str(hit_limit_5d)) / Decimal(str(count)),
        loss_over_5pct_pct=Decimal(str(loss_over_5)) / Decimal(str(count)),
    )


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
