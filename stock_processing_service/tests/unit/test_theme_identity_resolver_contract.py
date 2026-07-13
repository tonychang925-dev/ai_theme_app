"""ThemeIdentityResolver contract tests."""

from __future__ import annotations

import ast
from pathlib import Path

from stock_processing_service.application.services.identity import (
    RawThemeIdentity,
    ThemeIdentityResolver,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESOLVER_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "identity"
    / "theme_identity_resolver.py"
)


def test_theme_identity_resolver_maps_explicit_name_only() -> None:
    identity = ThemeIdentityResolver().resolve(
        RawThemeIdentity(subject_key="9055378", theme_name="存储芯片")
    )

    assert identity.subject_key == "9055378"
    assert identity.canonical_name == "存储芯片"
    assert identity.entity_type == "A_SHARE_THEME"
    assert identity.identity_source == "input.theme_name"
    assert identity.confidence == 1.0


def test_theme_identity_resolver_uses_cognition_card_lookup() -> None:
    identity = ThemeIdentityResolver().resolve(
        RawThemeIdentity(subject_key="9014001"),
        [{"subject_id": "9014001", "subject_name": "人形机器人", "_identity_source": "cognition_cards"}],
    )

    assert identity.subject_key == "9014001"
    assert identity.canonical_name == "人形机器人"
    assert identity.identity_source == "cognition_cards.subject_name"
    assert identity.confidence == 1.0


def test_theme_identity_resolver_marks_subject_name_source() -> None:
    identity = ThemeIdentityResolver().resolve(
        RawThemeIdentity(subject_key="9014001", subject_name="人形机器人")
    )

    assert identity.canonical_name == "人形机器人"
    assert identity.identity_source == "input.subject_name"


def test_theme_identity_resolver_does_not_use_subject_key_as_name() -> None:
    identity = ThemeIdentityResolver().resolve(RawThemeIdentity(subject_key="9018144"))

    assert identity.subject_key == "9018144"
    assert identity.canonical_name is None
    assert identity.identity_source is None
    assert identity.confidence == 0.0


def test_theme_identity_resolver_rejects_scraped_driver_text_as_name() -> None:
    identity = ThemeIdentityResolver().resolve(
        RawThemeIdentity(
            subject_key="9069479",
            theme_name="【驱动事件：7月9日连板复盘】7月9日连板复盘\n行情报价\n题材库\n自选股",
        )
    )

    assert identity.subject_key == "9069479"
    assert identity.canonical_name is None
    assert identity.identity_source is None
    assert identity.confidence == 0.0


def test_theme_identity_resolver_enriches_theme_rows_before_assembler() -> None:
    rows = ThemeIdentityResolver().resolve_theme_rows(
        [{"subject_key": "9055378", "role": "MAINLINE"}],
        [{"subject_id": "9055378", "subject_name": "存储芯片"}],
    )

    assert rows == [
        {
            "subject_key": "9055378",
            "theme_name": "存储芯片",
            "role": "MAINLINE",
            "theme_identity": {
                "subject_key": "9055378",
                "canonical_name": "存储芯片",
                "entity_type": "A_SHARE_THEME",
                "identity_source": "cognition_cards.subject_name",
                "confidence": 1.0,
            },
        }
    ]


def test_theme_identity_resolver_removes_invalid_theme_name_from_rows() -> None:
    rows = ThemeIdentityResolver().resolve_theme_rows(
        [
            {
                "subject_key": "9069479",
                "theme_name": "【驱动事件：7月9日热门题材复盘】7月9日热门题材复盘\n系统设置\n全部A股",
                "role": "MAINLINE",
            }
        ],
        [],
    )

    assert rows == [
        {
            "subject_key": "9069479",
            "role": "MAINLINE",
            "theme_identity": {
                "subject_key": "9069479",
                "canonical_name": None,
                "entity_type": "A_SHARE_THEME",
                "identity_source": None,
                "confidence": 0.0,
            },
        }
    ]


def test_theme_identity_resolver_has_no_business_judgement_terms() -> None:
    tree = ast.parse(RESOLVER_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "rank",
        "classify",
        "classification",
        "strength",
        "hot",
        "weak",
        "tradable",
        "priority",
    }
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            lowered = node.name.lower()
            hits.extend(term for term in forbidden if term in lowered)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            hits.extend(term for term in forbidden if term in lowered)

    assert not hits
