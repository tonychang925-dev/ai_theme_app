"""PR1.3 — ReviewDocument ContextFactory + Assembler tests."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from pathlib import Path

import pytest

from stock_processing_service.application.services.review_document import (
    CapitalContext,
    EmotionContext,
    MarketContext,
    OverrideContext,
    PlanContext,
    ReviewDocumentAssembler,
    ReviewDocumentAssemblerInput,
    ReviewDocumentContext,
    ReviewDocumentContextFactory,
    SectionQualityStatus,
    StockContext,
    ThemeContext,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "review_document"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _snapshot_from_golden() -> dict:
    golden = _fixture("2026-07-09-golden.json")
    return {
        "trade_date": golden["trade_date"],
        "snapshot_version": 1,
        "snapshot_hash": "sha256:snapshot",
        "approved": True,
        "approved_at": "2026-07-09T16:30:00+08:00",
        "approval_mode": "analyst_approved",
        "source_mode": "analyst_workbench",
        "composition_mode": "review_document",
        "attention_state": {
            "review_document_context": {
                "trade_date": golden["trade_date"],
                "market_state": {
                    "limit_up_count": golden["market"]["limit_up_count"],
                    "limit_down_count": golden["market"]["limit_down_count"],
                    "up_count": golden["market"]["breadth"]["up_count"],
                    "down_count": golden["market"]["breadth"]["down_count"],
                },
                "themes": [
                    {
                        "subject_key": "storage",
                        "theme_name": "存储芯片",
                        "role": "MAINLINE",
                        "stage": "启动第1天",
                    },
                    {
                        "subject_key": "robot",
                        "theme_name": "机器人",
                        "role": "SECONDARY",
                        "stage": "分歧",
                    },
                    {
                        "subject_key": "robot_watch",
                        "theme_name": "机器人",
                        "role": "WATCH",
                        "stage": "观察",
                    },
                ],
                "money_flows": [
                    {"theme_name": "存储芯片", "role_label": "机构"},
                    {"theme_name": "半导体设备", "role_label": "机构"},
                    {"theme_name": "商业航天", "role_label": "游资"},
                    {"theme_name": "洪涝", "role_label": "游资"},
                ],
                "strong_stocks": [
                    {
                        "stock_code": "603137.SH",
                        "stock_name": golden["stocks"]["leader"]["stock_name"],
                        "board_height": golden["stocks"]["leader"]["board_height"],
                        "theme_name": "存储芯片",
                    }
                ],
            }
        },
        "emotion_review": {
            "phase": golden["emotion"]["phase"],
            "score": golden["emotion"]["score"],
            "summary": "反弹第1天，情绪修复但不是反转",
        },
        "chart_reviews": [],
        "cognition_cards": [
            {
                "subject_id": "robot",
                "subject_name": golden["override"]["ai_value"],
                "attention_level": "CRITICAL",
                "field_overrides": {
                    "subject_name": {
                        "ai_value": golden["override"]["ai_value"],
                        "analyst_value": golden["override"]["analyst_value"],
                        "final_value": golden["override"]["final_value"],
                        "reason": "资金切换",
                    }
                },
            }
        ],
        "playbook": {
            "scenario": "REBOUND_ARBITRAGE",
            "allowed_actions": ["核心方向低吸套利"],
            "forbidden_actions": ["高位接力追龙头"],
            "watch_themes": [{"theme_name": golden["override"]["final_value"]}],
        },
        "override_summary": {},
    }


def test_context_factory_outputs_typed_context_without_exposing_snapshot() -> None:
    context = ReviewDocumentContextFactory().create(_snapshot_from_golden())

    assert isinstance(context, ReviewDocumentContext)
    assert context.trade_date == "2026-07-09"
    assert context.market_context.market_metrics["limit_up_count"] == 75
    assert context.emotion_context.emotion_review["phase"] == "REBOUND"
    assert len(context.theme_context.cognition_cards) == 1
    assert len(context.theme_context.theme_cycle_rows) == 3
    assert len(context.capital_context.money_flow_rows) == 4
    assert len(context.stock_context.strong_stock_rows) == 1

    assert not hasattr(context, "snapshot")
    assert not hasattr(context, "derived_context")


def test_context_factory_only_extracts_whitelist() -> None:
    snapshot = {
        **_snapshot_from_golden(),
        "secret_debug_field": "should_not_leak",
        "legacy_blob": {"old": "world"},
        "recap_doc": {"must": "not leak"},
    }

    context = ReviewDocumentContextFactory().create(snapshot)
    payload = asdict(context)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "secret_debug_field" not in serialized
    assert "should_not_leak" not in serialized
    assert "legacy_blob" not in serialized
    assert "recap_doc" not in serialized


def test_assembler_requires_review_document_assembler_input() -> None:
    assembler = ReviewDocumentAssembler()

    with pytest.raises(AttributeError):
        assembler.assemble(_snapshot_from_golden())  # type: ignore[arg-type]


def test_assembler_outputs_review_document_matching_20260709_golden() -> None:
    golden = _fixture("2026-07-09-golden.json")
    context = ReviewDocumentContextFactory().create(_snapshot_from_golden())

    document = ReviewDocumentAssembler().assemble(
        ReviewDocumentAssemblerInput(context=context, mode="approved")
    ).to_dict()

    assert document["metadata"]["status"] == "APPROVED"
    assert document["market"]["limit_up_count"] == golden["market"]["limit_up_count"]
    assert document["market"]["limit_down_count"] == golden["market"]["limit_down_count"]
    assert document["market"]["up_count"] == golden["market"]["breadth"]["up_count"]
    assert document["market"]["down_count"] == golden["market"]["breadth"]["down_count"]
    assert document["emotion"]["phase"] == golden["emotion"]["phase"]
    assert document["emotion"]["score"] == golden["emotion"]["score"]

    theme_names = {
        item["name"]["final_value"]
        for item in document["themes"]
        if isinstance(item.get("name"), dict)
    }
    assert set(golden["themes"]["must_include"]) <= theme_names
    assert document["summary"]["primary_theme"]["final_value"] == golden["override"]["final_value"]

    institution_names = {item["theme_name"] for item in document["capital"]["institution"]}
    hot_money_names = {item["theme_name"] for item in document["capital"]["hot_money"]}
    assert set(golden["capital"]["institution_must_include"]) <= institution_names
    assert set(golden["capital"]["hot_money_must_include"]) <= hot_money_names
    assert document["stocks"][0]["stock_name"] == golden["stocks"]["leader"]["stock_name"]
    assert document["stocks"][0]["board_height"] == golden["stocks"]["leader"]["board_height"]


def test_assembler_outputs_core_field_provenance() -> None:
    golden = _fixture("2026-07-09-golden.json")
    context = ReviewDocumentContextFactory().create(_snapshot_from_golden())
    document = ReviewDocumentAssembler().assemble(
        ReviewDocumentAssemblerInput(context=context, mode="approved")
    ).to_dict()

    provenance = document["field_provenance"]
    for field_path, expected in golden["field_provenance_required"].items():
        assert field_path in provenance
        assert provenance[field_path]["source"]
        assert provenance[field_path]["field_type"] == expected["field_type"]
        assert provenance[field_path]["source_trade_date"] == expected["source_trade_date"]
        assert provenance[field_path]["validation_status"] == "verified"


def test_assembler_is_deterministic_for_same_context() -> None:
    context = ReviewDocumentContextFactory().create(_snapshot_from_golden())
    assembler_input = ReviewDocumentAssemblerInput(context=context, mode="approved")

    doc1 = ReviewDocumentAssembler().assemble(assembler_input).to_dict()
    doc2 = ReviewDocumentAssembler().assemble(assembler_input).to_dict()

    assert doc1["metadata"]["final_document_hash"].startswith("sha256:")
    assert doc1["metadata"]["final_document_hash"] == doc2["metadata"]["final_document_hash"]

    raw1 = json.dumps(doc1, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw2 = json.dumps(doc2, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(raw1.encode("utf-8")).hexdigest() == hashlib.sha256(raw2.encode("utf-8")).hexdigest()


def test_empty_context_is_blocked_not_ready() -> None:
    context = ReviewDocumentContext(
        trade_date="2026-07-09",
        metadata={},
        market_context=MarketContext(),
        emotion_context=EmotionContext(),
        theme_context=ThemeContext(),
        capital_context=CapitalContext(),
        stock_context=StockContext(),
        plan_context=PlanContext(),
        override_context=OverrideContext(),
    )

    document = ReviewDocumentAssembler().assemble(
        ReviewDocumentAssemblerInput(context=context, mode="draft")
    ).to_dict()

    assert document["quality"]["overall"] == SectionQualityStatus.BLOCKED.value
    assert document["quality"]["can_approve"] is False
    assert document["quality"]["sections"]["market"]["status"] == SectionQualityStatus.BLOCKED.value
    assert document["quality"]["sections"]["themes"]["status"] == SectionQualityStatus.BLOCKED.value
    assert document["quality"]["sections"]["capital"]["status"] == SectionQualityStatus.BLOCKED.value


def test_context_factory_accepts_workbench_draft_context_shape() -> None:
    snapshot = {
        "trade_date": "2026-07-09",
        "attention_state": {
            "review_document_context": {
                "trade_date": "2026-07-09",
                "market_state": {
                    "emotion_score": 39,
                    "facts": {
                        "limit_up_count": 75,
                        "limit_down_count": 29,
                        "up_count": 3561,
                        "down_count": 1609,
                    },
                },
                "themes": [
                    {"subject_key": "pcb", "theme_name": "PCB", "role": "MAINLINE", "stage": "承接"}
                ],
                "capital_state": {
                    "status": "derived_money_flow",
                    "top_stocks": [
                        {"theme_name": "PCB", "role_label": "机构", "stock_name": "测试股份"}
                    ],
                },
                "strong_stocks": [
                    {"stock_code": "000001.SZ", "stock_name": "测试股份", "theme_name": "PCB"}
                ],
            }
        },
        "emotion_review": {"phase": "REBOUND", "score": 39},
        "cognition_cards": [],
        "playbook": {"scenario": "REBOUND_ARBITRAGE"},
    }

    context = ReviewDocumentContextFactory().create(snapshot)
    document = ReviewDocumentAssembler().assemble(
        ReviewDocumentAssemblerInput(context=context, mode="draft")
    ).to_dict()

    assert document["market"]["limit_up_count"] == 75
    assert document["market"]["up_count"] == 3561
    assert document["capital"]["institution"][0]["theme_name"] == "PCB"
    assert document["themes"][0]["name"]["final_value"] == "PCB"
    assert document["quality"]["sections"]["market"]["status"] == SectionQualityStatus.READY.value


def test_assembler_output_has_no_legacy_or_formal_review() -> None:
    context = ReviewDocumentContextFactory().create(_snapshot_from_golden())
    document = ReviewDocumentAssembler().assemble(
        ReviewDocumentAssemblerInput(context=context, mode="approved")
    ).to_dict()

    serialized = json.dumps(document, ensure_ascii=False)
    for forbidden in ("formal_review", "legacy", "recap_doc", "emotion_review", "market_chart_reviews"):
        assert forbidden not in document
    for forbidden in ("formal_review", "legacy", "recap_doc"):
        assert forbidden not in serialized
