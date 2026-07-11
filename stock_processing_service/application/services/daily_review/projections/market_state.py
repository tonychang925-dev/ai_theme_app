"""Market State projection.

Merges market_regime_review + emotion_review + market_overview_review
+ index_technical_reviews + chart_reviews + limit_up_ladder + new_high_summary.

Key rules:
  - market_health_score and emotion_score are SEPARATE (different dimensions)
  - Each FACT field has a unique Owner Producer (no multi-source fallback)
  - relay_summary (ladder summary) stays in formal report, full ladder in appendix
  - new_high_brief stays in formal report, full details in appendix
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import resolve_fact


def project_market_state(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_chart_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the market_state block.

    Args:
        engine_report: Full engine report from PostMarketEngineReportComposer.
        snapshot_emotion: emotion_review from approved ReviewSnapshot.
        snapshot_chart_reviews: chart_reviews from approved ReviewSnapshot.

    Returns:
        market_state dict.
    """
    emotion = snapshot_emotion or {}
    charts = snapshot_chart_reviews or []

    # ── regime ──
    regime = _build_regime(engine_report)

    # ── emotion ──
    emotion_block = _build_emotion_block(emotion)

    # ── facts (unique owner per FACT field) ──
    facts = _build_facts(engine_report, charts)

    # ── market_health_score (separate from emotion_score!) ──
    market_health_score = _extract_market_health_score(engine_report)

    # ── emotion_score ──
    emotion_score = emotion.get("emotion_score")

    # ── fade_status ──
    fade_status = _extract_fade_status(engine_report)

    # ── relay_summary ──
    relay_summary = _build_relay_summary(engine_report, charts)

    # ── new_high_brief ──
    new_high_brief = _build_new_high_brief(engine_report)

    # ── index_technical ──
    index_technical = engine_report.get("index_technical_reviews") or []

    # ── chart_summary (5-dim summary from chart_reviews) ──
    chart_summary = _build_chart_summary(charts)

    # ── summary text ──
    summary = _build_summary_text(engine_report, emotion)

    return {
        "regime": regime,
        "emotion": emotion_block,
        "facts": facts,
        "market_health_score": market_health_score,
        "emotion_score": emotion_score,
        "fade_status": fade_status,
        "relay_summary": relay_summary,
        "new_high_brief": new_high_brief,
        "index_technical": index_technical,
        "chart_summary": chart_summary,
        "summary": summary,
    }


# ── private helpers ──


def _build_regime(engine_report: dict[str, Any]) -> dict[str, Any]:
    """Extract market regime from engine_report."""
    regime_review = engine_report.get("market_regime_review") or {}
    return {
        "broad_market_regime": regime_review.get("broad_market_regime", ""),
        "short_term_sentiment": regime_review.get("short_term_sentiment", ""),
        "mainline_environment": regime_review.get("mainline_environment", ""),
        "allow_trade": regime_review.get("allow_trade", False),
        "trade_mode": regime_review.get("trade_mode", ""),
        "position_limit": regime_review.get("position_limit"),
        "no_trade_reasons": regime_review.get("no_trade_reasons") or [],
    }


def _build_emotion_block(emotion: dict[str, Any]) -> dict[str, Any]:
    """Build the emotion sub-block from emotion_review."""
    return {
        "emotion_node": emotion.get("emotion_node", ""),
        "emotion_label": emotion.get("emotion_label", ""),
        "emotion_score": emotion.get("emotion_score"),
        "risk_level": emotion.get("risk_level", "UNKNOWN"),
        "confidence": emotion.get("confidence"),
        "strategy_bias": emotion.get("strategy_bias", ""),
        "dimensions": {
            "breadth": {
                "score": emotion.get("breadth_score"),
                "label": emotion.get("breadth_label", ""),
            },
            "momentum": {
                "score": emotion.get("momentum_score"),
                "label": emotion.get("momentum_label", ""),
            },
            "relay": {
                "score": emotion.get("relay_score"),
                "label": emotion.get("relay_label", ""),
            },
            "capital": {
                "score": emotion.get("capital_score"),
                "label": emotion.get("capital_label", ""),
            },
            "style": {
                "score": emotion.get("style_score"),
                "label": emotion.get("style_label", ""),
            },
        },
        "analyst_adjustment": emotion.get("analyst_adjustment"),
        "key_evidence": emotion.get("key_evidence") or [],
    }


