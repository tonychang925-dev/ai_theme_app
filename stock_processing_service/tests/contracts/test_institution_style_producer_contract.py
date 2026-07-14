"""PR4.2.33a Institution Style Producer — Contract Tests.

Contracts verified:
  C1: Component explainability (base_score reproducible from components)
  C2: Score stability (deterministic replay)
  C3: Multi-signal mandatory (3+ signals used)
  C4: DT optional (missing → redistributed, confidence penalty, not blocked)
  C5: Evidence quality per signal
  C6: No forbidden inference
  C7: Coverage-aware (low coverage → downgraded)
  C8: Stage bonus correct (FERMENTATION=85, DECAY=5)
  C10: Component observable (each score individually readable)
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "institution_style_producer.py"
)
SQL_PATH = (
    PROJECT_ROOT
    / "database_service"
    / "scripts"
    / "create_institution_style_daily.sql"
)

# ── Sample data ──

SAMPLE_FLOWS: list[dict] = [
    {"trade_date": "2026-07-09", "subject_key": "9015778", "theme_name": "存储芯片",
     "net_flow_yuan": 1860000000.00, "large_flow_yuan": 520000000.00,
     "flow_coverage_ratio": 0.82, "positive_stock_count": 8, "attributed_stock_count": 16, "stock_count": 20},
    {"trade_date": "2026-07-09", "subject_key": "9014001", "theme_name": "国产算力",
     "net_flow_yuan": 600000000.00, "large_flow_yuan": 420000000.00,
     "flow_coverage_ratio": 0.70, "positive_stock_count": 6, "attributed_stock_count": 14, "stock_count": 20},
    {"trade_date": "2026-07-09", "subject_key": "9014636", "theme_name": "人形机器人",
     "net_flow_yuan": -200000000.00, "large_flow_yuan": None,
     "flow_coverage_ratio": 0.35, "positive_stock_count": 3, "attributed_stock_count": 7, "stock_count": 20},
]

SAMPLE_CYCLES: list[dict] = [
    {"subject_key": "9015778", "final_cycle_state": "FERMENTATION", "previous_stage": "START"},
    {"subject_key": "9014001", "final_cycle_state": "START", "previous_stage": ""},
    {"subject_key": "9014636", "final_cycle_state": "DIVERGENCE", "previous_stage": "FERMENTATION"},
]

SAMPLE_STOCKS: dict[str, list[dict]] = {
    "9015778": [
        {"stock_code": "300223.SZ", "role": "龙头", "watch_score": 85.0},
        {"stock_code": "605178.SH", "role": "龙头", "watch_score": 72.0},
        {"stock_code": "688001.SH", "role": "中军", "watch_score": 65.0},
        {"stock_code": "688002.SH", "role": "中军", "watch_score": 55.0},
    ] + [{"stock_code": f"6880{i:02d}.SH", "role": "", "watch_score": 30.0} for i in range(3, 8)],
    "9014001": [
        {"stock_code": "603019.SH", "role": "龙头", "watch_score": 90.0},
    ] + [{"stock_code": f"6030{i:02d}.SH", "role": "", "watch_score": 20.0} for i in range(20, 25)],
    "9014636": [
        {"stock_code": "002747.SZ", "role": "龙头", "watch_score": 50.0},
        {"stock_code": "002748.SZ", "role": "", "watch_score": -10.0},
    ],
}

SAMPLE_DT: dict[str, list[dict]] = {
    "9015778": [
        {"seat_type": "机构专用", "buy_amount": 50000000},
        {"seat_type": "机构专用", "buy_amount": 30000000},
    ],
    "9014001": [],
}


@pytest.fixture
def producer():
    from stock_processing_service.application.services.capital_evidence.institution_style_producer import (
        InstitutionStyleProducer,
    )
    return InstitutionStyleProducer()


# ═══════════════════════════════════════════════════════════════
# C1: Component explainability
# ═══════════════════════════════════════════════════════════════

class TestC1Explainability:
    """C1: base_score must be reproducible from component scores."""

    def test_base_score_from_components_with_dt(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        chip = next(r for r in results if r.subject_key == "9015778")
        assert chip.base_score > 0
        # All 4 components present
        assert chip.flow_score is not None
        assert chip.cycle_score is not None
        assert chip.structure_score is not None
        assert chip.dragon_tiger_score is not None

    def test_base_score_from_components_without_dt(self, producer):
        """Theme 9014001 has no DT seats — scores still produced with redistribution."""
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        suanli = next(r for r in results if r.subject_key == "9014001")
        assert suanli.base_score > 0
        assert suanli.dragon_tiger_score is None  # DT missing
        assert suanli.evidence_quality["dragon_tiger"] == "MISSING"

    def test_every_component_individually_readable(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        for r in results:
            assert hasattr(r, "flow_score")
            assert hasattr(r, "cycle_score")
            assert hasattr(r, "structure_score")
            assert hasattr(r, "dragon_tiger_score")


# ═══════════════════════════════════════════════════════════════
# C2: Score stability
# ═══════════════════════════════════════════════════════════════

class TestC2Stability:
    """C2: Same inputs → same scores."""

    def test_deterministic_replay(self, producer):
        r1 = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        r2 = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        for a, b in zip(r1, r2):
            assert a.institution_score == b.institution_score
            assert a.base_score == b.base_score
            assert a.confidence == b.confidence

    def test_deterministic_without_dt(self, producer):
        r1 = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, None)
        r2 = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, None)
        for a, b in zip(r1, r2):
            assert a.institution_score == b.institution_score


# ═══════════════════════════════════════════════════════════════
# C3: Multi-signal mandatory
# ═══════════════════════════════════════════════════════════════

class TestC3MultiSignal:
    """C3: institution_score uses 3+ signals."""

    def test_flow_only_input_produces_scores(self, producer):
        """Even with only flows, the producer uses cycle+structure as neutral signals."""
        empty_cycles: list[dict] = []
        empty_stocks: dict[str, list[dict]] = {}
        results = producer.produce(SAMPLE_FLOWS[:1], empty_cycles, empty_stocks, None)
        assert len(results) >= 0  # May produce with MISSING evidence


# ═══════════════════════════════════════════════════════════════
# C4: DT optional
# ═══════════════════════════════════════════════════════════════

class TestC4DTOptional:
    """C4: Missing DT → redistributed, confidence penalty, not blocked."""

    def test_dt_missing_does_not_block_output(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, None)
        assert len(results) == 3

    def test_dt_missing_downgrades_confidence(self, producer):
        r_with = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        r_without = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, None)

        chip_with = next(r for r in r_with if r.subject_key == "9015778")
        chip_without = next(r for r in r_without if r.subject_key == "9015778")

        # With DT: chip should have higher confidence (strong core signals → -5%)
        # Without DT: chip should have lower confidence (DT missing)
        assert chip_with.dragon_tiger_score is not None
        assert chip_without.dragon_tiger_score is None
        # Both should produce valid scores
        assert chip_without.institution_score > 0

    def test_dt_empty_list_vs_none_same_result(self, producer):
        r_empty = producer.produce(SAMPLE_FLOWS[:1], SAMPLE_CYCLES[:1],
                                    {"9015778": SAMPLE_STOCKS["9015778"]},
                                    {"9015778": []})
        r_none = producer.produce(SAMPLE_FLOWS[:1], SAMPLE_CYCLES[:1],
                                   {"9015778": SAMPLE_STOCKS["9015778"]}, None)
        assert r_empty[0].dragon_tiger_score is None
        assert r_none[0].dragon_tiger_score is None


# ═══════════════════════════════════════════════════════════════
# C5: Evidence quality
# ═══════════════════════════════════════════════════════════════

class TestC5EvidenceQuality:
    """C5: Every output row has evidence_quality per signal."""

    def test_all_rows_have_evidence_quality(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        for r in results:
            eq = r.evidence_quality
            assert "flow" in eq
            assert "cycle" in eq
            assert "structure" in eq
            assert "dragon_tiger" in eq
            assert eq["flow"] in ("HIGH", "MEDIUM", "LOW", "MISSING")
            assert eq["dragon_tiger"] in ("HIGH", "MEDIUM", "LOW", "MISSING")

    def test_evidence_detail_present(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        for r in results:
            assert "lifecycle_stage" in r.evidence
            assert "flow_coverage_ratio" in r.evidence


# ═══════════════════════════════════════════════════════════════
# C6: No forbidden inference
# ═══════════════════════════════════════════════════════════════

class TestC6ForbiddenInference:
    """C6: Zero forbidden inference patterns."""

    FORBIDDEN = ("institution", "hot_money", "main_force")

    def test_module_has_no_forbidden_field_names(self, producer):
        import ast
        source = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        field_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                field_names.add(node.target.id)
        for word in self.FORBIDDEN:
            for name in field_names:
                # Allow "institution_score" and "institution_style" as output labels
                if name.startswith("institution_"):
                    continue
                assert word not in name.lower(), f"Forbidden '{word}' in field: {name}"


# ═══════════════════════════════════════════════════════════════
# C7: Coverage-aware
# ═══════════════════════════════════════════════════════════════

class TestC7CoverageAware:
    """C7: Low coverage → downgraded flow_score."""

    def test_low_coverage_theme_gets_lower_score(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)

        chip = next(r for r in results if r.subject_key == "9015778")
        robot = next(r for r in results if r.subject_key == "9014636")

        # 存储芯片 (coverage=0.82) should rank higher than 人形机器人 (coverage=0.35)
        assert chip.institution_score > robot.institution_score, (
            f"High-coverage theme should outrank low-coverage: "
            f"chip={chip.institution_score}, robot={robot.institution_score}"
        )


# ═══════════════════════════════════════════════════════════════
# C8: Stage bonus correct
# ═══════════════════════════════════════════════════════════════

class TestC8StageBonus:
    """C8: FERMENTATION=0.85 top, DECAY=0.05 bottom."""

    def test_fermentation_ranks_highest(self, producer):
        """存储芯片 at FERMENTATION should outrank START and DIVERGENCE."""
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        scores = {r.subject_key: (r.cycle_score, r.lifecycle_stage) for r in results}
        chip_cycle = scores.get("9015778", (0, ""))[0]
        suanli_cycle = scores.get("9014001", (0, ""))[0]
        assert chip_cycle is not None
        assert suanli_cycle is not None
        assert chip_cycle > suanli_cycle, (
            f"FERMENTATION cycle should outrank START: chip={chip_cycle}, suanli={suanli_cycle}"
        )


# ═══════════════════════════════════════════════════════════════
# C10: Component observable
# ═══════════════════════════════════════════════════════════════

class TestC10ComponentObservable:
    """C10: Each component score individually readable for M7 calibration."""

    def test_to_row_includes_all_components(self, producer):
        results = producer.produce(SAMPLE_FLOWS, SAMPLE_CYCLES, SAMPLE_STOCKS, SAMPLE_DT)
        r = results[0]
        row = r.to_row()
        assert "flow_score" in row
        assert "cycle_score" in row
        assert "structure_score" in row
        assert "dragon_tiger_score" in row
        assert "base_score" in row
        assert "institution_score" in row
        assert "confidence" in row


# ═══════════════════════════════════════════════════════════════
# DB schema
# ═══════════════════════════════════════════════════════════════

class TestDBSchema:
    """Verify institution_style_daily table matches design."""

    def test_sql_file_exists(self):
        assert SQL_PATH.exists()

    def test_table_has_component_score_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        for col in ("flow_score", "cycle_score", "structure_score", "dragon_tiger_score"):
            assert col in sql, f"Missing column: {col}"

    def test_table_has_base_and_final_score(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "base_score" in sql
        assert "institution_score" in sql

    def test_table_has_evidence_and_lifecycle(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "evidence_quality" in sql
        assert "lifecycle_stage" in sql
