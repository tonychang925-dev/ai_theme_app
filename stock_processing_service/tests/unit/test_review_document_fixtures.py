"""PR1.2 — ReviewDocument golden fixtures and negative cases.

These tests define what "correct" means before ContextFactory/Assembler exists.
They intentionally validate semantic fixtures, not generated ReviewDocuments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "review_document"


def _load_fixture(relative_path: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / relative_path
    return json.loads(path.read_text(encoding="utf-8"))


def test_20260709_golden_fixture_is_semantic_not_full_report() -> None:
    fixture = _load_fixture("2026-07-09-golden.json")

    assert fixture["fixture_type"] == "semantic_golden"
    assert fixture["trade_date"] == "2026-07-09"

    # Semantic golden: no full report blobs.
    assert "review_document" not in fixture
    assert "quality" not in fixture
    assert "source_refs" not in fixture
    assert "audit" not in fixture

    # It must stay compact enough to be manually reviewable.
    assert len(json.dumps(fixture, ensure_ascii=False)) < 3500


def test_20260709_golden_fixture_locks_core_market_emotion_and_override() -> None:
    fixture = _load_fixture("2026-07-09-golden.json")

    assert fixture["market"] == {
        "limit_up_count": 75,
        "limit_down_count": 29,
        "breadth": {
            "up_count": 3561,
            "down_count": 1609,
        },
    }
    assert fixture["emotion"] == {
        "phase": "REBOUND",
        "score": 39,
    }
    assert fixture["override"] == {
        "field": "themes.name",
        "ai_value": "人形机器人",
        "analyst_value": "PCB",
        "final_value": "PCB",
    }


def test_20260709_golden_fixture_locks_required_entities() -> None:
    fixture = _load_fixture("2026-07-09-golden.json")

    assert set(fixture["themes"]["must_include"]) >= {"PCB", "存储芯片", "机器人"}
    assert fixture["capital"]["institution_required"] is True
    assert fixture["capital"]["hot_money_required"] is True
    assert set(fixture["capital"]["institution_must_include"]) >= {"存储芯片", "半导体设备"}
    assert set(fixture["capital"]["hot_money_must_include"]) >= {"商业航天", "洪涝"}
    assert fixture["stocks"]["leader"] == {
        "stock_name": "恒尚节能",
        "board_height": 8,
    }


def test_20260709_golden_fixture_requires_core_field_provenance() -> None:
    fixture = _load_fixture("2026-07-09-golden.json")

    provenance = fixture["field_provenance_required"]
    required_fields = {
        "market.limit_up_count": "FACT",
        "emotion.score": "ASSESSMENT",
        "themes.primary": "IDENTITY",
    }
    assert set(provenance) == set(required_fields)

    for field_path, field_type in required_fields.items():
        item = provenance[field_path]
        assert item["source"]
        assert item["field_type"] == field_type
        assert item["source_trade_date"] == fixture["trade_date"]


def test_20260709_golden_fixture_is_review_document_not_snapshot() -> None:
    fixture = _load_fixture("2026-07-09-golden.json")

    forbidden_snapshot_lifecycle_fields = {
        "snapshot_hash",
        "approved_at",
        "approval_mode",
        "source_mode",
        "composition_mode",
        "snapshot_version",
    }
    serialized = json.dumps(fixture, ensure_ascii=False)
    for field_name in forbidden_snapshot_lifecycle_fields:
        assert field_name not in fixture
        assert field_name not in serialized


def test_negative_missing_capital_blocks_fake_ready_state() -> None:
    fixture = _load_fixture("negative/missing_capital.json")

    assert fixture["case"] == "missing_capital"
    assert fixture["input"]["capital"] == {"institution": [], "hot_money": []}
    assert fixture["expected"]["quality"]["overall"] == "BLOCKED"
    assert fixture["expected"]["quality"]["sections"]["capital"]["status"] == "MISSING"
    assert "quality.overall=READY" in fixture["forbidden_outputs"]
    assert any("共0个方向" in item for item in fixture["forbidden_outputs"])


def test_negative_stale_fact_blocks_cross_date_market_fact() -> None:
    fixture = _load_fixture("negative/stale_fact.json")

    assert fixture["case"] == "stale_fact"
    assert fixture["trade_date"] == "2026-07-09"
    assert fixture["input"]["market"]["source_trade_date"] == "2026-07-08"
    assert fixture["expected"]["quality"]["overall"] == "BLOCKED"
    assert fixture["expected"]["field_provenance"]["market.limit_up_count"]["validation_status"] == "invalid"


def test_negative_invalid_override_blocks_missing_final_value() -> None:
    fixture = _load_fixture("negative/invalid_override.json")

    override = fixture["input"]["override"]
    assert override["ai_value"] == "人形机器人"
    assert override["analyst_value"] == "PCB"
    assert override["final_value"] is None
    assert fixture["expected"]["quality"]["overall"] == "BLOCKED"
    assert fixture["expected"]["quality"]["reason"] == "explicit override final_value missing"


def test_negative_legacy_leakage_defines_api_contract_and_source_bans() -> None:
    fixture = _load_fixture("negative/legacy_leakage.json")

    assert fixture["case"] == "legacy_leakage"
    assert "review_document" in fixture["expected"]["api_contract"]["must_include"]
    assert set(fixture["expected"]["api_contract"]["must_not_include"]) >= {
        "formal_review",
        "legacy",
        "emotion_review",
        "market_chart_reviews",
    }
    assert set(fixture["forbidden_top_level_fields"]) >= {
        "formal_review",
        "legacy",
        "emotion_review",
        "market_chart_reviews",
        "recap_doc",
    }
    assert set(fixture["forbidden_source_terms"]) >= {
        "/api/emotion-",
        "/api/analyst-charts/",
        "recap_doc",
        "legacy",
    }
