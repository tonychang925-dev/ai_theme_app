from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SetupFactContextBuildError(RuntimeError):
    """Required setup facts are missing; fail loud."""


@dataclass(frozen=True)
class SourceStatus:
    source_status: dict[str, str] = field(default_factory=dict)
    blocking_errors: list[str] = field(default_factory=list)
    non_blocking_warnings: list[str] = field(default_factory=list)

    @property
    def has_blocking_error(self) -> bool:
        return bool(self.blocking_errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_status": dict(self.source_status),
            "blocking_errors": list(self.blocking_errors),
            "non_blocking_warnings": list(self.non_blocking_warnings),
        }


@dataclass(frozen=True)
class PostMarketSetupFactContext:
    trade_date: str
    watch_date: str

    active_mainlines: list[dict[str, Any]]
    strong_hotspot_subjects: list[dict[str, Any]]
    active_subject_keys: set[str]

    lifecycle_by_subject: dict[str, dict[str, Any]]
    market_regime: dict[str, Any]
    trading_principle: dict[str, Any]

    subject_stock_rows: list[dict[str, Any]]
    stock_daily_bars: list[dict[str, Any]]
    limit_up_rows: list[dict[str, Any]]

    subject_market_breadth: dict[str, dict[str, Any]] = field(default_factory=dict)
    prior_daily_bars: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pressure_by_stock: dict[str, dict[str, Any]] = field(default_factory=dict)
    ma_pattern_by_stock: dict[str, dict[str, Any]] = field(default_factory=dict)

    diagnostics: SourceStatus = field(default_factory=SourceStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "watch_date": self.watch_date,
            "active_mainlines": self.active_mainlines,
            "strong_hotspot_subjects": self.strong_hotspot_subjects,
            "active_subject_keys": sorted(self.active_subject_keys),
            "lifecycle_by_subject": self.lifecycle_by_subject,
            "market_regime": self.market_regime,
            "trading_principle": self.trading_principle,
            "subject_stock_rows": self.subject_stock_rows,
            "stock_daily_bars": self.stock_daily_bars,
            "limit_up_rows": self.limit_up_rows,
            "subject_market_breadth": self.subject_market_breadth,
            "prior_daily_bars": self.prior_daily_bars,
            "pressure_by_stock": self.pressure_by_stock,
            "ma_pattern_by_stock": self.ma_pattern_by_stock,
            "diagnostics": self.diagnostics.to_dict(),
        }
