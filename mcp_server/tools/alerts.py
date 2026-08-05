"""Tool 2: list_active_alerts — Julia's "active awareness"."""
from __future__ import annotations

from core.contracts.decision_envelope import (
    DecisionEnvelope, Evidence, CausalLink, ThemeContext,
    AlertLevel, Lifecycle,
)


def list_active_alerts(level: str = AlertLevel.DECISION) -> list[DecisionEnvelope]:
    """Return all active alerts at the given level.

    Julia calls this every morning at 08:30 — her "主动意识".
    """
    # TODO Phase 2: Wire to actual Decision Table WHERE level >= given level AND active

    return [
        DecisionEnvelope(
            id="dec_20260806_001",
            source="news",
            type="theme_match",
            level=AlertLevel.DECISION,
            evidence=(
                Evidence(type="news", text="AI Agent政策催化", source="cls_api", authority=0.9),
                Evidence(type="capital_flow", text="AI板块资金流入", source="jyhf", authority=0.85),
            ),
            causal_chain=(
                CausalLink(
                    cause="AI Agent技术突破 + 政策催化",
                    effect="产业预期升温",
                    market_response="相关概念股上涨",
                    confidence=0.82,
                ),
            ),
            theme_context=ThemeContext(
                theme_id="9019807",
                lifecycle=Lifecycle.DIFFUSION,
                previous_state=Lifecycle.START,
                change="heat increasing",
                days_active=5,
            ),
            prediction_id="pred_20260806_001",
            confidence=0.82,
            impact="positive",
        ),
        DecisionEnvelope(
            id="dec_20260806_002",
            source="market",
            type="support_alert",
            level=AlertLevel.DECISION,
            evidence=(
                Evidence(type="market_data", text="半导体板块成交放量", source="tdx", authority=0.8),
            ),
            causal_chain=(),
            theme_context=None,
            prediction_id=None,
            confidence=0.75,
            impact="unknown",
        ),
    ]
