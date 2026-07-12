"""ReviewDocument schema contracts.

Phase 4.5.7 introduces ReviewDocument as the single frontend display
contract for Analyst Workbench and DailyReview. This package starts with
schema/types only; assembler and API wiring are intentionally separate PRs.
"""

from .enums import (
    DocumentStatus,
    FieldClass,
    SectionQualityStatus,
    TransformType,
    ValidationStatus,
)
from .quality import FreshnessQuality, ReviewDocumentQuality, SectionQuality
from .context import (
    CapitalContext,
    EmotionContext,
    MarketContext,
    OverrideContext,
    PlanContext,
    ReviewDocumentAssemblerInput,
    ReviewDocumentContext,
    ReviewDocumentContextFactory,
    StockContext,
    ThemeContext,
)
from .assembler import ReviewDocumentAssembler
from .schema import (
    FieldProvenanceEntry,
    ReviewDocument,
    ReviewDocumentMetadata,
)

__all__ = [
    "DocumentStatus",
    "CapitalContext",
    "EmotionContext",
    "FieldClass",
    "FieldProvenanceEntry",
    "FreshnessQuality",
    "MarketContext",
    "OverrideContext",
    "PlanContext",
    "ReviewDocument",
    "ReviewDocumentAssembler",
    "ReviewDocumentAssemblerInput",
    "ReviewDocumentContext",
    "ReviewDocumentContextFactory",
    "ReviewDocumentMetadata",
    "ReviewDocumentQuality",
    "SectionQuality",
    "SectionQualityStatus",
    "StockContext",
    "ThemeContext",
    "TransformType",
    "ValidationStatus",
]
