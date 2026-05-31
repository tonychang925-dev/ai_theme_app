"""PR-11 Market Regime data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndexTechnicalReview:
    index_code: str = ""
    index_name: str = ""
    trend_state: str = "unknown"
    trend_score: float | None = None
    ma_structure: dict[str, Any] = field(default_factory=dict)
    support_resistance: dict[str, Any] = field(default_factory=dict)
    volume_pattern: str = "unknown"
    macd_state: str = "unknown"
    risk_flags: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_code": self.index_code, "index_name": self.index_name,
            "trend_state": self.trend_state, "trend_score": self.trend_score,
            "ma_structure": self.ma_structure, "support_resistance": self.support_resistance,
            "volume_pattern": self.volume_pattern, "macd_state": self.macd_state,
            "risk_flags": self.risk_flags, "diagnostics": self.diagnostics,
        }


@dataclass
class BroadMarketRegimeReview:
    broad_market_regime: str = "unknown"
    broad_market_score: float | None = None
    index_technical: dict[str, Any] = field(default_factory=dict)
    breadth_score: float | None = None
    volume_score: float | None = None
    risk_flags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broad_market_regime": self.broad_market_regime,
            "broad_market_score": self.broad_market_score,
            "index_technical": self.index_technical,
            "breadth_score": self.breadth_score, "volume_score": self.volume_score,
            "risk_flags": self.risk_flags, "evidence": self.evidence,
            "diagnostics": self.diagnostics,
        }


@dataclass
class ShortTermSentimentReview:
    short_term_sentiment: str = "unknown"
    sentiment_score: float | None = None
    limit_up_count: int | None = None
    limit_down_count: int | None = None
    up_count: int | None = None
    down_count: int | None = None
    relay_status: str = "unknown"
    intraday_fade_status: str = "unknown"
    risk_flags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "short_term_sentiment": self.short_term_sentiment,
            "sentiment_score": self.sentiment_score,
            "limit_up_count": self.limit_up_count, "limit_down_count": self.limit_down_count,
            "up_count": self.up_count, "down_count": self.down_count,
            "relay_status": self.relay_status,
            "intraday_fade_status": self.intraday_fade_status,
            "risk_flags": self.risk_flags, "evidence": self.evidence,
            "diagnostics": self.diagnostics,
        }


@dataclass
class MainlineEnvironmentReview:
    confirmed_mainline_count: int = 0
    trade_alive_mainline_count: int = 0
    mainline_environment: str = "no_confirmed_mainline"
    mainline_environment_score: float | None = None
    tradable_mainlines: list[dict[str, Any]] = field(default_factory=list)
    watch_only_mainlines: list[dict[str, Any]] = field(default_factory=list)
    fading_mainlines: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmed_mainline_count": self.confirmed_mainline_count,
            "trade_alive_mainline_count": self.trade_alive_mainline_count,
            "mainline_environment": self.mainline_environment,
            "mainline_environment_score": self.mainline_environment_score,
            "tradable_mainlines": self.tradable_mainlines,
            "watch_only_mainlines": self.watch_only_mainlines,
            "fading_mainlines": self.fading_mainlines,
            "diagnostics": self.diagnostics,
        }


@dataclass
class TradingPermissionReview:
    allow_trade: bool = False
    trade_mode: str = "no_trade"
    position_limit: float = 0.0
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    no_trade_reasons: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_trade": self.allow_trade, "trade_mode": self.trade_mode,
            "position_limit": self.position_limit,
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
            "no_trade_reasons": self.no_trade_reasons,
            "risk_notes": self.risk_notes,
        }


@dataclass
class MarketRegimeReview:
    trade_date: str = ""
    broad_market_regime: str = "unknown"
    short_term_sentiment: str = "unknown"
    mainline_environment: str = "no_confirmed_mainline"
    market_structure: str = "unknown"
    allow_trade: bool = False
    trade_mode: str = "no_trade"
    position_limit: float = 0.0
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    no_trade_reasons: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    broad_market: dict[str, Any] = field(default_factory=dict)
    sentiment: dict[str, Any] = field(default_factory=dict)
    mainline: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "broad_market_regime": self.broad_market_regime,
            "short_term_sentiment": self.short_term_sentiment,
            "mainline_environment": self.mainline_environment,
            "market_structure": self.market_structure,
            "allow_trade": self.allow_trade,
            "trade_mode": self.trade_mode,
            "position_limit": self.position_limit,
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
            "no_trade_reasons": self.no_trade_reasons,
            "risk_notes": self.risk_notes,
            "broad_market": self.broad_market,
            "sentiment": self.sentiment,
            "mainline": self.mainline,
            "diagnostics": self.diagnostics,
        }
