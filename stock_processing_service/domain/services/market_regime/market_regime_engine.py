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

        # Determine blocking rule from the highest-priority no_trade_reason
        # PR-13B: distinguish no_active_confirmed_mainline (registry empty)
        # vs no_trade_alive_mainline (registry has mainlines but none trade_alive)
        blocking_rule = ""
        ntr = permission.no_trade_reasons
        if ntr and isinstance(ntr, list) and len(ntr) > 0:
            first = str(ntr[0])
            if "无人工确认主线" in first:
                # Check if registry actually has confirmed mainlines but none trade_alive
                trade_alive_count = sum(1 for lr in life if lr.get("mainline_trade_alive"))
                mainline_alive_count = sum(1 for lr in life if lr.get("mainline_alive"))
                if mainline_alive_count > 0 and trade_alive_count == 0:
                    blocking_rule = "no_trade_alive_mainline"
                elif mainline_alive_count == 0:
                    blocking_rule = "no_active_confirmed_mainline"
                else:
                    blocking_rule = "no_trade_alive_mainline"
            elif "退潮" in first or "风险关闭" in first:
                blocking_rule = "mainline_fading"
            elif "大盘环境" in first:
                blocking_rule = "broad_market_regime_" + broad.broad_market_regime
            elif "情绪" in first or "死亡" in first:
                blocking_rule = "short_term_sentiment_dead"
            elif "观察级" in first:
                blocking_rule = "mainline_watch_only"
            else:
                blocking_rule = first[:80]

        diag = {
            "broad_regime": broad.broad_market_regime,
            "sentiment": sentiment.short_term_sentiment,
            "mainline_env": mainline.mainline_environment,
            "data_quality": "partial" if not kline else "ready",
            "lifecycle_review_count": len(life),
            "lifecycle_alive_count": sum(1 for lr in life if lr.get("mainline_alive")),
            "lifecycle_trade_alive_count": sum(1 for lr in life if lr.get("mainline_trade_alive")),
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
            no_trade_blocking_rule=blocking_rule,
            risk_notes=permission.risk_notes,
            broad_market=broad.to_dict(),
            sentiment=sentiment.to_dict(),
            mainline=mainline.to_dict(),
            diagnostics=diag,
        )
