"""ThemeIdentityResolver — resolve subject_key to display name.

Phase 4.5.6-PROJECTION HARDENING PR-A.

The compiler must NOT hardcode subject_key → name mappings.
Resolution sources (priority order):
  1. theme_name_map (from builder, populated by DerivedRecapDocReader)
  2. theme_reviews (from derived tables, subject_key → theme_name rows)
  3. cognition_cards (from snapshot, subject_id → subject_name)
"""

from __future__ import annotations

from typing import Any


class ThemeIdentityResolver:
    """Resolve subject_key identifiers to Chinese display names.

    Builds a lookup from all available data sources present in the
    approved snapshot and derived evidence. Contains NO hardcoded
    business knowledge — all mappings come from data.
    """

    def __init__(
        self,
        theme_name_map: dict[str, str] | None = None,
        theme_reviews: list[dict[str, Any]] | None = None,
        cognition_cards: list[dict[str, Any]] | None = None,
    ):
        self._name_map: dict[str, str] = {}

        # Source 1: theme_name_map from builder (priority)
        if theme_name_map:
            for sk, tn in theme_name_map.items():
                sk = str(sk)
                tn = str(tn)
                if tn and tn != sk and not tn.isdigit():
                    self._name_map[sk] = tn

        # Source 2: theme_reviews from derived data
        if theme_reviews:
            for tr in theme_reviews:
                sk = str(tr.get("subject_key", ""))
                tn = str(tr.get("theme_name", ""))
                if sk and tn and tn != sk and not tn.isdigit():
                    if sk not in self._name_map:
                        self._name_map[sk] = tn

        # Source 3: cognition_cards from snapshot
        if cognition_cards:
            for card in cognition_cards:
                sk = str(card.get("subject_id", ""))
                sn = str(card.get("subject_name", ""))
                # Only use if subject_name is a real name (not a subject_key)
                if sk and sn and sn != sk and not sn.isdigit():
                    if sk not in self._name_map:
                        self._name_map[sk] = sn

    def resolve(self, raw: str) -> str:
        """Resolve a subject_key to its display name.

        Returns the display name if found, otherwise returns raw unchanged.
        """
        if not raw:
            return ""
        # Already a display name
        if not raw.isdigit() and raw.isascii() and not any('\u4e00' <= c <= '\u9fff' for c in raw[:3]):
            if raw in self._name_map:
                return self._name_map[raw]
            return raw
        # Subject_key lookup
        if raw in self._name_map:
            return self._name_map[raw]
        # Strip "theme:" prefix and retry
        if raw.startswith("theme:"):
            sk = raw[6:]
            if sk in self._name_map:
                return self._name_map[sk]
        return raw

    def __contains__(self, key: str) -> bool:
        return key in self._name_map
