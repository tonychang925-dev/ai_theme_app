"""Tool 3: review_market_snapshot — Julia's daily context entry point."""
from __future__ import annotations

from core.contracts.decision_envelope import MarketSnapshot, DecisionEnvelope


def review_market_snapshot(date: str | None = None) -> MarketSnapshot:
    """Return today's market overview: sentiment, active themes, top signals, risk alerts.

    Julia calls this every morning — her Morning Brief entry point.
    """
    # TODO Phase 2: Wire to actual market data aggregation

    return MarketSnapshot(
        market_sentiment="偏弱",
        active_themes=("AI Agent", "半导体", "机器人"),
        top_signals=(
            DecisionEnvelope(
                id="dec_20260806_001",
                source="news",
                type="theme_match",
                level="decision",
                impact="positive",
                confidence=0.82,
            ),
            DecisionEnvelope(
                id="dec_20260806_002",
                source="market",
                type="support_alert",
                level="decision",
                impact="unknown",
                confidence=0.75,
            ),
        ),
        risk_alerts=("外围市场波动", "成交未能放量", "AI板块短期过热风险"),
        date=date or "",
    )
