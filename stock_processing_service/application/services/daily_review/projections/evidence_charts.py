"""Evidence Charts projection — PR-S2.

Extracts normalized chart data from the same MarketMetrics source as
emotion_review, ensuring chart values are consistent with emotion text.

Replaces the need for ChartRenderer to fetch raw analyst-charts JSON.
"""

from __future__ import annotations

from typing import Any


def project_evidence_charts(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_chart_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build evidence_charts from approved sources.

    Sources (priority order):
      1. Snapshot emotion_review (analyst-approved values)
      2. Snapshot chart_reviews (ChartReviewBuilder structured output)
      3. Engine report (MarketMetrics-derived chart data)
    """
    emotion = snapshot_emotion or {}
    charts = snapshot_chart_reviews or []

    # ── market_breadth chart ──
    breadth = _build_breadth_chart(emotion, charts, engine_report)

    # ── emotion_momentum chart ──
    momentum = _build_momentum_chart(emotion, charts)

    # ── active_capital chart ──
    capital = _build_capital_chart(emotion, charts)

    # ── relay_ecology chart ──
    relay = _build_relay_chart(emotion, charts, engine_report)

    # ── institution_style chart ──
    institution = _find_chart(charts, "institution_style")

    # ── hot_money_style chart ──
    hot_money = _find_chart(charts, "hot_money_style")

    # ── limit_up classification ──
    limit_up = _build_limit_up_chart(engine_report)

    return {
        "market_breadth": breadth,
        "emotion_momentum": momentum,
        "active_capital": capital,
        "relay_ecology": relay,
        "institution_style": institution,
        "hot_money_style": hot_money,
        "limit_up_summary": limit_up,
    }


def _build_breadth_chart(
    emotion: dict, charts: list[dict], engine: dict,
) -> dict[str, Any]:
    """Build market breadth chart normalized to emotion data source."""
    chart = _find_chart(charts, "market_breadth") or {}
    metrics = chart.get("key_metrics") or {}

    # Use emotion raw data (same source as emotion text) for consistency
    raw = emotion.get("raw") or {}
    breadth_key_evidence = emotion.get("key_evidence") or []

    # Detect degraded breadth
    up_count = raw.get("up_count", metrics.get("up_count"))
    down_count = raw.get("down_count", metrics.get("down_count"))
    breadth_degraded = (up_count == 0 and down_count == 0)

    return {
        "up_count": up_count,
        "down_count": down_count,
        "limit_up_count": raw.get("limit_up", metrics.get("limit_up_count")),
        "limit_down_count": raw.get("limit_down", metrics.get("limit_down_count")),
        "status": chart.get("status", ""),
        "summary": chart.get("summary", ""),
        "breadth_degraded": breadth_degraded,
        "source": "market_metrics" if not breadth_degraded else "degraded",
    }


def _build_momentum_chart(emotion: dict, charts: list[dict]) -> dict[str, Any]:
    """Build emotion momentum chart."""
    chart = _find_chart(charts, "emotion_momentum") or {}
    metrics = chart.get("key_metrics") or {}
    return {
        "momentum_score": emotion.get("momentum_score"),
        "momentum_label": emotion.get("momentum_label", ""),
        "first_board_red_ratio": metrics.get("first_board_red_ratio"),
        "chain_board_big_loss_ratio": metrics.get("chain_board_big_loss_ratio"),
        "status": chart.get("status", ""),
        "summary": chart.get("summary", ""),
    }


def _build_capital_chart(emotion: dict, charts: list[dict]) -> dict[str, Any]:
    """Build active capital chart."""
    chart = _find_chart(charts, "active_capital") or {}
    metrics = chart.get("key_metrics") or {}
    return {
        "active_amount_yi": metrics.get("active_amount_yi"),
        "total_amount_yi": metrics.get("total_amount_yi"),
        "active_ratio": None,
        "status": chart.get("status", ""),
        "summary": chart.get("summary", ""),
    }


def _build_relay_chart(
    emotion: dict, charts: list[dict], engine: dict,
) -> dict[str, Any]:
    """Build relay ecology chart."""
    chart = _find_chart(charts, "relay_ecology") or {}
    metrics = chart.get("key_metrics") or {}
    ladder = engine.get("limit_up_ladder") or {}
    return {
        "max_board_height": metrics.get("max_board_height"),
        "promotion_1_to_2": metrics.get("promotion_1_to_2"),
        "promotion_2_to_3": metrics.get("promotion_2_to_3"),
        "feedback_score": metrics.get("feedback_score"),
        "feedback_label": metrics.get("feedback_label", ""),
        "status": chart.get("status", ""),
        "summary": chart.get("summary", ""),
        "yesterday_limit_up": ladder.get("yesterday_limit_up_count"),
    }


def _build_limit_up_chart(engine: dict) -> dict[str, Any]:
    """Build limit-up classification summary."""
    ladder = engine.get("limit_up_ladder") or {}
    return {
        "summary": ladder.get("summary", ""),
        "theme_rows": ladder.get("theme_rows") or [],
        "board_rows": ladder.get("board_rows") or [],
    }


def _find_chart(charts: list[dict], chart_type: str) -> dict[str, Any] | None:
    for c in charts:
        if c.get("chart_type") == chart_type:
            return c
    return None
