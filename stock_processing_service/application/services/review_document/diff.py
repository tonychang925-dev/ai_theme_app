"""ReviewDocument diff model and generator.

Diff is read-only. It converts explicit analyst overrides already present in a
ReviewDocument into field-level changes for UI review and future learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import FieldClass


@dataclass(frozen=True, slots=True)
class ReviewDocumentDiffChange:
    path: str
    field_class: FieldClass
    before: Any
    after: Any
    final_value: Any
    reason: str = ""
    source: str = "explicit_override"
    entity_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "field_class": self.field_class.value,
            "before": self.before,
            "after": self.after,
            "final_value": self.final_value,
            "reason": self.reason,
            "source": self.source,
            "entity_key": self.entity_key,
        }


@dataclass(frozen=True, slots=True)
class ReviewDocumentDiff:
    changes: tuple[ReviewDocumentDiffChange, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [change.to_dict() for change in self.changes],
            "summary": dict(self.summary),
        }


class ReviewDocumentDiffService:
    """Build field-level diff from a ReviewDocument payload."""

    def diff(self, document: dict[str, Any]) -> ReviewDocumentDiff:
        audit = document.get("audit") if isinstance(document, dict) else {}
        explicit = audit.get("explicit_overrides") if isinstance(audit, dict) else []
        changes = tuple(
            change
            for item in explicit or []
            if isinstance(item, dict)
            for change in [self._change_from_override(item)]
            if change is not None
        )
        return ReviewDocumentDiff(
            changes=changes,
            summary={
                "total_changes": len(changes),
                "identity_changes": sum(1 for change in changes if change.field_class == FieldClass.IDENTITY),
                "assessment_changes": sum(1 for change in changes if change.field_class == FieldClass.ASSESSMENT),
                "plan_changes": sum(1 for change in changes if change.field_class == FieldClass.PLAN),
            },
        )

    def _change_from_override(self, item: dict[str, Any]) -> ReviewDocumentDiffChange | None:
        field_name = str(item.get("field") or "")
        if not field_name:
            return None
        field_class = _field_class_for(field_name)
        entity_key = str(item.get("entity_key") or "")
        return ReviewDocumentDiffChange(
            path=_path_for(entity_key=entity_key, field_name=field_name),
            field_class=field_class,
            before=item.get("ai_value"),
            after=item.get("analyst_value"),
            final_value=item.get("final_value") if item.get("final_value") not in (None, "") else item.get("analyst_value"),
            reason=str(item.get("reason") or ""),
            entity_key=entity_key,
        )


def _field_class_for(field_name: str) -> FieldClass:
    normalized = field_name.lower()
    if normalized in {"subject_name", "theme_name", "name", "subject_key", "theme_key"}:
        return FieldClass.IDENTITY
    if normalized in {"tomorrow_view", "scenario", "watch_themes", "allowed_actions", "forbidden_actions"}:
        return FieldClass.PLAN
    return FieldClass.ASSESSMENT


def _path_for(*, entity_key: str, field_name: str) -> str:
    if field_name in {"subject_name", "theme_name", "name"}:
        suffix = "name"
    else:
        suffix = field_name
    if entity_key:
        return f"themes[{entity_key}].{suffix}"
    return suffix
