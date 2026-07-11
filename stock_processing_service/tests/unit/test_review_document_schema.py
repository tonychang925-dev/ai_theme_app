"""PR1.1 — ReviewDocument schema and type contracts."""

from __future__ import annotations

import json
from dataclasses import fields

from stock_processing_service.application.services.review_document import (
    DocumentStatus,
    FieldClass,
    FieldProvenanceEntry,
    ReviewDocument,
    SectionQualityStatus,
    TransformType,
    ValidationStatus,
)
from stock_processing_service.application.services.review_document.schema import (
    ASSEMBLER_VERSION,
    DOCUMENT_SCHEMA_VERSION,
    REQUIRED_SECTIONS,
    REVIEW_DOCUMENT_SCHEMA_VERSION,
    ReviewDocumentMetadata,
    SNAPSHOT_SCHEMA_VERSION,
)


EXPECTED_TOP_LEVEL_FIELDS = {
    "metadata",
    "summary",
    "market",
    "emotion",
    "themes",
    "stocks",
    "capital",
    "limit_up",
    "plan",
    "risk",
    "quality",
    "field_provenance",
    "audit",
}


def test_empty_review_document_is_json_serializable_and_versioned() -> None:
    doc = ReviewDocument.create_empty(trade_date="2026-07-09")

    payload = doc.to_dict()
    json.dumps(payload, ensure_ascii=False)

    metadata = payload["metadata"]
    assert metadata["trade_date"] == "2026-07-09"
    assert metadata["status"] == DocumentStatus.DRAFT.value
    assert metadata["document_schema_version"] == DOCUMENT_SCHEMA_VERSION
    assert metadata["review_document_schema_version"] == REVIEW_DOCUMENT_SCHEMA_VERSION
    assert metadata["snapshot_schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert metadata["assembler_version"] == ASSEMBLER_VERSION


def test_review_document_has_quality_for_every_required_section() -> None:
    payload = ReviewDocument.create_empty(trade_date="2026-07-09").to_dict()

    quality = payload["quality"]
    assert quality["overall"] == SectionQualityStatus.BLOCKED.value
    assert quality["can_approve"] is False
    assert set(quality["sections"]) == set(REQUIRED_SECTIONS)

    for section in REQUIRED_SECTIONS:
        section_quality = quality["sections"][section]
        assert section_quality["status"] == SectionQualityStatus.MISSING.value
        assert "missing_fields" in section_quality
        assert "warnings" in section_quality
        assert "blocking_issues" in section_quality


def test_field_provenance_entry_serializes_validation_status() -> None:
    provenance = FieldProvenanceEntry(
        source="snapshot.chart_reviews.market_power.limit_up_count",
        field_type=FieldClass.FACT,
        confidence=1.0,
        transform=TransformType.DIRECT_MAPPING,
        validation_status=ValidationStatus.VERIFIED,
        source_trade_date="2026-07-09",
        source_generated_at="2026-07-09T15:05:00+08:00",
    )

    payload = provenance.to_dict()
    assert payload == {
        "source": "snapshot.chart_reviews.market_power.limit_up_count",
        "field_type": "FACT",
        "confidence": 1.0,
        "transform": "direct_mapping",
        "validation_status": "verified",
        "source_trade_date": "2026-07-09",
        "source_generated_at": "2026-07-09T15:05:00+08:00",
    }


def test_review_document_top_level_contract_has_no_legacy_or_formal_review() -> None:
    payload = ReviewDocument.create_empty(trade_date="2026-07-09").to_dict()

    assert "review_document" not in payload
    assert "formal_review" not in payload
    assert "legacy" not in payload
    assert "emotion_review" not in payload
    assert "market_chart_reviews" not in payload


def test_review_document_top_level_fields_are_frozen() -> None:
    field_names = {field.name for field in fields(ReviewDocument)}

    assert field_names == EXPECTED_TOP_LEVEL_FIELDS
    assert set(ReviewDocument.create_empty(trade_date="2026-07-09").to_dict()) == EXPECTED_TOP_LEVEL_FIELDS


def test_review_document_schema_names_do_not_contain_legacy_terms() -> None:
    schema_text = json.dumps(
        {
            "review_document_fields": [field.name for field in fields(ReviewDocument)],
            "metadata_fields": [field.name for field in fields(ReviewDocumentMetadata)],
            "payload": ReviewDocument.create_empty(trade_date="2026-07-09").to_dict(),
        },
        ensure_ascii=False,
    )

    forbidden_terms = ("legacy", "recap", "formal_review", "emotion_review", "market_chart_reviews")
    for term in forbidden_terms:
        assert term not in schema_text


def test_field_class_enum_is_frozen() -> None:
    assert [item.value for item in FieldClass] == [
        "FACT",
        "IDENTITY",
        "ASSESSMENT",
        "PLAN",
        "AUDIT",
    ]
    assert len(FieldClass) == 5


def test_transform_type_disallows_business_logic_and_fallback() -> None:
    values = {item.value for item in TransformType}

    assert values == {
        "direct_mapping",
        "explicit_override",
        "format_only",
        "aggregate_from_snapshot",
    }
    forbidden = {"fallback", "calculate", "infer", "derive", "computed", "merge"}
    assert values.isdisjoint(forbidden)


def test_metadata_version_fields_are_required_for_reproducibility() -> None:
    metadata = ReviewDocumentMetadata(
        trade_date="2026-07-09",
        status=DocumentStatus.DRAFT,
        snapshot_hash="sha256:snapshot",
        final_document_hash="sha256:document",
    ).to_dict()

    required = {
        "document_schema_version",
        "review_document_schema_version",
        "snapshot_schema_version",
        "assembler_version",
        "snapshot_hash",
        "final_document_hash",
    }
    assert required <= set(metadata)
    for field_name in required:
        assert metadata[field_name]
