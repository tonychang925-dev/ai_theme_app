"""Executive Summary projection.

Merges engine_summary + emotion_review + narrative + mainline_daily_states
into a single executive summary block.

Key rules:
  - main_story comes from narrative_review, NOT emotion_review.summary
    (they have different semantics: "why" vs "what")
  - risk_level and top_risks are SEPARATE fields
    (risk_level = single label, top_risks = list of flag strings)
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import (
    FieldClass,
    first_non_null,
    first_override_value,
    resolve_assessment,
)


def project_executive_summary(
    *,
    engine_report: dict[str, Any],
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_narrative: dict[str, Any] | None = None,
    snapshot_cognition_cards: list[dict[str, Any]] | None = None,
    theme_reviews: list[dict[str, Any]] | None = None,
    name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the executive_summary block.

    Sources (in priority order for ASSESSMENT):
      1. Analyst override (from cognition_cards)
      2. Approved AI snapshot (emotion_review, narrative)
      3. Engine report (engine_summary, mainline_daily_states)

    Args:
        engine_report: Full engine report from PostMarketEngineReportComposer.
        snapshot_emotion: emotion_review from approved ReviewSnapshot.
        snapshot_narrative: narrative from approved ReviewSnapshot.
        snapshot_cognition_cards: cognition_cards from approved ReviewSnapshot.

    Returns:
        executive_summary dict.
    """
    emotion = snapshot_emotion or {}
    narrative = snapshot_narrative or {}
    cards = snapshot_cognition_cards or []

    engine_summary = engine_report.get("engine_summary") or {}
    mainline_states = engine_report.get("mainline_daily_states") or []

    # ── market_conclusion ──
    # Analyst override > engine_summary.conclusion > emotion_review.summary
    market_conclusion = resolve_assessment(
        analyst_value=first_override_value(cards, "stage_judgement"),
        ai_value=emotion.get("summary"),
        engine_value=engine_summary.get("conclusion"),
    ) or ""

    # ── main_story ──
    # narrative.main_story ("why the market evolved this way")
    # NOT emotion_review.summary ("what the emotional state is")
    # These have different semantics per Matrix v2.0 review
    main_story = first_non_null(
        narrative.get("main_story"),
        narrative.get("emotion_desc"),
        engine_report.get("market_overview_narrative", {}).get("headline"),
    ) or ""

    # ── primary_theme ──
    # Analyst override > mainline_daily_states[0] > cognition_cards top attention
    primary_theme = ""
    analyst_theme = first_override_value(cards, "stage_judgement")
    if analyst_theme:
        primary_theme = _extract_subject_name(cards, analyst_theme) or analyst_theme
    if not primary_theme and mainline_states:
        primary_theme = mainline_states[0].get("mainline_name", "")
    if not primary_theme and cards:
        top_card = _top_attention_card(cards)
        if top_card:
            name = top_card.get("subject_name", "")
            # subject_name may be a numeric subject_key — resolve from
            # theme_reviews if available (populated by DerivedRecapDocReader)
            primary_theme = _resolve_theme_name(name, theme_reviews or [], name_map or {})

    # ── secondary_themes ──
    secondary_themes: list[str] = []
    for ms in mainline_states[1:4]:
        name = ms.get("mainline_name", "")
        if name and name != primary_theme:
            secondary_themes.append(name)
    # Also include high-attention cognition cards not already covered
    for card in cards:
        sn = card.get("subject_name", "")
        if sn and sn != primary_theme and sn not in secondary_themes:
            al = card.get("attention_level", "")
            if al in ("CRITICAL", "HIGH"):
                secondary_themes.append(sn)
        if len(secondary_themes) >= 3:
            break

    # ── trade_mode ──
    trade_mode = resolve_assessment(
        analyst_value=None,  # analyst doesn't typically override trade_mode
        ai_value=emotion.get("strategy_bias"),
        engine_value=engine_summary.get("action_bias"),
    ) or ""

    # ── risk_level ──
    # From emotion_review (single label: LOW/MEDIUM/HIGH/EXTREME)
    risk_level = emotion.get("risk_level") or "UNKNOWN"

    # ── top_risks ──
    # From multiple sources: emotion_review key_evidence + market_summary.risk_flags
    top_risks: list[str] = []
    key_evidence = emotion.get("key_evidence") or []
    if isinstance(key_evidence, list):
        for e in key_evidence:
            if isinstance(e, str) and e:
                top_risks.append(e)
    # Add risk flags from engine market_summary
    market_summary = engine_report.get("market_summary") or {}
    risk_flags = market_summary.get("risk_flags") or []
    if isinstance(risk_flags, list):
        for rf in risk_flags:
            if isinstance(rf, str) and rf and rf not in top_risks:
                top_risks.append(rf)
    # Emotion tomorrow_forbidden can indicate risks
    forbidden = emotion.get("tomorrow_forbidden") or []
    if isinstance(forbidden, list):
        for f in forbidden:
            if isinstance(f, str) and f:
                prefix = "禁止: "
                if not f.startswith(prefix):
                    f = prefix + f
                if f not in top_risks:
                    top_risks.append(f)

    # ── engine_conclusion ──
    engine_conclusion = engine_summary.get("conclusion") or ""

    return {
        "market_conclusion": market_conclusion,
        "main_story": main_story,
        "primary_theme": primary_theme,
        "secondary_themes": secondary_themes,
        "trade_mode": trade_mode,
        "risk_level": risk_level,
        "top_risks": top_risks,
        "engine_conclusion": engine_conclusion,
    }


def _top_attention_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the cognition card with highest attention_score."""
    best: dict[str, Any] | None = None
    best_score = -1
    for card in cards:
        score = card.get("attention_score", 0)
        if isinstance(score, (int, float)) and score > best_score:
            best_score = score
            best = card
    return best


def _extract_subject_name(cards: list[dict[str, Any]], match_value: str) -> str | None:
    """Given a final_value like 'PCB成为资金承接方向', find the subject_name."""
    for card in cards:
        for key, val in card.items():
            if isinstance(val, dict) and val.get("final_value") == match_value:
                return card.get("subject_name")
    return None


def _resolve_theme_name(
    raw: str,
    theme_reviews: list[dict[str, Any]],
    name_map: dict[str, str],
) -> str:
    """Resolve a numeric subject_key to its Chinese display name."""
    if not raw:
        return ""
    # If already a Chinese name, return as-is
    if not raw.isdigit():
        return raw
    # Try name_map first
    if name_map and raw in name_map:
        return name_map[raw]
    # Try theme_reviews
    for tr in theme_reviews:
        sk = str(tr.get("subject_key", ""))
        tn = str(tr.get("theme_name", ""))
        if sk == raw and tn and not tn.isdigit():
            return tn
    return raw
