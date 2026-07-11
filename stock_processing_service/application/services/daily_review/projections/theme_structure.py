"""Theme Structure projection — PR2.2a.

Implements Subject Union merge across 5+ theme data sources:

  subject_keys = union(
      theme_reviews,
      theme_capital_reviews,
      mainline_daily_states,
      theme_driver_events,
      cognition_cards,
  )

For each unique subject_key, compile a single theme entry with:
  - role, stage, state_evolution (from engine + builder)
  - capital (from theme_capital_reviews)
  - drivers (from theme_driver_events)
  - analyst_view (from cognition_cards dual-track overrides)

ASSESSMENT merge policy: Analyst final_value > Approved AI > Engine > Builder
FACT merge policy: Primary source only (theme_capital_reviews for capital, etc.)
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import (
    explicit_field_override,
    first_non_null,
    override_final_value,
    normalize_subject_identity,
    resolve_assessment,
    resolve_fact,
    resolve_identity_override_for_subject,
)


def project_theme_structure(
    *,
    engine_report: dict[str, Any],
    snapshot_cognition_cards: list[dict[str, Any]] | None = None,
    builder_theme_reviews: list[dict[str, Any]] | None = None,
    builder_theme_capital_reviews: list[dict[str, Any]] | None = None,
    theme_name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the theme_structure block via Subject Union.

    Args:
        engine_report: Full engine report (has mainline_daily_states, theme_driver_events).
        snapshot_cognition_cards: cognition_cards from approved ReviewSnapshot.
        builder_theme_reviews: theme_reviews from PostMarketDailyReviewV2Builder.
        builder_theme_capital_reviews: theme_capital_reviews from builder.
        theme_name_map: Subject key → display name lookup.

    Returns:
        {summary: {mainline_narrative, rotation_summary}, themes: [...]}
    """
    cards = snapshot_cognition_cards or []
    theme_reviews = builder_theme_reviews or []
    theme_cap_reviews = builder_theme_capital_reviews or []
    mainline_states = engine_report.get("mainline_daily_states") or []
    driver_events_list = engine_report.get("theme_driver_events") or []
    name_map = theme_name_map or {}

    # ── Step 1: Build lookup indexes ──
    theme_by_key: dict[str, dict[str, Any]] = {}
    for tr in theme_reviews:
        sk = str(tr.get("subject_key", ""))
        if sk:
            theme_by_key[sk] = tr

    capital_by_key: dict[str, dict[str, Any]] = {}
    for tc in theme_cap_reviews:
        sk = str(tc.get("subject_key", ""))
        if sk:
            capital_by_key[sk] = tc

    mainline_by_key: dict[str, dict[str, Any]] = {}
    for ml in mainline_states:
        sk = str(ml.get("canonical_subject_key", ""))
        if sk:
            mainline_by_key[sk] = ml

    drivers_by_key: dict[str, list[dict[str, Any]]] = {}
    for de in driver_events_list:
        sk = str(de.get("subject_key", ""))
        if sk:
            drivers_by_key[sk] = de.get("driver_events") or []

    # ── Step 2: Subject Union ──
    non_cognition_keys: set[str] = set()
    non_cognition_keys.update(theme_by_key.keys())
    non_cognition_keys.update(capital_by_key.keys())
    non_cognition_keys.update(mainline_by_key.keys())
    non_cognition_keys.update(drivers_by_key.keys())

    cognition_by_key: dict[str, dict[str, Any]] = {}
    cognition_subject_keys: set[str] = set()
    for card in cards:
        candidates = _card_subject_keys(card)
        if not candidates:
            continue
        for candidate in candidates:
            cognition_by_key[candidate] = card
            normalized = normalize_subject_identity(candidate)
            if normalized:
                cognition_by_key[normalized] = card
                cognition_by_key[f"theme:{normalized}"] = card
        cognition_subject_keys.add(_preferred_subject_key(candidates, non_cognition_keys))

    all_keys: set[str] = set()
    all_keys.update(theme_by_key.keys())
    all_keys.update(capital_by_key.keys())
    all_keys.update(mainline_by_key.keys())
    all_keys.update(drivers_by_key.keys())
    all_keys.update(cognition_subject_keys)

    # ── Step 3: Compile each theme ──
    themes: list[dict[str, Any]] = []
    for sk in sorted(all_keys):
        entry = _compile_theme(
            subject_key=sk,
            theme_row=theme_by_key.get(sk),
            capital_row=capital_by_key.get(sk),
            mainline_row=mainline_by_key.get(sk),
            driver_events=drivers_by_key.get(sk, []),
            cognition_card=cognition_by_key.get(sk),
            name_map=name_map,
        )
        if entry:
            themes.append(entry)

    # ── Summary ──
    mainline_narrative = ""
    mn = engine_report.get("mainline_narrative") or {}
    if isinstance(mn, dict):
        mainline_narrative = mn.get("summary", "")

    return {
        "summary": {
            "mainline_narrative": mainline_narrative,
            "rotation_summary": _build_rotation_summary(themes),
        },
        "themes": themes,
    }