def _build_facts(
    engine_report: dict[str, Any],
    charts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the facts block from snapshot chart_reviews (primary) and engine_report (fallback).

    Snapshot chart_reviews are the approved data source from the workbench.
    Engine report fields are secondary when snapshot data is unavailable.
    """
    facts: dict[str, Any] = {}

    # Primary: extract from chart_reviews (from approved snapshot)
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
            facts["total_amount_yi"] = metrics.get("total_amount_yi")
        elif ct == "relay_ecology":
            facts["max_board_height"] = metrics.get("max_board_height")
            facts["promotion_1_to_2"] = metrics.get("promotion_1_to_2")
            facts["feedback_score"] = metrics.get("feedback_score")

    # Fallback: engine_report market_overview_review
    overview = engine_report.get("market_overview_review") or {}
    for key in ("up_count", "down_count", "limit_up_total", "limit_down_total", "total_amount"):
        if key not in facts or facts[key] is None:
            val = overview.get(key)
            if val is not None:
                facts[key] = val

    # Remove None values
    return {k: v for k, v in facts.items() if v is not None}


def _extract_market_health_score(engine_report: dict[str, Any]) -> float | None:
    """Extract market health score from engine_report.

    The market_health_score is separate from emotion_score.
    Source: market_environment_review or market_summary.
    """
    env = engine_report.get("market_environment_review") or {}
    if "market_score" in env:
        return env["market_score"]
    ms = engine_report.get("market_summary") or {}
    return ms.get("market_health_score")


def _extract_fade_status(engine_report: dict[str, Any]) -> str:
    """Extract intraday fade status."""
    ms = engine_report.get("market_summary") or {}
    return ms.get("intraday_fade_status") or ""


def _build_relay_summary(
    engine_report: dict[str, Any],
    charts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build relay/ladder summary from limit_up_ladder + chart reviews.

    relay_summary stays in formal report; full ladder goes to evidence_appendix.
    """
    ladder = engine_report.get("limit_up_ladder") or {}
    board_rows = ladder.get("board_rows") or []

    max_board_height = 0
    for row in board_rows:
        bc = row.get("board_count", 0)
        if isinstance(bc, (int, float)) and bc > max_board_height:
            max_board_height = int(bc)

    # Compute promotion rate from chart_reviews relay_ecology
    promotion_rate = None
    for chart in charts:
        if chart.get("chart_type") == "relay_ecology":
            metrics = chart.get("key_metrics") or {}
            promotion_rate = metrics.get("promotion_1_to_2")
            break

    # Determine ladder shape
    ladder_shape = "完整"
    if max_board_height >= 5:
        ladder_shape = "完整"
    elif max_board_height == 0:
        ladder_shape = "无连板"
    elif max_board_height <= 2:
        ladder_shape = "断层"

    return {
        "max_board_height": max_board_height,
        "ladder_shape": ladder_shape,
        "promotion_rate": promotion_rate,
        "summary": ladder.get("summary", ""),
    }


def _build_new_high_brief(engine_report: dict[str, Any]) -> dict[str, Any]:
    """Build new_high brief from engine_report.

    Brief stays in formal report; full details go to evidence_appendix.
    """
    nh = engine_report.get("new_high_summary") or {}
    industries = nh.get("industry_summary") or []

    # Determine direction from industry names
    directions: list[str] = []
    for ind in industries[:4]:
        name = ind.get("industry_name", "")
        if name and name != "未分类":
            directions.append(name)

    return {
        "count": nh.get("today_count"),
        "yesterday_count": nh.get("yesterday_count"),
        "direction": " / ".join(directions) if directions else "",
        "summary": nh.get("summary", ""),
    }


def _build_chart_summary(charts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a 5-dim chart summary from the 6 chart reviews.

    Maps chart_type → {status, score, summary}.
    """
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


def _build_summary_text(
    engine_report: dict[str, Any],
    emotion: dict[str, Any],
) -> str:
    """Build a human-readable market state summary."""
    # Prefer emotion_review summary
    es = emotion.get("summary", "")
    if es:
        return es
    # Fall back to engine market_overview_narrative
    narrative = engine_report.get("market_overview_narrative") or {}
    return narrative.get("market_state_summary") or ""
