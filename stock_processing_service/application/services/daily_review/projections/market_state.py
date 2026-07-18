"""Market State projection — Snapshot First.

Data source: Approved Snapshot (emotion_review + chart_reviews).
NO engine_report fallback.
"""

from __future__ import annotations

from typing import Any


def project_market_state(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_chart_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    emotion = snapshot_emotion or {}
    charts = snapshot_chart_reviews or []

    return {
        "regime": _build_regime(emotion),
        "emotion": _build_emotion_block(emotion),
        "facts": _build_facts(charts),
        "market_health_score": None,
        "emotion_score": emotion.get("emotion_score"),
        "fade_status": "",
        "relay_summary": _build_relay_summary(charts),
        "new_high_brief": _build_new_high_brief(charts),
        "index_technical": [],
        "chart_summary": _build_chart_summary(charts),
        "summary": emotion.get("summary", ""),
    }


def _build_regime(emotion: dict[str, Any]) -> dict[str, Any]:
    return {
        "broad_market_regime": "",
        "short_term_sentiment": "",
        "mainline_environment": "",
        "allow_trade": True,
        "trade_mode": emotion.get("strategy_bias", ""),
        "position_limit": None,
        "no_trade_reasons": [],
    }


def _build_emotion_block(emotion: dict[str, Any]) -> dict[str, Any]:
    return {
        "emotion_node": emotion.get("emotion_node", ""),
        "emotion_label": emotion.get("emotion_label", ""),
        "emotion_score": emotion.get("emotion_score"),
        "risk_level": emotion.get("risk_level", "UNKNOWN"),
        "confidence": emotion.get("confidence"),
        "strategy_bias": emotion.get("strategy_bias", ""),
        "dimensions": {
            "breadth": {"score": emotion.get("breadth_score"), "label": emotion.get("breadth_label", "")},
            "momentum": {"score": emotion.get("momentum_score"), "label": emotion.get("momentum_label", "")},
            "relay": {"score": emotion.get("relay_score"), "label": emotion.get("relay_label", "")},
            "capital": {"score": emotion.get("capital_score"), "label": emotion.get("capital_label", "")},
            "style": {"score": emotion.get("style_score"), "label": emotion.get("style_label", "")},
        },
        "analyst_adjustment": emotion.get("analyst_adjustment"),
        "key_evidence": emotion.get("key_evidence") or [],
    }


def _build_facts(charts: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract facts from snapshot chart_reviews[].key_metrics."""
    facts: dict[str, Any] = {}
    for chart in charts:
        ct = chart.get("chart_type", "")
        metrics = chart.get("key_metrics") or {}
        if ct == "market_breadth":
            facts["up_count"] = metrics.get("up_count")
            facts["down_count"] = metrics.get("down_count")
            facts["limit_up_total"] = metrics.get("limit_up_count")
            facts["limit_down_total"] = metrics.get("limit_down_count")
        elif ct == "active_capital":
            facts["active_amount_yi"] = metrics.get("active_amount_yi")
            facts["total_amount_yi"] = _positive_number(metrics.get("total_amount_yi"))
        elif ct == "relay_ecology":
            facts["max_board_height"] = metrics.get("max_board_height")
            facts["promotion_1_to_2"] = metrics.get("promotion_1_to_2")
            facts["feedback_score"] = metrics.get("feedback_score")
    return {k: v for k, v in facts.items() if v is not None}


def _positive_number(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if value > 0 else None
    return value


def _build_relay_summary(charts: list[dict[str, Any]]) -> dict[str, Any]:
    max_board_height = 0
    promotion_rate = None
    for chart in charts:
        ct = chart.get("chart_type", "")
        metrics = chart.get("key_metrics") or {}
        if ct == "relay_ecology":
            max_board_height = metrics.get("max_board_height") or 0
            promotion_rate = metrics.get("promotion_1_to_2")
            break
    return {
        "max_board_height": max_board_height,
        "ladder_shape": "完整" if max_board_height >= 3 else ("断层" if max_board_height > 0 else "无连板"),
        "promotion_rate": promotion_rate,
        "summary": "",
    }


def _build_new_high_brief(charts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"count": None, "yesterday_count": None, "direction": "", "summary": ""}


def _build_chart_summary(charts: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for chart in charts:
        ct = chart.get("chart_type", "")
        if ct:
            summary[ct] = {
                "title": chart.get("title", ""),
                "status": chart.get("status", ""),
                "score": chart.get("score"),
                "summary": chart.get("summary", ""),
            }
    return summary
