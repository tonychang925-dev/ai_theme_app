"""Quality contracts for ReviewDocument sections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import SectionQualityStatus


@dataclass(frozen=True, slots=True)
class FreshnessQuality:
    """Freshness state for a document or section.

    FACT fields are expected to match the document trade_date. This class is
    schema-only; enforcement belongs to the assembler quality gate.
    """

    status: SectionQualityStatus = SectionQualityStatus.READY
    snapshot_age_seconds: int | None = None
    derived_data_time: str | None = None
    trade_date_match: bool | None = None
    source_trade_date: str | None = None
    source_generated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status.value}
        optional = {
            "snapshot_age_seconds": self.snapshot_age_seconds,
            "derived_data_time": self.derived_data_time,
            "trade_date_match": self.trade_date_match,
            "source_trade_date": self.source_trade_date,
            "source_generated_at": self.source_generated_at,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        return payload


@dataclass(frozen=True, slots=True)
class SectionQuality:
    """Quality status for one ReviewDocument section."""

    status: SectionQualityStatus
    missing_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()
    freshness: FreshnessQuality | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status.value,
            "missing_fields": list(self.missing_fields),
            "warnings": list(self.warnings),
            "blocking_issues": list(self.blocking_issues),
        }
        if self.freshness is not None:
            payload["freshness"] = self.freshness.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ReviewDocumentQuality:
    """Top-level quality state for a ReviewDocument."""

    overall: SectionQualityStatus
    sections: dict[str, SectionQuality] = field(default_factory=dict)
    can_approve: bool = False
    blocking_issues: tuple[str, ...] = ()
    freshness: FreshnessQuality | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "overall": self.overall.value,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "can_approve": self.can_approve,
            "blocking_issues": list(self.blocking_issues),
        }
        if self.freshness is not None:
            payload["freshness"] = self.freshness.to_dict()
        return payload
