from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .leader_core_engine import LeaderCoreEngine
from .market_environment_engine import MarketEnvironmentEngine
from .next_day_watchlist_engine import NextDayWatchlistEngine
from .theme_decision_engine import ThemeDecisionEngine
from .trading_principle_engine import TradingPrincipleEngine


@dataclass
class PostMarketDecisionEngine:
    """Orchestrator that chains all five sub-engines in order.

    Flow:
      MarketEnvironment → ThemeDecision → LeaderCore
          → NextDayWatchlist → TradingPrinciple

    Returns a single dict with keys:
      market_environment_review, theme_decision_reviews,
      strong_stock_decision_reviews, watchlist_reviews,
      trading_principle, decision_diagnostics
    """

    market_engine: MarketEnvironmentEngine = field(default_factory=MarketEnvironmentEngine)
    theme_engine: ThemeDecisionEngine = field(default_factory=ThemeDecisionEngine)
    leader_engine: LeaderCoreEngine = field(default_factory=LeaderCoreEngine)
    watchlist_engine: NextDayWatchlistEngine = field(
        default_factory=NextDayWatchlistEngine
    )
    principle_engine: TradingPrincipleEngine = field(
        default_factory=TradingPrincipleEngine
    )

    def execute(
        self,
        *,
        trade_date: Any,
        report_context: dict[str, Any],
        theme_context_map: dict[str, dict[str, Any]],
        market_summary: dict[str, Any] | None = None,
        strong_stock_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        market_environment = self.market_engine.build(
            trade_date=trade_date,
            report_context=report_context,
            market_summary=market_summary,
        )

        theme_decisions = self.theme_engine.build(
            theme_context_map=theme_context_map,
            market_environment=market_environment,
        )

        stock_decisions = self.leader_engine.build(
            report_context=report_context,
            strong_stock_reviews=strong_stock_reviews,
        )

        watchlist_reviews = self.watchlist_engine.build(
            theme_decisions=theme_decisions,
            stock_decisions=stock_decisions,
            market_environment=market_environment,
        )

        trading_principle = self.principle_engine.build(
            trade_date=trade_date,
            market_environment=market_environment,
            theme_decisions=theme_decisions,
            watchlist_reviews=watchlist_reviews,
        )

        return {
            "market_environment_review": market_environment,
            "theme_decision_reviews": theme_decisions,
            "strong_stock_decision_reviews": stock_decisions,
            "watchlist_reviews": watchlist_reviews,
            "trading_principle": trading_principle,
            "decision_diagnostics": {
                "theme_decision_count": len(theme_decisions),
                "stock_decision_count": len(stock_decisions),
                "watchlist_count": len(watchlist_reviews),
                "market_mode": market_environment.get("market_mode"),
            },
        }
