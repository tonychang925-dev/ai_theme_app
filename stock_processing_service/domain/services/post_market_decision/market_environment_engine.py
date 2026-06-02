from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarketEnvironmentEngine:
    """Build market environment review from report_context.market.

    Classifies market into four modes (attack/normal/defense/wait)
    and derives position limits, allowed/forbidden actions, and risk flags.
    """

    def build(
        self,
        *,
        trade_date: Any,
        report_context: dict[str, Any],
        market_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market = dict(report_context.get("market") or {})
        fallback_used: list[str] = []

        score = self._float(market.get("market_health_score"))
        limit_up = self._int(market.get("limit_up_count"))
        limit_down = self._int(market.get("limit_down_count"))

        if score is None:
            if not market:
                score = 0.0
                fallback_used.append("market_score.missing_context_default_zero")
            else:
                score = self._score_from_counts(limit_up, limit_down)
                fallback_used.append("market_score.from_limit_counts")

        mode = self._classify_mode(score, limit_up, limit_down)

        if mode == "attack":
            allow_trade = True
            position_limit = 1.0
            allowed_actions = ["主线龙头", "龙二卡位", "主线核心弱转强"]
            forbidden_actions = ["非主线杂毛追涨"]
        elif mode == "normal":
            allow_trade = True
            position_limit = 0.5
            allowed_actions = ["主线核心", "主线核心弱转强"]
            forbidden_actions = ["非主线追涨", "后排套利"]
        elif mode == "defense":
            allow_trade = True
            position_limit = 0.3
            allowed_actions = ["只看主线核心弱转强"]
            forbidden_actions = ["高位接力", "非主线追涨", "无资金确认的套利股"]
        else:
            allow_trade = False
            position_limit = 0.0
            allowed_actions = []
            forbidden_actions = ["开新仓", "追涨", "接力", "套利"]

        risk_flags = self._risk_flags(market, mode, limit_down)

        return {
            "trade_date": str(trade_date),
            "market_mode": mode,
            "market_score": float(score or 0),
            "emotion_stage": str(
                market.get("relay_sentiment_status")
                or market.get("short_term_sentiment_status")
                or "unknown"
            ),
            "allow_trade": allow_trade,
            "position_limit": position_limit,
            "allowed_actions": allowed_actions,
            "forbidden_actions": forbidden_actions,
            "risk_flags": risk_flags,
            "evidence": {
                "market_health_score": market.get("market_health_score"),
                "limit_up_count": market.get("limit_up_count"),
                "limit_down_count": market.get("limit_down_count"),
                "breadth_status": market.get("breadth_status"),
                "short_term_sentiment_status": market.get("short_term_sentiment_status"),
                "relay_sentiment_status": market.get("relay_sentiment_status"),
                "intraday_fade_status": market.get("intraday_fade_status"),
            },
            "diagnostics": {
                "source": "report_context.market",
                "fallback_used": fallback_used,
                "data_quality": "ready" if market else "missing_market_context",
            },
        }

    @staticmethod
    def _classify_mode(score: float, limit_up: int, limit_down: int) -> str:
        if score >= 75 and limit_up >= 60 and limit_down <= 5:
            return "attack"
        if score >= 55 and limit_up >= 35:
            return "normal"
        if score >= 35:
            return "defense"
        return "wait"

    @staticmethod
    def _score_from_counts(limit_up: int, limit_down: int) -> float:
        return max(0.0, min(100.0, 50.0 + limit_up * 0.5 - limit_down * 2.0))

    @staticmethod
    def _risk_flags(market: dict[str, Any], mode: str, limit_down: int) -> list[str]:
        flags: list[str] = []
        if mode in {"defense", "wait"}:
            flags.append("市场环境偏弱")
        if limit_down >= 10:
            flags.append("跌停家数偏多")
        raw = str(market.get("intraday_fade_status") or "").lower()
        if raw in {"fade", "weak", "退潮"}:
            flags.append("盘中退潮风险")
        return flags

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _int(value: Any) -> int:
        try:
            if value in (None, ""):
                return 0
            return int(float(value))
        except Exception:
            return 0
