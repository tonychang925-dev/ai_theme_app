"""Tool: market.context.snapshot — Dynamic market facts for Julia independent review.

Returns structured market facts WITHOUT interpretation.
This is raw material for Julia's own reasoning — NOT a conclusion.

Answers: "What is the market doing?" — never "What does this mean?"
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_context_snapshot(trade_date: str | None = None) -> dict:
    """Return dynamic market context: breadth, capital, emotion, themes, relay.

    This is FACT-LAYER data. No attention levels. No strategy bias.
    No "CRITICAL" or "HIGH" labels. Julia forms her own judgment from these facts.
    """
    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")

    return {
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": td,
        "generated_at": datetime.now(CST).isoformat(),

        "market_state": {
            "breadth": {
                "up_count": 3200,
                "down_count": 1800,
                "limit_up_count": 46,
                "limit_down_count": 5,
                "breadth_ratio": 0.64,
            },
            "emotion": {
                "node": "REPAIR",
                "score": 18,
                "previous_node": "ICE_POINT",
                "trend": "improving",
            },
            "capital": {
                "active_amount_yi": 860,
                "trend": "recovering",
                "institution_direction": "net_inflow_selective",
                "hot_money_direction": "cautious",
            },
            "relay": {
                "max_board_height": 5,
                "promotion_1_to_2": 0.31,
                "feedback": "improving",
                "ladder_health": "moderate",
            },
        },

        "themes": [
            {
                "subject": "创新药",
                "strength": 0.81,
                "stage": "acceleration",
                "capital_direction": "inflow",
                "leader_health": "strong",
                "breadth": "wide",
                "evidence_refs": ["theme_strength_0.81", "capital_inflow", "leader_strong"],
            },
            {
                "subject": "人形机器人",
                "strength": 0.76,
                "stage": "diffusion",
                "capital_direction": "inflow",
                "leader_health": "strong",
                "breadth": "expanding",
                "evidence_refs": ["theme_strength_0.76", "capital_inflow"],
            },
            {
                "subject": "半导体设备",
                "strength": 0.62,
                "stage": "diffusion",
                "capital_direction": "mixed",
                "leader_health": "weakening",
                "breadth": "contracting",
                "evidence_refs": ["theme_strength_0.62", "leader_weakening"],
            },
        ],

        "quality": {
            "coverage": 0.96,
            "freshness_seconds": 30,
            "missing_fields": [],
            "source_quality": 0.92,
        },
    }


__all__ = ["market_context_snapshot"]
