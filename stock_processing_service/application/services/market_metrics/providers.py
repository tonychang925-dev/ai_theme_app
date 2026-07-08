"""M2.5 Phase 2.0 — Market Microstructure Provider Interfaces.

Defines the contracts that data providers must implement.
MarketMetricsService consumes these interfaces — never raw SQL directly.

This layer ensures:
  1. Provider swap (a-stock-data → TDX → custom) without touching MarketMetrics
  2. MockProvider for RelayMetrics validation before production integration
  3. No second computation path — all data enters through these ports

Architecture:
  a-stock-data / THS / TDX / ...
        │
        ▼
  LimitUpProvider (Protocol)  ←── phase 2.0 (this file)
  YesterdayLimitUpProvider
  FriedBoardProvider
  LimitDownProvider
        │
        ▼
  MarketMetricsService
        │
        ▼
  Consumers (Diagnosis, Chart, Emotion, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


# ── Provider DTOs ──

@dataclass(frozen=True, slots=True)
class LimitUpStock:
    """A single stock that touched the limit-up board."""
    stock_code: str
    stock_name: str
    trade_date: date

    pct_chg: float             # closing % change
    turnover_rate: float       # 换手率 (%)
    amount: float              # 成交额 (元)
    volume: float              # 成交量 (股)
    big_order_net: float       # 大单净量

    # Board type
    board_type: str            # "主板" | "创业板" | "科创板" | "北交所"
    is_st: bool = False

    # Limit-up detail (phase 2.2 fried board enrichment)
    first_limit_time: str | None = None    # "09:35:00"
    last_limit_time: str | None = None
    open_count: int = 0                    # 开板次数
    sealed_duration_min: int = 0           # 封板持续时间（分钟）


@dataclass(frozen=True, slots=True)
class YesterdayLimitUpStock:
    """A stock that hit limit-up on the PREVIOUS trading day.

    Used for RelayMetrics: yesterday's first-board stocks → today's
    second-board stocks → REAL promotion rates (no streak backtracking).
    """
    stock_code: str
    stock_name: str
    trade_date: date           # yesterday's date
    board_count: int           # yesterday's board height (1=first, 2=second, ...)
    sealed: bool               # did it close at limit yesterday?
    pct_chg: float             # yesterday's closing %


@dataclass(frozen=True, slots=True)
class FriedBoardStock:
    """A stock that hit limit-up but FAILED to seal (炸板).

    Enriches LimitUpMetrics with: first limit time, open count,
    seal order size changes, etc.
    """
    stock_code: str
    stock_name: str
    trade_date: date

    first_limit_time: str      # "09:35:00"
    open_count: int            # how many times it opened after hitting limit
    last_limit_time: str | None  # final seal time (None = never sealed)
    max_seal_amount_yi: float | None  # peak封单金额（亿元）
    final_seal_amount_yi: float | None


@dataclass(frozen=True, slots=True)
class LimitDownStock:
    """A stock that hit the limit-DOWN board (跌停).

    Used for LossEffectMetrics: 跌停数 + 大面数 + 高位断板.
    """
    stock_code: str
    stock_name: str
    trade_date: date
    pct_chg: float             # typically close to -10% / -20%
    board_count_before: int    # board height before this crash (0 if no prior board)
    is_leader: bool = False    # was this stock a leader/龙头 before the crash?


# ── Provider Interfaces (Protocols) ──


class LimitUpProvider(Protocol):
    """Provide today's limit-up board data.

    Current impl: ths_hot_reason_snapshot (hybrid)
    Future impl:  a-stock-data limit_up_pool + fried_board_pool
    """

    async def get_limit_up_stocks(self, trade_date: date) -> list[LimitUpStock]:
        """Return all stocks that touched limit-up today."""
        ...


class YesterdayLimitUpProvider(Protocol):
    """Provide yesterday's limit-up board data.

    This is THE most impactful Phase 2 integration:
    yesterday's pool JOIN today's pool → real promotion rates.

    Current: streak backtracking from ths_hot_reason_snapshot (弱推理)
    Future:  a-stock-data yesterday_limit_up_pool (精确)
    """

    async def get_yesterday_stocks(self, trade_date: date) -> list[YesterdayLimitUpStock]:
        """Return stocks that hit limit-up on the PREVIOUS trading day."""
        ...


class FriedBoardProvider(Protocol):
    """Provide fried board (炸板) detail data.

    Current: derived from pct_chg threshold (Phase 0)
    Future:  a-stock-data fried_board_pool with open_count, seal detail
    """

    async def get_fried_stocks(self, trade_date: date) -> list[FriedBoardStock]:
        """Return stocks that hit limit-up but failed to seal."""
        ...


class LimitDownProvider(Protocol):
    """Provide limit-down board (跌停) data.

    Current: NOT AVAILABLE (gap)
    Future:  a-stock-data limit_down_pool
    """

    async def get_limit_down_stocks(self, trade_date: date) -> list[LimitDownStock]:
        """Return stocks that hit limit-down today."""
        ...


# ── Mock Providers (for RelayMetrics validation) ──


class MockYesterdayLimitUpProvider:
    """Mock yesterday limit-up data for testing RelayMetrics.

    Simulates a known historical day to validate promotion rate
    calculations before connecting real a-stock-data.
    """

    def __init__(self, stocks: list[YesterdayLimitUpStock] | None = None):
        self._stocks = stocks or []

    async def get_yesterday_stocks(self, trade_date: date) -> list[YesterdayLimitUpStock]:
        return [s for s in self._stocks if s.trade_date == trade_date]


class MockLimitUpProvider:
    """Mock today's limit-up data for testing."""

    def __init__(self, stocks: list[LimitUpStock] | None = None):
        self._stocks = stocks or []

    async def get_limit_up_stocks(self, trade_date: date) -> list[LimitUpStock]:
        return [s for s in self._stocks if s.trade_date == trade_date]
