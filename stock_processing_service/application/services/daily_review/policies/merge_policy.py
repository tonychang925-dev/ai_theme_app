"""Field-level merge policy for FormalReviewProjectionCompiler.

Enforces the constitutional merge rules:

    FACT:
      Primary source only. Human override forbidden.
      Example: 涨停数、成交额、上涨家数

    ASSESSMENT:
      Analyst final_value > Approved AI conclusion > Engine Assessment > Legacy

    PLAN:
      Analyst final_value > Approved playbook > Engine plan > Legacy

    IDENTITY:
      Analyst explicit identity override > AI/entity identity.
      Example: subject_name "人形机器人" → "PCB"

    AUDIT:
      Append only. Never overwrite.

All resolve_* functions return the resolved value — they do NOT modify input dicts.
"""

from __future__ import annotations

from typing import Any


class FieldClass:
    FACT = "FACT"
    IDENTITY = "IDENTITY"
    ASSESSMENT = "ASSESSMENT"
    PLAN = "PLAN"
    AUDIT = "AUDIT"


def resolve_fact(primary: Any, *fallbacks: Any) -> Any:
    """Resolve a FACT field.

    Primary source only. Falls back only if primary is None/missing.
    Human override is FORBIDDEN for FACT fields.
    """
    if primary is not None and primary != "":
        return primary
    for fb in fallbacks:
        if fb is not None and fb != "":
            return fb
    return primary


def resolve_assessment(
    analyst_value: Any = None,
    ai_value: Any = None,
    engine_value: Any = None,
    legacy_value: Any = None,
) -> Any:
    """Resolve an ASSESSMENT field.

    Priority: Analyst final_value > Approved AI > Engine > Legacy
    """
    for val in (analyst_value, ai_value, engine_value, legacy_value):
        if val is not None and val != "" and val != [] and val != {}:
            return val
    return None


def resolve_plan(
    analyst_value: Any = None,
    playbook_value: Any = None,
    engine_value: Any = None,
    legacy_value: Any = None,
) -> Any:
    """Resolve a PLAN field.

    Priority: Analyst final_value > Approved playbook > Engine plan > Legacy
    """
    for val in (analyst_value, playbook_value, engine_value, legacy_value):
        if val is not None and val != "" and val != [] and val != {}:
            return val
    return None


def resolve_identity(
    *,
    entity_value: Any = None,
    override: dict[str, Any] | None = None,
) -> Any:
    """Resolve an IDENTITY field.

    Identity fields name or key the business entity itself. They are not FACT
    fields, but they also should not be inferred from legacy fallbacks. Only an
    explicit analyst override is allowed to replace the AI/entity value.
    """
    final_value = override_final_value(override)
    if final_value is not None and final_value != "":
        return final_value
    return entity_value


def resolve_audit(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge audit data. Append only, never overwrite existing keys."""
    merged = dict(existing)
    for k, v in incoming.items():
        if k not in merged:
            merged[k] = v
    return merged


def first_non_null(*values: Any) -> Any:
    """Return the first non-None, non-empty value."""
    for v in values:
        if v is not None and v != "" and v != [] and v != {}:
            return v
    return None


def pick_override_final(
    ai_value: Any,
    analyst_value: Any | None = None,
    override: bool = False,
) -> Any:
    """Pick final_value from a dual-track override field.

    Returns (final_value, source) tuple.
    source is one of: "analyst", "ai", "none"
    """
    if override and analyst_value is not None and analyst_value != "":
        return analyst_value, "analyst"
    if ai_value is not None and ai_value != "":
        return ai_value, "ai"
    return None, "none"


def extract_override_field(
    card: dict[str, Any],
    field_name: str,
) -> dict[str, Any] | None:
    """Extract a dual-track override field from a cognition card.

    Cards store overrides as:
      {"field": "stage_judgement", "ai_value": "...", "analyst_value": "...",
       "final_value": "...", "override": true, "reason": "..."}

    Returns the override dict if it exists and override=True, else None.
    """
    val = card.get(field_name)
    if isinstance(val, dict) and val.get("override") is True:
        return val
    return None


def first_override_value(
    cards: list[dict[str, Any]],
    field_name: str,
) -> str | None:
    """Scan cognition_cards for the first override of field_name.

    Returns the analyst_value of the first card with override=True for this field.
    """
    for card in cards:
        override = extract_override_field(card, field_name)
        if override:
            return override.get("analyst_value") or override.get("final_value")
    return None


def first_override_by_subject(
    cards: list[dict[str, Any]],
    field_name: str,
    subject_key: str | None = None,
) -> str | None:
    """Scan cognition_cards for the first override of field_name, optionally filtered by subject."""
    for card in cards:
        if subject_key and card.get("subject_id") != subject_key:
            continue
        override = extract_override_field(card, field_name)
        if override:
            return override.get("analyst_value") or override.get("final_value")
    return None


def normalize_subject_identity(value: Any) -> str:
    """Normalize subject identifiers for exact identity matching."""
    text = str(value or "").strip()
    if text.startswith("theme:"):
        return text.removeprefix("theme:")
    return text


def subject_identity_matches(card: dict[str, Any], subject_key: str | None) -> bool:
    """Return True when a cognition card refers to the projection subject."""
    if not subject_key:
        return True
    target = normalize_subject_identity(subject_key)
    candidates = [
        card.get("subject_key"),
        card.get("subject_id"),
        card.get("subject_name"),
        card.get("theme_name"),
        card.get("name"),
    ]
    return any(normalize_subject_identity(candidate) == target for candidate in candidates)


def explicit_field_override(
    card: dict[str, Any] | None,
    field_name: str,
) -> dict[str, Any] | None:
    """Extract an explicit override from card.field_overrides.

    This is intentionally separate from dual-track review fields because
    identity edits such as subject_name live in field_overrides and are not
    encoded as top-level {override: true} review fields.
    """
    if not isinstance(card, dict):
        return None
    overrides = card.get("field_overrides")
    if not isinstance(overrides, dict):
        return None
    override = overrides.get(field_name)
    if isinstance(override, dict):
        return override
    return None


def override_final_value(override: dict[str, Any] | None) -> Any:
    """Return the explicit analyst/final value from a field override."""
    if not isinstance(override, dict):
        return None
    for key in ("final_value", "analyst_value"):
        value = override.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return None


def resolve_identity_override_for_subject(
    *,
    card: dict[str, Any] | None,
    subject_key: str | None,
    field_name: str,
    entity_value: Any = None,
) -> Any:
    """Resolve an identity field for a single subject cognition card."""
    if not isinstance(card, dict) or not subject_identity_matches(card, subject_key):
        return entity_value
    return resolve_identity(
        entity_value=entity_value,
        override=explicit_field_override(card, field_name),
    )
