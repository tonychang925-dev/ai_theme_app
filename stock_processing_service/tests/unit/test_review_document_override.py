"""PR3 — ReviewDocument override model and applier tests."""

from __future__ import annotations

import copy

from stock_processing_service.application.services.review_document import (
    FieldClass,
    ReviewOverride,
    ReviewOverrideApplier,
)


def _draft_document() -> dict:
    return {
        "metadata": {
            "trade_date": "2026-07-09",
            "status": "DRAFT",
            "document_schema_version": "review_document_v1",
            "review_document_schema_version": "1.0",
            "assembler_version": "assembler_v1.0",
            "final_document_hash": "sha256:old",
        },
        "summary": {
            "primary_theme": {
                "ai_value": "人形机器人",
                "analyst_value": None,
                "final_value": "人形机器人",
                "reason": "",
            }
        },
        "market": {"limit_up_count": 75},
        "themes": [
            {
                "theme_key": "robot",
                "name": {
                    "ai_value": "人形机器人",
                    "analyst_value": None,
                    "final_value": "人形机器人",
                    "reason": "",
                },
                "role": "MAINLINE",
                "stage": "分歧",
            }
        ],
        "quality": {"overall": "READY"},
        "field_provenance": {},
        "audit": {"explicit_overrides": []},
    }


def test_review_override_round_trip_contract() -> None:
    payload = {
        "field_path": "themes[robot].name",
        "field_class": "IDENTITY",
        "ai_value": "人形机器人",
        "analyst_value": "PCB",
        "final_value": "PCB",
        "reason": "资金切换",
        "author": "analyst",
        "timestamp": "2026-07-09T16:00:00+08:00",
    }

    override = ReviewOverride.from_dict(payload)

    assert override.field_class == FieldClass.IDENTITY
    assert override.to_dict() == payload


def test_identity_override_updates_document_without_mutating_input() -> None:
    draft = _draft_document()
    original = copy.deepcopy(draft)
    override = ReviewOverride(
        field_path="themes[robot].name",
        field_class=FieldClass.IDENTITY,
        ai_value="人形机器人",
        analyst_value="PCB",
        final_value="PCB",
        reason="资金切换",
        author="analyst",
        timestamp="2026-07-09T16:00:00+08:00",
    )

    result = ReviewOverrideApplier().apply(draft, [override]).to_dict()
    final_doc = result["document"]

    assert draft == original
    assert result["rejected_overrides"] == []
    assert final_doc["metadata"]["status"] == "EDITING"
    assert final_doc["metadata"]["final_document_hash"].startswith("sha256:")
    assert final_doc["metadata"]["final_document_hash"] != "sha256:old"
    assert final_doc["themes"][0]["name"] == {
        "ai_value": "人形机器人",
        "analyst_value": "PCB",
        "final_value": "PCB",
        "reason": "资金切换",
    }
    assert final_doc["summary"]["primary_theme"]["final_value"] == "PCB"
    assert final_doc["audit"]["explicit_overrides"][0]["field_class"] == "IDENTITY"
    assert final_doc["audit"]["explicit_overrides"][0]["field_path"] == "themes[robot].name"
    assert final_doc["field_provenance"]["themes[robot].name.final_value"]["source"] == "review_override"


def test_override_changes_document_hash_deterministically() -> None:
    draft = _draft_document()
    override = ReviewOverride(
        field_path="themes[robot].name",
        field_class=FieldClass.IDENTITY,
        ai_value="人形机器人",
        analyst_value="PCB",
        final_value="PCB",
        reason="资金切换",
    )

    result1 = ReviewOverrideApplier().apply(draft, [override]).to_dict()
    result2 = ReviewOverrideApplier().apply(draft, [override]).to_dict()

    assert result1["document"]["metadata"]["final_document_hash"] != draft["metadata"]["final_document_hash"]
    assert result1["document"]["metadata"]["final_document_hash"] == result2["document"]["metadata"]["final_document_hash"]


def test_override_hash_is_stable_independent_of_input_order() -> None:
    draft = _draft_document()
    override_a = ReviewOverride(
        field_path="themes[robot].name",
        field_class=FieldClass.IDENTITY,
        ai_value="人形机器人",
        analyst_value="PCB",
        final_value="PCB",
        reason="资金切换",
    )
    override_b = ReviewOverride(
        field_path="summary.market_conclusion",
        field_class=FieldClass.ASSESSMENT,
        ai_value="混沌",
        analyst_value="反弹套利",
        final_value="反弹套利",
        reason="情绪修复",
    )

    result_ab = ReviewOverrideApplier().apply(draft, [override_a, override_b]).to_dict()
    result_ba = ReviewOverrideApplier().apply(draft, [override_b, override_a]).to_dict()

    assert result_ab["document"]["metadata"]["final_document_hash"] == result_ba["document"]["metadata"]["final_document_hash"]
    assert result_ab["document"]["audit"]["explicit_overrides"] == result_ba["document"]["audit"]["explicit_overrides"]


def test_fact_override_is_rejected() -> None:
    draft = _draft_document()
    override = ReviewOverride(
        field_path="market.limit_up_count",
        field_class=FieldClass.FACT,
        ai_value=75,
        analyst_value=99,
        final_value=99,
        reason="manual correction",
    )

    result = ReviewOverrideApplier().apply(draft, [override]).to_dict()

    assert result["applied_overrides"] == []
    assert result["rejected_overrides"][0]["reason"] == "fact_override_forbidden"
    assert result["document"]["market"]["limit_up_count"] == 75
    assert result["document"]["metadata"]["final_document_hash"] == "sha256:old"


def test_fact_path_cannot_be_overridden_with_identity_class() -> None:
    draft = _draft_document()
    override = ReviewOverride(
        field_path="market.limit_up_count",
        field_class=FieldClass.IDENTITY,
        ai_value=75,
        analyst_value=99,
        final_value=99,
        reason="wrong class",
    )

    result = ReviewOverrideApplier().apply(draft, [override]).to_dict()

    assert result["applied_overrides"] == []
    assert result["rejected_overrides"][0]["reason"] == "fact_path_override_forbidden"
    assert result["document"]["market"]["limit_up_count"] == 75
    assert result["document"]["metadata"]["final_document_hash"] == "sha256:old"
