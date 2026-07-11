"""Enums for the ReviewDocument v1 schema."""

from __future__ import annotations

from enum import StrEnum


class FieldClass(StrEnum):
    """Field classification used by merge, quality, and provenance logic."""

    FACT = "FACT"
    IDENTITY = "IDENTITY"
    ASSESSMENT = "ASSESSMENT"
    PLAN = "PLAN"
    AUDIT = "AUDIT"


class DocumentStatus(StrEnum):
    """Lifecycle status of a ReviewDocument view."""

    DRAFT = "DRAFT"
    EDITING = "EDITING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED_VIEW = "PUBLISHED_VIEW"


class SectionQualityStatus(StrEnum):
    """Section-level data quality status."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class ValidationStatus(StrEnum):
    """Field provenance validation state."""

    VERIFIED = "verified"
    WARNING = "warning"
    INVALID = "invalid"


class TransformType(StrEnum):
    """Allowed field transformation labels for provenance."""

    DIRECT_MAPPING = "direct_mapping"
    EXPLICIT_OVERRIDE = "explicit_override"
    FORMAT_ONLY = "format_only"
    AGGREGATE_FROM_SNAPSHOT = "aggregate_from_snapshot"
