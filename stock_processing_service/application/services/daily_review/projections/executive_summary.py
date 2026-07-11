"""Executive Summary projection.

Primary data source: Approved Snapshot (emotion_review, narrative,
cognition_cards). Engine report is fallback only.

NO hardcoded business knowledge — all identity resolution goes through
the ThemeIdentityResolver.
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import first_non_null


def project_executive_summary(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_narrative: dict[str, Any] | None = None,
    snapshot_cognition_cards: list[dict[str, Any]] | None = None,
    identity: Any = None,  # ThemeIdentityResolver
) -> dict[str, Any]:
    """Build the executive_summary block from Approved Snapshot."""
    emotion = snapshot_emotion or {}
    narrative = snapshot_narrative or {}
    cards = snapshot_cognition_cards or []
    engine_summary = engine_report.get("engine_summary") or {}
    mainline_states = engine_report.get("mainline_daily_states") or []

    # ── market_conclusion ──
    # From snapshot: emotion_review.summary (structured by EmotionReviewBuilder).
    # Compiler does NOT generate new narrative — it projects existing data.
    market_conclusion = first_non_null(
        emotion.get("summary"),
        engine_summary.get("conclusion"),
    ) or ""

    # ── main_story ──
    main_story = first_non_null(
        narrative.get("main_story"),
        narrative.get("emotion_desc"),
        engine_report.get("market_overview_narrative", {}).get("headline"),
    ) or ""

    # ── primary_theme ──
    primary_theme = _resolve_primary_theme(cards, mainline_states, identity)

    # ── secondary_themes ──
    secondary_themes = _resolve_secondary_themes(cards, mainline_states, primary_theme, identity)

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


def _resolve_name(raw: str, identity: Any) -> str:
    """Resolve subject_key → display name via ThemeIdentityResolver."""
    if not raw:
        return ""
    if identity is not None:
        return identity.resolve(raw)
    return raw


def _resolve_primary_theme(
    cards: list[dict[str, Any]],
    mainline_states: list[dict[str, Any]],
    identity: Any,
) -> str:
    # Best: top CRITICAL cognition card with non-numeric name
    for card in cards:
        al = str(card.get("attention_level", "")).upper()
        if al == "CRITICAL":
            name = str(card.get("subject_name", ""))
            resolved = _resolve_name(name, identity)
            if resolved and not resolved.isdigit():
                return resolved
    # Next: mainline_states[0]
    if mainline_states:
        name = str(mainline_states[0].get("mainline_name", ""))
        resolved = _resolve_name(name, identity)
        if resolved:
            return resolved
    # Last: first card's subject_name
    if cards:
        name = str(cards[0].get("subject_name", ""))
        return _resolve_name(name, identity)
    return ""


def _resolve_secondary_themes(
    cards: list[dict[str, Any]],
    mainline_states: list[dict[str, Any]],
    primary: str,
    identity: Any,
) -> list[str]:
    result: list[str] = []
    seen = {primary}
    for ms in mainline_states[1:4]:
        name = _resolve_name(str(ms.get("mainline_name", "")), identity)
        if name and name not in seen and not name.isdigit():
            result.append(name)
            seen.add(name)
    for card in cards:
        al = str(card.get("attention_level", "")).upper()
        if al in ("CRITICAL", "HIGH"):
            name = _resolve_name(str(card.get("subject_name", "")), identity)
            if name and name not in seen and not name.isdigit():
                result.append(name)
                seen.add(name)
        if len(result) >= 3:
            break
    return result
