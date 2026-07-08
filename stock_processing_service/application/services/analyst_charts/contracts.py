"""P2.7 — Analyst Chart Contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class AnalystChartArtifact:
    chart_id: str
    trade_date: date
    chart_type: str          # table | bar | line | heatmap | ladder | classification
    title: str
    module: str              # emotion | relay | style | limitup
    data: dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    evidence_refs: tuple[str, ...] = ()
    calibrated: bool = False
    calibration_source: str = ""  # "analyst_pdf" | "analyst_manual" | ""
    source_priority: str = ""     # "metrics_table" | "recap_snapshot" | "estimate"


# ── Unit normalization ──
# All amounts unified to 亿 (100 million CNY) before chart rendering.

def normalize_amount_wan_to_yi(amount_wan: float) -> float:
    """Convert 万元 → 亿元."""
    return round(amount_wan / 10_000, 1)

def normalize_amount_yuan_to_yi(amount_yuan: float) -> float:
    """Convert 元 → 亿元."""
    return round(amount_yuan / 100_000_000, 1)

def normalize_pct(raw: float) -> float:
    """Ensure percentage is 0-100 scale (not 0-1)."""
    return round(raw * 100, 1) if 0 < raw <= 1 else round(raw, 1)
