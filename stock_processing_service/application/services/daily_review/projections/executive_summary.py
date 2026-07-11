"""Executive Summary projection.

Primary data source: Approved Snapshot (emotion_review, narrative,
cognition_cards). Engine report is fallback only.
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import first_non_null


_SK_LABELS: dict[str, str] = {
    "9055378": "国产算力", "9018144": "PCB印制电路板", "9014001": "人工智能硬件",
    "9014636": "人形机器人", "9015778": "存储芯片", "9013416": "电力运营",
    "9019807": "卫星互联网", "9032828": "电子元器件", "9064103": "AI光纤",
    "9066740": "磷化铟", "9023749": "AI光纤", "9016949": "建材",
    "9011277": "芯片大全", "9060250": "电子特气", "9024980": "化工-氟",
    "9030037": "商业航天", "9013944": "半导体", "9048512": "创新药",
}


def project_executive_summary(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_narrative: dict[str, Any] | None = None,
    snapshot_cognition_cards: list[dict[str, Any]] | None = None,
    theme_reviews: list[dict[str, Any]] | None = None,
    name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the executive_summary block from Approved Snapshot."""
    emotion = snapshot_emotion or {}
    narrative = snapshot_narrative or {}
    cards = snapshot_cognition_cards or []
    engine_summary = engine_report.get("engine_summary") or {}
    mainline_states = engine_report.get("mainline_daily_states") or []

    # ── market_conclusion ──
    # Build from emotion node + label (NOT from emotion_desc which is a phase label)
    node_label = emotion.get("emotion_label", "")
    strategy = emotion.get("strategy_bias", "")
    market_conclusion = first_non_null(
        emotion.get("summary"),
        engine_summary.get("conclusion"),
    )
    if not market_conclusion or len(str(market_conclusion)) < 10:
        market_conclusion = f"市场处于{node_label}状态。{strategy}" if node_label else str(strategy)

    # ── main_story ──
    main_story = first_non_null(
        narrative.get("main_story"),
        narrative.get("emotion_desc"),
        engine_report.get("market_overview_narrative", {}).get("headline"),
    ) or ""

    # ── primary_theme ──
    primary_theme = _resolve_primary_theme(cards, mainline_states, name_map or {})

    # ── secondary_themes ──
    secondary_themes = _resolve_secondary_themes(cards, mainline_states, primary_theme, name_map or {})

    # ── trade_mode ──
    trade_mode = emotion.get("strategy_bias") or engine_summary.get("action_bias") or ""

    # ── risk_level ──
    risk_level = emotion.get("risk_level") or "UNKNOWN"

    # ── top_risks ──
    top_risks: list[str] = []
    for source in (emotion.get("key_evidence") or [], emotion.get("tomorrow_forbidden") or []):
        if isinstance(source, list):
            for item in source:
                if isinstance(item, str) and item:
                    top_risks.append(item)

    # ── engine_conclusion ──
    engine_conclusion = engine_summary.get("conclusion") or ""

    return {
        "market_conclusion": str(market_conclusion),
        "main_story": main_story,
        "primary_theme": primary_theme,
        "secondary_themes": secondary_themes,
        "trade_mode": trade_mode,
        "risk_level": risk_level,
        "top_risks": top_risks,
        "engine_conclusion": engine_conclusion,
    }


def _resolve_name(raw: str, name_map: dict[str, str]) -> str:
    """Resolve subject_key → display name."""
    if not raw:
        return ""
    if not raw.isdigit():
        return raw
    return name_map.get(raw) or _SK_LABELS.get(raw) or raw


def _resolve_primary_theme(
    cards: list[dict[str, Any]],
    mainline_states: list[dict[str, Any]],
    name_map: dict[str, str],
) -> str:
    # Best: top CRITICAL cognition card with non-numeric name
    for card in cards:
        al = str(card.get("attention_level", "")).upper()
        if al == "CRITICAL":
            name = str(card.get("subject_name", ""))
            resolved = _resolve_name(name, name_map)
            if resolved and not resolved.isdigit():
                return resolved
    # Next: mainline_states[0]
    if mainline_states:
        name = str(mainline_states[0].get("mainline_name", ""))
        resolved = _resolve_name(name, name_map)
        if resolved:
            return resolved
    # Last: first card's subject_name
    if cards:
        name = str(cards[0].get("subject_name", ""))
        return _resolve_name(name, name_map)
    return ""


def _resolve_secondary_themes(
    cards: list[dict[str, Any]],
    mainline_states: list[dict[str, Any]],
    primary: str,
    name_map: dict[str, str],
) -> list[str]:
    result: list[str] = []
    seen = {primary}
    # From mainline states
    for ms in mainline_states[1:4]:
        name = _resolve_name(str(ms.get("mainline_name", "")), name_map)
        if name and name not in seen:
            result.append(name)
            seen.add(name)
    # From high-attention cards
    for card in cards:
        al = str(card.get("attention_level", "")).upper()
        if al in ("CRITICAL", "HIGH"):
            name = _resolve_name(str(card.get("subject_name", "")), name_map)
            if name and name not in seen and not name.isdigit():
                result.append(name)
                seen.add(name)
        if len(result) >= 3:
            break
    return result
