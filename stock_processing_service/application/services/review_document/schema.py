"""ReviewDocument v1 schema.

These dataclasses define the display contract only. They do not assemble,
compute, infer, or fetch business data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import (
    DocumentStatus,
    FieldClass,
    SectionQualityStatus,
    TransformType,
    ValidationStatus,
)
from .quality import FreshnessQuality, ReviewDocumentQuality, SectionQuality

DOCUMENT_SCHEMA_VERSION = "review_document_v1"
REVIEW_DOCUMENT_SCHEMA_VERSION = "1.0"
SNAPSHOT_SCHEMA_VERSION = "4.5.7"
ASSEMBLER_VERSION = "assembler_v1.0"

REQUIRED_SECTIONS = (
    "summary",
    "market",
    "emotion",
    "themes",
    "stocks",
    "capital",
    "limit_up",
    "plan",
    "risk",
)


@dataclass(frozen=True, slots=True)
class ReviewDocumentMetadata:
    """Versioned metadata required for historical reproducibility."""

    trade_date: str
    status: DocumentStatus
    document_schema_version: str = DOCUMENT_SCHEMA_VERSION
    review_document_schema_version: str = REVIEW_DOCUMENT_SCHEMA_VERSION
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION
    assembler_version: str = ASSEMBLER_VERSION
    source: str = "analyst_workbench"
    snapshot_hash: str | None = None
    final_document_hash: str | None = None
    snapshot_version: int | None = None
    generated_at: str | None = None
    approved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trade_date": self.trade_date,
            "document_schema_version": self.document_schema_version,
            "review_document_schema_version": self.review_document_schema_version,
            "snapshot_schema_version": self.snapshot_schema_version,
            "assembler_version": self.assembler_version,
            "status": self.status.value,
            "source": self.source,
        }
        optional = {
            "snapshot_hash": self.snapshot_hash,
            "final_document_hash": self.final_document_hash,
            "snapshot_version": self.snapshot_version,
            "generated_at": self.generated_at,
            "approved_at": self.approved_at,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        return payload


@dataclass(frozen=True, slots=True)
class FieldProvenanceEntry:
    """Field-level provenance and validation state."""

    source: str
    field_type: FieldClass
    confidence: float
    transform: TransformType
    validation_status: ValidationStatus
    source_trade_date: str | None = None
    source_generated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "field_type": self.field_type.value,
            "confidence": self.confidence,
            "transform": self.transform.value,
            "validation_status": self.validation_status.value,
        }
        if self.source_trade_date is not None:
            payload["source_trade_date"] = self.source_trade_date
        if self.source_generated_at is not None:
            payload["source_generated_at"] = self.source_generated_at
        return payload


@dataclass(frozen=True, slots=True)
class ReviewDocument:
    """Unified frontend display contract for Workbench and DailyReview."""

    metadata: ReviewDocumentMetadata
    quality: ReviewDocumentQuality
    summary: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)
    emotion: dict[str, Any] = field(default_factory=dict)
    themes: tuple[dict[str, Any], ...] = ()
    stocks: tuple[dict[str, Any], ...] = ()
    capital: dict[str, Any] = field(default_factory=dict)
    limit_up: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    field_provenance: dict[str, FieldProvenanceEntry] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_empty(cls, *, trade_date: str, status: DocumentStatus = DocumentStatus.DRAFT) -> "ReviewDocument":
        """Create a schema-valid empty document skeleton.

        This is useful for contract tests and empty states. It deliberately
        marks all business sections as MISSING and cannot be approved.
        """
        sections = {
            section: SectionQuality(status=SectionQualityStatus.MISSING)
            for section in REQUIRED_SECTIONS
        }
        quality = ReviewDocumentQuality(
            overall=SectionQualityStatus.BLOCKED,
            sections=sections,
            can_approve=False,
            blocking_issues=("review_document_empty",),
            freshness=FreshnessQuality(status=SectionQualityStatus.MISSING),
        )
        return cls(
            metadata=ReviewDocumentMetadata(trade_date=trade_date, status=status),
            quality=quality,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "summary": dict(self.summary),
            "market": dict(self.market),
            "emotion": dict(self.emotion),
            "themes": [dict(item) for item in self.themes],
            "stocks": [dict(item) for item in self.stocks],
            "capital": dict(self.capital),
            "limit_up": dict(self.limit_up),
            "plan": dict(self.plan),
            "risk": dict(self.risk),
            "evidence": dict(self.evidence),
            "quality": self.quality.to_dict(),
            "field_provenance": {
                key: value.to_dict()
                for key, value in self.field_provenance.items()
            },
            "audit": dict(self.audit),
        }
