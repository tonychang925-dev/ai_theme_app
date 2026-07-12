"""Theme identity resolver.

This module resolves only stable identity fields. It does not decide market
state or lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RawThemeIdentity:
    subject_key: str
    theme_name: str | None = None
    subject_name: str | None = None


@dataclass(frozen=True, slots=True)
class ThemeIdentity:
    subject_key: str
    canonical_name: str | None
    entity_type: str
    identity_source: str | None
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "identity_source": self.identity_source,
            "confidence": self.confidence,
        }


class ThemeIdentityResolver:
    """Resolve subject_key to canonical theme identity from explicit records."""

    entity_type = "A_SHARE_THEME"

    def resolve(self, raw: RawThemeIdentity, lookup_records: list[dict[str, Any]] | None = None) -> ThemeIdentity:
        direct_name = _clean_text(raw.theme_name)
        direct_source = "input.theme_name"
        if not direct_name or direct_name.isdigit():
            fallback = _clean_text(raw.subject_name)
            if fallback and not fallback.isdigit():
                direct_name = fallback
                direct_source = "input.subject_name"
            else:
                direct_name = ""
        if direct_name:
            return ThemeIdentity(
                subject_key=raw.subject_key,
                canonical_name=direct_name,
                entity_type=self.entity_type,
                identity_source=direct_source,
                confidence=1.0,
            )

        for record in lookup_records or []:
            key = _record_key(record)
            if key != raw.subject_key:
                continue
            name = _clean_text(record.get("theme_name")) or _clean_text(record.get("subject_name"))
            if name and not name.isdigit():
                return ThemeIdentity(
                    subject_key=raw.subject_key,
                    canonical_name=name,
                    entity_type=self.entity_type,
                    identity_source=_record_source(record),
                    confidence=1.0,
                )

        return ThemeIdentity(
            subject_key=raw.subject_key,
            canonical_name=None,
            entity_type=self.entity_type,
            identity_source=None,
            confidence=0.0,
        )

    def resolve_theme_rows(
        self,
        theme_rows: list[dict[str, Any]],
        cognition_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        lookup_records = [
            *_with_identity_source(theme_rows, "theme_rows"),
            *_with_identity_source(cognition_cards, "cognition_cards"),
        ]
        resolved_rows: list[dict[str, Any]] = []
        for row in theme_rows:
            key = _record_key(row)
            if not key:
                resolved_rows.append(dict(row))
                continue
            identity = self.resolve(
                RawThemeIdentity(
                    subject_key=key,
                    theme_name=_clean_text(row.get("theme_name")),
                    subject_name=_clean_text(row.get("subject_name")),
                ),
                lookup_records,
            )
            resolved = dict(row)
            resolved["subject_key"] = key
            resolved["theme_identity"] = identity.to_dict()
            if identity.canonical_name:
                resolved["theme_name"] = identity.canonical_name
            else:
                resolved.pop("theme_name", None)
            resolved_rows.append(resolved)
        return resolved_rows


def _with_identity_source(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    return [{**row, "_identity_source": source} for row in rows]


def _record_key(record: dict[str, Any]) -> str:
    return _clean_text(record.get("subject_key") or record.get("theme_key") or record.get("subject_id"))


def _record_source(record: dict[str, Any]) -> str:
    source = _clean_text(record.get("_identity_source"))
    if source:
        return f"{source}.subject_name"
    return "lookup.subject_name"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text
