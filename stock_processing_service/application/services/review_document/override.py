"""ReviewDocument field-level override model and applier.

Overrides are explicit analyst edits. They are applied to a ReviewDocument
view-model only; this module never mutates snapshots, queries databases, or
generates business conclusions.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .enums import FieldClass
from .schema import REVIEW_DOCUMENT_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ReviewOverride:
    field_path: str
    field_class: FieldClass
    ai_value: Any
    analyst_value: Any
    final_value: Any
    reason: str
    author: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "field_class": self.field_class.value,
            "ai_value": self.ai_value,
            "analyst_value": self.analyst_value,
            "final_value": self.final_value,
            "reason": self.reason,
            "author": self.author,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReviewOverride":
        return cls(
            field_path=str(payload.get("field_path") or ""),
            field_class=FieldClass(str(payload.get("field_class") or FieldClass.ASSESSMENT.value)),
            ai_value=payload.get("ai_value"),
            analyst_value=payload.get("analyst_value"),
            final_value=payload.get("final_value") if payload.get("final_value") not in (None, "") else payload.get("analyst_value"),
            reason=str(payload.get("reason") or ""),
            author=str(payload.get("author") or ""),
            timestamp=str(payload.get("timestamp") or ""),
        )


@dataclass(frozen=True, slots=True)
class ReviewOverrideResult:
    document: dict[str, Any]
    applied_overrides: tuple[ReviewOverride, ...]
    rejected_overrides: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "applied_overrides": [item.to_dict() for item in self.applied_overrides],
            "rejected_overrides": list(self.rejected_overrides),
        }


class ReviewOverrideApplier:
    """Apply explicit overrides to a ReviewDocument dict."""

    def apply(self, document: dict[str, Any], overrides: list[ReviewOverride]) -> ReviewOverrideResult:
        next_doc = copy.deepcopy(document)
        applied: list[ReviewOverride] = []
        rejected: list[dict[str, Any]] = []

        for override in overrides:
            ok, reason = _apply_one(next_doc, override)
            if ok:
                applied.append(override)
                _append_audit(next_doc, override)
                _append_provenance(next_doc, override)
            else:
                rejected.append({"override": override.to_dict(), "reason": reason})

        if applied:
            metadata = next_doc.setdefault("metadata", {})
            metadata["review_document_schema_version"] = metadata.get("review_document_schema_version") or REVIEW_DOCUMENT_SCHEMA_VERSION
            metadata["status"] = "EDITING"
            metadata["final_document_hash"] = _document_hash(next_doc)

        return ReviewOverrideResult(
            document=next_doc,
            applied_overrides=tuple(applied),
            rejected_overrides=tuple(rejected),
        )


def _apply_one(document: dict[str, Any], override: ReviewOverride) -> tuple[bool, str]:
    if not override.field_path:
        return False, "field_path_missing"
    if override.field_class == FieldClass.FACT:
        return False, "fact_override_forbidden"

    if override.field_path.startswith("themes["):
        return _apply_theme_override(document, override)

    target, field_name = _resolve_simple_parent(document, override.field_path)
    if target is None or not field_name:
        return False, "path_not_found"
    target[field_name] = override.final_value
    return True, ""


def _apply_theme_override(document: dict[str, Any], override: ReviewOverride) -> tuple[bool, str]:
    token, field_name = _parse_bracket_path(override.field_path, prefix="themes")
    if token is None or not field_name:
        return False, "invalid_theme_path"
    themes = document.get("themes")
    if not isinstance(themes, list):
        return False, "themes_missing"

    theme = _find_theme(themes, token)
    if theme is None:
        return False, "theme_not_found"

    current = theme.get(field_name)
    if isinstance(current, dict):
        ai_value = current.get("ai_value", override.ai_value)
    else:
        ai_value = current if current not in (None, "") else override.ai_value

    if override.field_class == FieldClass.IDENTITY and field_name in {"name", "subject_name", "theme_name"}:
        theme["name"] = {
            "ai_value": ai_value,
            "analyst_value": override.analyst_value,
            "final_value": override.final_value,
            "reason": override.reason,
        }
        _sync_summary_primary_theme(document, theme)
        return True, ""

    theme[field_name] = override.final_value
    return True, ""


def _sync_summary_primary_theme(document: dict[str, Any], theme: dict[str, Any]) -> None:
    summary = document.setdefault("summary", {})
    current_primary = summary.get("primary_theme")
    if not current_primary:
        summary["primary_theme"] = theme.get("name")
        return
    current_final = _final_value(current_primary)
    theme_ai = _final_value({"final_value": (theme.get("name") or {}).get("ai_value")} if isinstance(theme.get("name"), dict) else theme.get("name"))
    if current_final == theme_ai or current_final == _final_value(theme.get("name")):
        summary["primary_theme"] = theme.get("name")


def _resolve_simple_parent(document: dict[str, Any], field_path: str) -> tuple[dict[str, Any] | None, str]:
    parts = [part for part in field_path.split(".") if part]
    if not parts:
        return None, ""
    current: Any = document
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return None, ""
        current = current.get(part)
    return (current, parts[-1]) if isinstance(current, dict) else (None, "")


def _parse_bracket_path(path: str, *, prefix: str) -> tuple[str | None, str]:
    start = f"{prefix}["
    if not path.startswith(start):
        return None, ""
    end = path.find("]")
    if end < len(start):
        return None, ""
    token = path[len(start):end]
    suffix = path[end + 1:]
    if suffix.startswith("."):
        suffix = suffix[1:]
    return token, suffix


def _find_theme(themes: list[Any], token: str) -> dict[str, Any] | None:
    if token.isdigit():
        idx = int(token)
        if 0 <= idx < len(themes) and isinstance(themes[idx], dict):
            return themes[idx]
        return None
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        if str(theme.get("theme_key") or theme.get("subject_key") or "") == token:
            return theme
    return None


def _append_audit(document: dict[str, Any], override: ReviewOverride) -> None:
    audit = document.setdefault("audit", {})
    explicit = audit.setdefault("explicit_overrides", [])
    if isinstance(explicit, list):
        explicit.append({
            "entity_key": _entity_key_from_path(override.field_path),
            "field": _field_name_from_path(override.field_path),
            "field_path": override.field_path,
            "field_class": override.field_class.value,
            "ai_value": override.ai_value,
            "analyst_value": override.analyst_value,
            "final_value": override.final_value,
            "reason": override.reason,
            "author": override.author,
            "timestamp": override.timestamp,
        })


def _append_provenance(document: dict[str, Any], override: ReviewOverride) -> None:
    provenance = document.setdefault("field_provenance", {})
    if isinstance(provenance, dict):
        provenance[f"{override.field_path}.final_value"] = {
            "source": "review_override",
            "field_type": override.field_class.value,
            "confidence": 1.0,
            "transform": "explicit_override",
            "validation_status": "verified",
        }


def _document_hash(document: dict[str, Any]) -> str:
    payload = copy.deepcopy(document)
    metadata = payload.setdefault("metadata", {})
    metadata.pop("final_document_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entity_key_from_path(path: str) -> str:
    if path.startswith("themes["):
        token, _field = _parse_bracket_path(path, prefix="themes")
        return token or ""
    return ""


def _field_name_from_path(path: str) -> str:
    if path.startswith("themes["):
        _token, field = _parse_bracket_path(path, prefix="themes")
        return "subject_name" if field == "name" else field
    return path.split(".")[-1]


def _final_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("final_value")
    return value
