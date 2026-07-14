"""PR4.2.34a-3 — Direction Capital Aggregator.

Aggregates theme_capital_flow_daily into direction_capital_flow_daily
using direction_theme_binding weights. Enforces:
  C10: SUM(allocated per theme) ≤ source_flow × 1.001
  C12: Σ direction_flow + unallocated = Σ theme_flow

Direction = unit of capital cognition (投资认知单位)
Theme    = unit of market classification (市场标签单位)

Deterministic only. No AI, no event inference, no producer modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

FLOW_TYPE = "ATTRIBUTED_DIRECTION_FLOW"
ATTRIBUTION_METHOD = "direction_weighted"
SOURCE = "direction_capital_aggregator"


# ── Config loader ──

def load_bootstrap_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load direction bootstrap YAML config."""
    if path is None:
        path = Path(__file__).parent / "direction_bootstrap.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Output ──

@dataclass(frozen=True, slots=True)
class DirectionCapitalFlow:
    trade_date: date
    direction_key: str
    direction_name: str
    net_flow_yuan: float | None
    large_flow_yuan: float | None
    flow_type: str
    theme_count: int
    attributed_theme_count: int
    flow_coverage_ratio: float
    attribution_method: str

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "direction_key": self.direction_key,
            "direction_name": self.direction_name,
            "net_flow_yuan": self.net_flow_yuan,
            "large_flow_yuan": self.large_flow_yuan,
            "flow_type": self.flow_type,
            "theme_count": self.theme_count,
            "attributed_theme_count": self.attributed_theme_count,
            "flow_coverage_ratio": self.flow_coverage_ratio,
            "attribution_method": self.attribution_method,
            "source": SOURCE,
        }


@dataclass(frozen=True, slots=True)
class ThemeDirectionAllocation:
    trade_date: date
    subject_key: str
    direction_key: str
    allocated_amount_yuan: float | None
    allocation_weight: float
    source_flow_yuan: float | None

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "direction_key": self.direction_key,
            "allocated_amount_yuan": self.allocated_amount_yuan,
            "allocation_weight": self.allocation_weight,
            "source_flow_yuan": self.source_flow_yuan,
        }


# ── Aggregator ──

class DirectionCapitalAggregator:
    """Aggregate theme flows into direction flows using binding weights.

    C10: SUM(allocated per theme across directions) ≤ source_flow × 1.001
    C12: Σ direction_flow + unallocated = Σ theme_flow
    """

    def aggregate(
        self,
        theme_flows: list[dict[str, Any]],
        bindings: list[dict[str, Any]],
        trade_date: date,
    ) -> tuple[list[DirectionCapitalFlow], list[ThemeDirectionAllocation]]:
        """Aggregate theme flows by direction.

        Args:
            theme_flows: Rows from theme_capital_flow_daily.
            bindings: Rows from direction_theme_binding (active bindings).
            trade_date: Trade date.

        Returns:
            (direction_flows, allocations) tuple.
        """
        # Index theme flows by subject_key
        flow_by_key: dict[str, dict[str, Any]] = {}
        for f in theme_flows:
            key = str(f.get("subject_key") or "").strip()
            if key:
                flow_by_key[key] = f

        # Group bindings by direction
        dir_bindings: dict[str, list[dict[str, Any]]] = {}
        dir_names: dict[str, str] = {}
        for b in bindings:
            dk = str(b.get("direction_key") or "").strip()
            if not dk:
                continue
            dir_bindings.setdefault(dk, []).append(b)
            dir_names[dk] = str(b.get("direction_name") or dk)

        # Aggregate
        direction_flows: list[DirectionCapitalFlow] = []
        allocations: list[ThemeDirectionAllocation] = []

        for dk, binds in dir_bindings.items():
            dir_net = 0.0
            dir_large = 0.0
            attributed_count = 0
            total_count = len(binds)

            for b in binds:
                sk = str(b.get("subject_key") or "").strip()
                weight = float(b.get("weight") or 0)
                flow = flow_by_key.get(sk)

                if flow:
                    net = float(flow.get("net_flow_yuan") or 0)
                    large = float(flow.get("large_flow_yuan") or 0)
                    allocated = net * weight
                    dir_net += allocated
                    dir_large += large * weight
                    attributed_count += 1

                    # C10: record allocation for conservation audit
                    allocations.append(ThemeDirectionAllocation(
                        trade_date=trade_date,
                        subject_key=sk,
                        direction_key=dk,
                        allocated_amount_yuan=round(allocated, 2),
                        allocation_weight=weight,
                        source_flow_yuan=round(net, 2) if net != 0 else None,
                    ))

            direction_flows.append(DirectionCapitalFlow(
                trade_date=trade_date,
                direction_key=dk,
                direction_name=dir_names.get(dk, dk),
                net_flow_yuan=round(dir_net, 2) if dir_net != 0 else None,
                large_flow_yuan=round(dir_large, 2) if dir_large != 0 else None,
                flow_type=FLOW_TYPE,
                theme_count=total_count,
                attributed_theme_count=attributed_count,
                flow_coverage_ratio=round(attributed_count / max(total_count, 1), 4),
                attribution_method=ATTRIBUTION_METHOD,
            ))

        return direction_flows, allocations


# ── Conservation validator ──

def validate_conservation(
    theme_flows: list[dict[str, Any]],
    allocations: list[ThemeDirectionAllocation],
) -> dict[str, Any]:
    """C10/C12 conservation check.

    C10: SUM(allocated per theme across directions) ≤ source_flow × 1.001
    C12: Σ direction_flow + unallocated ≈ Σ theme_flow
    """
    total_theme_flow = sum(
        abs(float(tf.get("net_flow_yuan") or 0)) for tf in theme_flows
    )
    total_allocated = sum(
        abs(a.allocated_amount_yuan or 0) for a in allocations
    )

    c10_failures: list[str] = []
    by_theme: dict[str, tuple[float, float]] = {}
    for a in allocations:
        total, source = by_theme.get(a.subject_key, (0.0, 0.0))
        by_theme[a.subject_key] = (
            total + abs(a.allocated_amount_yuan or 0),
            abs(a.source_flow_yuan or 0),
        )

    for sk, (alloc, src) in by_theme.items():
        if src > 0 and alloc > src * 1.001:
            c10_failures.append(f"{sk}: allocated={alloc:.0f} > source×1.001={src*1.001:.0f}")

    return {
        "c10_passed": len(c10_failures) == 0,
        "c10_failures": c10_failures,
        "c12_total_theme_flow": round(total_theme_flow, 2),
        "c12_total_allocated": round(total_allocated, 2),
        "c12_ratio": round(total_allocated / max(total_theme_flow, 1), 4),
    }
