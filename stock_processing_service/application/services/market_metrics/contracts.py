"""M2.5 — Market Metrics Contracts.

MarketMetricsSnapshot is the SINGLE canonical fact layer.
All engines (Emotion, Diagnosis, Charts, Workspace) consume from here.
No module queries DB or parses JSON independently.

Key rules:
  - All amounts: internal unit = 亿元 (100M CNY)
  - Every field: value + unit + source + is_calibrated + confidence
  - PDF calibration applied HERE, not in individual consumers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ── Metric source tracking ──

@dataclass(frozen=True, slots=True)
class MetricSource:
    """Where did this metric come from?"""
    source_type: str          # metrics_table / recap_snapshot / db_query / pdf_calibrated / estimate
    source_detail: str = ""   # table name, field name, etc.
    confidence: float = 1.0   # 0-1
    is_calibrated: bool = False


# ── Typed metric with source ──

@dataclass(frozen=True, slots=True)
class TypedMetric:
    value: float
    unit: str
    source: MetricSource
    raw_value: float | None = None  # original value before normalization


# ── Sub-metrics ──

@dataclass(frozen=True, slots=True)
class MarketBreadthMetrics:
    up_count: int; down_count: int
    limit_up_count: int; limit_down_count: int
    up_ratio: float                 # 0-1
    turnover_yi: float              # 亿元
    source: MetricSource


@dataclass(frozen=True, slots=True)
class LimitUpMetrics:
    total_count: int
    chain_board_count: int           # 连板家数
    max_board_height: int            # 最高板（含一字板）
    max_turnover_board_height: int   # 最高换手板
    first_board_count: int           # 首板数
    sealed_board_ratio: float        # 封板率 0-1
    fried_board_count: int           # 炸板数
    source: MetricSource


@dataclass(frozen=True, slots=True)
class RelayEcologyMetrics:
    promotion_1_to_2: float   # 一进二晋级率
    promotion_2_to_3: float   # 二进三晋级率
    promotion_3_to_4: float   # 三进四晋级率
    chain_board_count: int
    max_board_height: int
    max_turnover_board_height: int
    source: MetricSource


@dataclass(frozen=True, slots=True)
class ActiveCapitalMetrics:
    total_turnover_yi: float          # 全市场成交额（亿元）
    active_limitup_amount_yi: float   # 涨停/触板活跃资金成交额（亿元）
    active_ratio: float               # 活跃资金 / 全市场成交额
    source: MetricSource


@dataclass(frozen=True, slots=True)
class EmotionMomentumMetrics:
    # Raw scores (analyst scale, roughly -18 to +10)
    first_board_red_ratio: float
    first_board_big_loss_ratio: float
    chain_board_red_ratio: float
    chain_board_big_loss_ratio: float
    momentum_raw: float              # -18 ~ +10 (analyst scale)
    momentum_normalized: float       # -100 ~ +100
    source: MetricSource


@dataclass(frozen=True, slots=True)
class FundFlowMetrics:
    main_net_inflow_yi: float        # 主力净流入（亿元）
    institution_inflow_yi: float     # 机构净流入（亿元）
    hot_money_inflow_yi: float       # 游资净流入（亿元）
    source: MetricSource


# ── Unified snapshot ──

@dataclass(frozen=True, slots=True)
class MarketMetricsSnapshot:
    """Single canonical fact layer for a trading day.

    ALL modules consume this. None query DB independently.
    """
    trade_date: date

    breadth: MarketBreadthMetrics
    limitup: LimitUpMetrics
    relay: RelayEcologyMetrics
    capital: ActiveCapitalMetrics
    emotion_momentum: EmotionMomentumMetrics
    fund_flow: FundFlowMetrics | None = None

    # Calibration
    calibration_applied: bool = False
    calibration_source: str = ""     # "analyst_pdf" / "analyst_manual"
    calibration_fields: tuple[str, ...] = ()

    # Data quality
    data_quality_score: float = 1.0  # 0-1
    missing_fields: tuple[str, ...] = ()


# ── Unit normalization ──

def normalize_to_yi(value: float, from_unit: str) -> float:
    """Convert to 亿元 (100M CNY)."""
    factors = {
        "yuan": 1e-8,       # 元 → 亿
        "wan": 1e-4,        # 万 → 亿
        "yi": 1.0,          # 亿 → 亿
        "wan_yi": 1e4,      # 万亿 → 亿
    }
    factor = factors.get(from_unit, 1.0)
    return round(value * factor, 2)


def display_amount(value_yi: float) -> str:
    """Display amount in human-readable form."""
    if abs(value_yi) >= 10000:
        return f"{value_yi / 10000:.2f}万亿"
    return f"{value_yi:.0f}亿"


def display_pct(value: float) -> str:
    """Display percentage (0-1 scale input)."""
    if 0 < value <= 1:
        return f"{value * 100:.1f}%"
    return f"{value:.1f}%"