# ── private helpers ──


def _card_subject_keys(card: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ("subject_id", "subject_key", "theme_key", "subject_name", "theme_name", "name"):
        value = str(card.get(field, "") or "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


def _preferred_subject_key(candidates: list[str], existing_keys: set[str]) -> str:
    """Choose the subject key that preserves existing source identity."""
    if not existing_keys:
        return candidates[0]

    by_normalized = {
        normalize_subject_identity(key): key
        for key in existing_keys
        if normalize_subject_identity(key)
    }
    for candidate in candidates:
        if candidate in existing_keys:
            return candidate
        normalized = normalize_subject_identity(candidate)
        if normalized in by_normalized:
            return by_normalized[normalized]
    return candidates[0]


def _compile_theme(
    *,
    subject_key: str,
    theme_row: dict[str, Any] | None,
    capital_row: dict[str, Any] | None,
    mainline_row: dict[str, Any] | None,
    driver_events: list[dict[str, Any]],
    cognition_card: dict[str, Any] | None,
    name_map: dict[str, str],
) -> dict[str, Any] | None:
    """Compile a single theme entry from all available sources."""

    # ── theme_name: priority resolution ──
    theme_name = ""
    # Analyst cognition card has subject_name
    if cognition_card:
        theme_name = str(cognition_card.get("subject_name", ""))
    # Engine mainline has mainline_name
    if not theme_name and mainline_row:
        theme_name = str(mainline_row.get("mainline_name", ""))
    # Builder theme_reviews has theme_name
    if not theme_name and theme_row:
        theme_name = str(theme_row.get("theme_name", ""))
    # Capital row
    if not theme_name and capital_row:
        theme_name = str(capital_row.get("theme_name", ""))
    # name_map fallback
    if not theme_name:
        theme_name = name_map.get(subject_key, subject_key)

    theme_name = resolve_identity_override_for_subject(
        card=cognition_card,
        subject_key=subject_key,
        field_name="subject_name",
        entity_value=theme_name,
    )

    # Filter noise keys
    if _is_noise_subject_key(subject_key, theme_name):
        return None

    # ── role: MAINLINE / SECONDARY / WATCH ──
    role = _resolve_role(theme_row, mainline_row, cognition_card)

    # ── stage ──
    stage = _resolve_stage(theme_row, mainline_row, cognition_card)

    # ── state_evolution ──
    state_evolution = _build_state_evolution(mainline_row, theme_row)

    # ── capital ──
    capital = _build_capital_block(capital_row, theme_row)

    # ── drivers ──
    drivers = _build_drivers_block(driver_events)

    # ── analyst_view ──
    analyst_view = _build_analyst_view(cognition_card, theme_row)

    return {
        "subject_key": subject_key,
        "theme_name": theme_name,
        "role": role,
        "stage": stage,
        "state_evolution": state_evolution,
        "capital": capital,
        "drivers": drivers,
        "analyst_view": analyst_view,
    }


def _is_noise_subject_key(subject_key: str, theme_name: str) -> bool:
    """Filter out noise/aggregate keys that aren't real themes."""
    if not subject_key or not subject_key.strip():
        return True
    # Pure numeric keys shorter than 4 digits are usually noise
    if subject_key.isdigit() and len(subject_key) < 4:
        return True
    # Garbage: text that is clearly not a theme name
    if theme_name and len(theme_name) > 30:
        return True
    if theme_name and ("【" in theme_name or "】" in theme_name):
        return True
    if theme_name and ("连板复盘" in theme_name or "行情报价" in theme_name):
        return True
    # Empty or code-like names
    if theme_name == subject_key and subject_key.isdigit():
        return False  # Keep pure numeric but real keys
    return False


def _resolve_role(
    theme_row: dict[str, Any] | None,
    mainline_row: dict[str, Any] | None,
    cognition_card: dict[str, Any] | None,
) -> str:
    """Resolve theme role: MAINLINE / SECONDARY / WATCH.

    Priority: mainline_daily_states.mainline_alive > theme_reviews.tier > cognition.attention_level
    """
    # Engine mainline state
    if mainline_row:
        alive = mainline_row.get("mainline_alive")
        trade_alive = mainline_row.get("mainline_trade_alive")
        if alive and trade_alive:
            return "MAINLINE"
        if alive:
            return "SECONDARY"

    # Builder tier
    if theme_row:
        tier = str(theme_row.get("tier", "")).lower()
        if tier in ("mainline", "confirmed"):
            return "MAINLINE"
        if tier in ("secondary", "watch_candidate"):
            return "SECONDARY"

    # Cognition attention level
    if cognition_card:
        al = str(cognition_card.get("attention_level", "")).upper()
        if al == "CRITICAL":
            return "MAINLINE"
        if al == "HIGH":
            return "SECONDARY"

    return "WATCH"


def _resolve_stage(
    theme_row: dict[str, Any] | None,
    mainline_row: dict[str, Any] | None,
    cognition_card: dict[str, Any] | None,
) -> str:
    """Resolve lifecycle stage.

    Priority: mainline_daily_states.lifecycle_state > cognition.stage_judgement
              > theme_reviews.final_cycle_state > theme_reviews.cycle_stage
    """
    # Engine mainline lifecycle
    if mainline_row:
        ls = mainline_row.get("lifecycle_state", "")
        if ls:
            return str(ls)

    # Analyst override (from cognition card stage_judgement)
    if cognition_card:
        sj = cognition_card.get("stage_judgement")
        if isinstance(sj, dict) and sj.get("override"):
            return str(sj.get("final_value", ""))

    # Builder
    if theme_row:
        fcs = theme_row.get("final_cycle_state", "")
        if fcs:
            return str(fcs)
        cs = theme_row.get("cycle_stage", "")
        if cs:
            return str(cs)

    return "unknown"


def _build_state_evolution(
    mainline_row: dict[str, Any] | None,
    theme_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build state_evolution from mainline_daily_states + theme_reviews.

    mainline_daily_states has unique data: fade_risk, alive status, strength score.
    These are NOT all in theme_reviews.
    """
    evo: dict[str, Any] = {}

    if mainline_row:
        evo["mainline_alive"] = mainline_row.get("mainline_alive")
        evo["mainline_trade_alive"] = mainline_row.get("mainline_trade_alive")
        evo["fade_risk_score"] = mainline_row.get("fade_risk_score")
        evo["mainline_strength_score"] = mainline_row.get("mainline_strength_score")
        evo["strong_pool_count"] = mainline_row.get("strong_pool_count", 0)
        evo["d1_count"] = mainline_row.get("d1_count", 0)
        evo["focus_count"] = mainline_row.get("focus_count", 0)
        evo["action_advice"] = mainline_row.get("action_advice", "")
        evo["conclusion"] = mainline_row.get("conclusion", "")
        evo["risk_state"] = mainline_row.get("risk_state")

    if theme_row:
        if "fade_risk_score" not in evo or evo["fade_risk_score"] is None:
            evo["fade_risk_score"] = theme_row.get("fade_risk_score")
        if "mainline_strength_score" not in evo or evo["mainline_strength_score"] is None:
            evo["mainline_strength_score"] = theme_row.get("mainline_strength_score")

    return evo


def _build_capital_block(
    capital_row: dict[str, Any] | None,
    theme_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build capital block. FACT data — primary source is theme_capital_reviews."""
    cap: dict[str, Any] = {}

    src = capital_row or theme_row or {}
    cap["total_inflow"] = src.get("total_inflow")
    cap["leader_inflow"] = src.get("leader_inflow")
    cap["top3_inflow"] = capital_row.get("top3_inflow") if capital_row else None
    cap["inflow_stock_count"] = capital_row.get("inflow_stock_count") if capital_row else None
    cap["rank_order"] = capital_row.get("rank_order") if capital_row else None
    cap["capital_validation"] = src.get("capital_validation", "")

    return {k: v for k, v in cap.items() if v is not None}


def _build_drivers_block(
    driver_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build drivers block from theme_driver_events."""
    drivers: list[dict[str, Any]] = []
    for de in driver_events:
        drivers.append({
            "event_id": de.get("event_id", ""),
            "summary": de.get("summary", ""),
            "event_time": de.get("event_time", ""),
            "confidence": de.get("confidence"),
            "match_reason": de.get("match_reason", ""),
        })
    return drivers


def _build_analyst_view(
    cognition_card: dict[str, Any] | None,
    theme_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build analyst_view from cognition_card dual-track overrides.

    Only includes fields where analyst explicitly overrode the AI value.
    """
    view: dict[str, Any] = {}
    if not cognition_card:
        return view

    # 12 dual-track fields from cognition cards
    override_fields = [
        "stage_judgement",
        "trading_style",
        "long_identifiability",
        "short_identifiability",
        "old_leaders",
        "yesterday_view",
        "today_actual",
        "intraday_understanding",
        "trader_sentiment",
        "index_resonance",
        "tomorrow_view",
        "analyst_notes",
    ]

    overrides: list[dict[str, Any]] = []
    subject_name_override = explicit_field_override(cognition_card, "subject_name")
    subject_name_final = override_final_value(subject_name_override)
    if subject_name_override and subject_name_final:
        overrides.append({
            "field": "subject_name",
            "ai_value": subject_name_override.get("ai_value", ""),
            "analyst_value": subject_name_override.get("analyst_value", ""),
            "final_value": subject_name_final,
            "reason": subject_name_override.get("reason", ""),
            "field_class": "IDENTITY",
        })

    for field in override_fields:
        val = cognition_card.get(field)
        if isinstance(val, dict) and val.get("override") is True:
            overrides.append({
                "field": field,
                "ai_value": val.get("ai_value", ""),
                "analyst_value": val.get("analyst_value", ""),
                "final_value": val.get("final_value", ""),
                "reason": val.get("reason", ""),
            })

    if overrides:
        view["overrides"] = overrides
        view["override_count"] = len(overrides)

    view["analyst_reviewed"] = cognition_card.get("analyst_reviewed", False)
    view["attention_level"] = cognition_card.get("attention_level", "")
    view["attention_score"] = cognition_card.get("attention_score")

    return view


def _build_rotation_summary(themes: list[dict[str, Any]]) -> str:
    """Build a rotation summary from the compiled theme list."""
    mainlines = [t for t in themes if t.get("role") == "MAINLINE"]
    secondaries = [t for t in themes if t.get("role") == "SECONDARY"]
    watches = [t for t in themes if t.get("role") == "WATCH"]

    parts: list[str] = []
    if mainlines:
        names = ", ".join(t["theme_name"] for t in mainlines[:3])
        parts.append(f"主线: {names}")
    if secondaries:
        names = ", ".join(t["theme_name"] for t in secondaries[:3])
        parts.append(f"支线: {names}")
    if not parts:
        return ""

    return "；".join(parts)
