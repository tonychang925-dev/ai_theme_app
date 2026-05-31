"""PR-11H: MarketRegimeEngine — orchestrator combining all regime sub-engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .broad_market_regime_engine import BroadMarketRegimeEngine
from .short_term_sentiment_engine import ShortTermSentimentEngine
from .mainline_environment_engine import MainlineEnvironmentEngine
from .trading_permission_engine import TradingPermissionEngine
from .models import MarketRegimeReview


@dataclass
class MarketRegimeEngine:
    broad_engine: BroadMarketRegimeEngine = field(default_factory=BroadMarketRegimeEngine)
    sentiment_engine: ShortTermSentimentEngine = field(default_factory=ShortTermSentimentEngine)
    mainline_engine: MainlineEnvironmentEngine = field(default_factory=MainlineEnvironmentEngine)
    permission_engine: TradingPermissionEngine = field(default_factory=TradingPermissionEngine)

    def evaluate(
        self, *,
        trade_date: str = "",
        index_kline: list[dict[str, Any]] | None = None,
        market_snapshot: dict[str, Any] | None = None,
        lifecycle_reviews: list[dict[str, Any]] | None = None,
    ) -> MarketRegimeReview:
        kline = index_kline or []
        snap = market_snapshot or {}
        life = lifecycle_reviews or []

        broad = self.broad_engine.build(index_kline=kline, market_snapshot=snap)
        sentiment = self.sentiment_engine.build(market_snapshot=snap)
        mainline = self.mainline_engine.build(lifecycle_reviews=life)
        permission = self.permission_engine.build(broad=broad, sentiment=sentiment, mainline=mainline)

        ms = "unknown"
        if mainline.mainline_environment == "no_confirmed_mainline":
            ms = "no_confirmed_mainline"
        elif not permission.allow_trade:
            ms = "confirmed_mainline_but_adverse_regime"
        elif permission.trade_mode == "ultra_short_only":
            ms = "confirmed_mainline_ultra_short_only"
        elif permission.trade_mode == "mainline_core_only":
            ms = "confirmed_mainline_choppy_market"
        else:
            ms = "confirmed_mainline_supportive_market"

        diag = {
            "broad_regime": broad.broad_market_regime,
            "sentiment": sentiment.short_term_sentiment,
            "mainline_env": mainline.mainline_environment,
            "data_quality": "partial" if not kline else "ready",
        }

        return MarketRegimeReview(
            trade_date=trade_date,
            broad_market_regime=broad.broad_market_regime,
            short_term_sentiment=sentiment.short_term_sentiment,
            mainline_environment=mainline.mainline_environment,
            market_structure=ms,
            allow_trade=permission.allow_trade,
            trade_mode=permission.trade_mode,
            position_limit=permission.position_limit,
            allowed_actions=permission.allowed_actions,
            forbidden_actions=permission.forbidden_actions,
            no_trade_reasons=permission.no_trade_reasons,
            risk_notes=permission.risk_notes,
            broad_market=broad.to_dict(),
            sentiment=sentiment.to_dict(),
            mainline=mainline.to_dict(),
            diagnostics=diag,
        )
