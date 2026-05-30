from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TradingPrincipleEngine:
    """Build the top-level trading principle — the single gate for all decisions.

    Outputs:
    - Whether trading is allowed tomorrow
    - Position limit
    - Main strategy
    - Allowed / forbidden actions
    - Focus themes
    - No-trade reasons (when applicable)
    """

    def build(
        self,
        *,
        trade_date: Any,
        market_environment: dict[str, Any],
        theme_decisions: list[dict[str, Any]],
        watchlist_reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mode = str(market_environment.get("market_mode") or "wait")
        mainline_themes = [
            x for x in theme_decisions
            if x.get("decision") in {"mainline_focus", "watch_weak_to_strong"}
        ]

        no_trade_reasons: list[str] = []
        if mode == "wait":
            no_trade_reasons.append("市场环境不支持开新仓")
        if not mainline_themes:
            no_trade_reasons.append("无明确主线方向")

        if no_trade_reasons:
            return {
                "trade_date": str(trade_date),
                "market_mode": mode,
                "allow_trade": False,
                "position_limit": 0.0,
                "main_strategy": "空仓等待",
                "focus_themes": [],
                "allowed_actions": [],
                "forbidden_actions": market_environment.get("forbidden_actions") or [
                    "开新仓"
                ],
                "no_trade_reasons": no_trade_reasons,
                "risk_notes": market_environment.get("risk_flags") or [],
            }

        position_limit = float(market_environment.get("position_limit") or 0)
        if mode == "defense":
            main_strategy = "只做主线核心弱转强"
        elif mode == "normal":
            main_strategy = "主线核心优先"
        elif mode == "attack":
            main_strategy = "主线龙头优先"
        else:
            main_strategy = "防守观察"

        return {
            "trade_date": str(trade_date),
            "market_mode": mode,
            "allow_trade": bool(watchlist_reviews) and position_limit > 0,
            "position_limit": position_limit,
            "main_strategy": main_strategy,
            "focus_themes": [
                str(x.get("theme_name") or "")
                for x in mainline_themes[:5]
                if x.get("theme_name")
            ],
            "allowed_actions": market_environment.get("allowed_actions") or [],
            "forbidden_actions": market_environment.get("forbidden_actions") or [],
            "no_trade_reasons": [],
            "risk_notes": market_environment.get("risk_flags") or [],
        }
