"""PR4.2.37a — 2026-07-09 Golden UI Validation.

Locks assertions for Capital Intelligence pipeline end-to-end:
  - Producer → ReviewDocument → Workspace JSON → Frontend Props

Deprecated fields (institution[], hot_money[]) must remain for 30-day
compatibility period but must NOT be the active render source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RD_PATH = PROJECT_ROOT / "tmp" / "analyst_workbench" / "2026-07-09" / "review_document.json"


@pytest.fixture
def capital():
    """Load 7/09 review_document.json capital section."""
    import asyncio
    sys.path.insert(0, str(PROJECT_ROOT))
    from stock_processing_service.api_app import _inject_capital_producer_outputs_async

    if RD_PATH.exists():
        with open(RD_PATH) as f:
            doc = json.load(f)
    else:
        doc = {"metadata": {"trade_date": "2026-07-09"}, "capital": {}}

    result = asyncio.run(_inject_capital_producer_outputs_async(doc))
    return result.get("capital", {})


# ═══════════════════════════════════════════════════════════════
# Producer output assertions
# ═══════════════════════════════════════════════════════════════

class TestProducerOutput:
    def test_institution_style_has_4_rows(self, capital):
        assert len(capital.get("institution_style", [])) == 4

    def test_hot_money_style_has_15_rows(self, capital):
        assert len(capital.get("hot_money_style", [])) == 15

    def test_institution_rows_have_direction_name(self, capital):
        for r in capital["institution_style"]:
            assert r.get("direction_name"), f"Missing direction_name in {r}"

    def test_institution_rows_have_score_and_confidence(self, capital):
        for r in capital["institution_style"]:
            assert r.get("score") is not None
            assert r.get("confidence") is not None

    def test_institution_rows_have_lifecycle_stage(self, capital):
        for r in capital["institution_style"]:
            assert r.get("lifecycle_stage") is not None

    def test_institution_sorted_by_score_desc(self, capital):
        scores = [r["score"] for r in capital["institution_style"]]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not sorted: {scores[i]} < {scores[i+1]}"

    def test_hot_money_rows_have_theme_name(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("theme_name")

    def test_hot_money_rows_have_attack_stage(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("attack_stage") in ("FIRST_WAVE", "CONTINUING", "CLIMAX", "RETREATING")

    def test_hot_money_rows_have_institution_relation(self, capital):
        for r in capital["hot_money_style"]:
            assert r.get("institution_hot_relation") in (
                "BOTH", "INSTITUTION_ONLY", "HOT_MONEY_ONLY", "DIVERGENCE"
            )


# ═══════════════════════════════════════════════════════════════
# Render source assertions
# ═══════════════════════════════════════════════════════════════

class TestRenderSource:
    def test_render_source_is_canonical(self, capital):
        rs = capital.get("capital_render_source", {})
        assert rs.get("institution") == "institution_style"
        assert rs.get("hot_money") == "hot_money_style"

    def test_fallback_not_used(self, capital):
        rs = capital.get("capital_render_source", {})
        assert rs.get("fallback_used") == False, (
            "DEPRECATED FIELDS ARE BEING RENDERED — investigation required"
        )

    def test_deprecated_fields_still_present_for_compatibility(self, capital):
        """Old fields must exist during 30-day deprecation window."""
        assert "institution" in capital, "Deprecated field removed too early"
        assert "hot_money" in capital, "Deprecated field removed too early"


# ═══════════════════════════════════════════════════════════════
# Data quality assertions
# ═══════════════════════════════════════════════════════════════

class TestDataQuality:
    def test_no_numeric_ids_as_names(self, capital):
        for r in capital["institution_style"]:
            name = r.get("direction_name", "")
            assert not name.isdigit(), f"Numeric ID leaked: {name}"

        for r in capital["hot_money_style"]:
            name = r.get("theme_name", "")
            assert not name.isdigit(), f"Numeric ID leaked: {name}"

    def test_scores_in_valid_range(self, capital):
        for r in capital["institution_style"]:
            assert 0 <= r["score"] <= 100, f"Score out of range: {r['score']}"
        for r in capital["hot_money_style"]:
            assert 0 <= r["score"] <= 100, f"Score out of range: {r['score']}"

    def test_confidence_in_valid_range(self, capital):
        for r in capital["institution_style"]:
            assert 0 <= r["confidence"] <= 1, f"Confidence out of range: {r['confidence']}"
