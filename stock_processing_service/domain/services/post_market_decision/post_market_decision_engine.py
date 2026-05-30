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

        # ── P1-2: extract event_context from report_context ──
        event_context = self._extract_event_context(report_context, theme_context_map)

        theme_decisions = self.theme_engine.build(
            theme_context_map=theme_context_map,
            market_environment=market_environment,
            event_context=event_context,
        )

        stock_decisions = self.leader_engine.build(
            report_context=report_context,
            strong_stock_reviews=strong_stock_reviews,
        )

        watchlist_reviews, watchlist_diag = self.watchlist_engine.build(
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
                "watchlist_join_diagnostics": watchlist_diag,
                "event_context_subject_keys": len(event_context),
            },
        }

    @staticmethod
    def _extract_event_context(
        report_context: dict[str, Any],
        theme_context_map: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Extract per-subject_key event lists from report_context.

        Priority:
        1. report_context.event_theme_map — explicit mapping
        2. report_context.news_event — join by subject_key field
        3. report_context.subject_history — join by subject_key
        """
        result: dict[str, list[dict[str, Any]]] = {}

        # Try event_theme_map first
        event_map = report_context.get("event_theme_map")
        if isinstance(event_map, dict):
            for sk, events in event_map.items():
                key = str(sk)
                if isinstance(events, list):
                    result.setdefault(key, []).extend(events)

        # Try news_event — each row may have subject_key
        news_rows = report_context.get("news_event")
        if isinstance(news_rows, list):
            for row in news_rows:
                if not isinstance(row, dict):
                    continue
                sk = str(row.get("subject_key") or "")
                if sk:
                    result.setdefault(sk, []).append(row)

        # Try subject_history
        sh_rows = report_context.get("subject_history")
        if isinstance(sh_rows, list):
            for row in sh_rows:
                if not isinstance(row, dict):
                    continue
                sk = str(row.get("subject_key") or "")
                if sk:
                    result.setdefault(sk, []).append(row)

        # If no events found, try to create dummy entries for any theme with stock_facts
        # (at least note that no events are available)
        return result
