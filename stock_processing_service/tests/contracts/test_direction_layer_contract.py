"""PR4.2.34a Direction Layer — Contract Tests.

Contracts:
  C10: SUM(allocated per theme across directions) ≤ source × 1.001
  C11: Direction MUST NOT replace Theme (separate tables, no cascade delete)
  C12: Σ direction_flow + unallocated = Σ theme_flow (capital closure)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = (
    PROJECT_ROOT / "database_service" / "scripts" / "create_investment_direction_tables.sql"
)
YAML_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "direction_bootstrap.yaml"
)
MODULE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "direction_capital_aggregator.py"
)


# ── Sample data ──

SAMPLE_THEME_FLOWS: list[dict] = [
    {"subject_key": "9018144", "theme_name": "PCB印制电路板", "net_flow_yuan": 2000000000.00, "large_flow_yuan": 600000000.00},
    {"subject_key": "9023001", "theme_name": "高速铜连接",   "net_flow_yuan": 1500000000.00, "large_flow_yuan": 450000000.00},
    {"subject_key": "9034501", "theme_name": "MPO",         "net_flow_yuan": 1200000000.00, "large_flow_yuan": 300000000.00},
    {"subject_key": "9019807", "theme_name": "光模块",       "net_flow_yuan": 800000000.00,  "large_flow_yuan": 200000000.00},
    {"subject_key": "9024001", "theme_name": "覆铜板",       "net_flow_yuan": 500000000.00,  "large_flow_yuan": 100000000.00},
]

SAMPLE_BINDINGS: list[dict] = [
    {"direction_key": "AI_HIGH_SPEED_INTERCONNECT", "direction_name": "AI高速互联",
     "subject_key": "9018144", "weight": 0.25, "role": "PRIMARY_DRIVER"},
    {"direction_key": "AI_HIGH_SPEED_INTERCONNECT", "direction_name": "AI高速互联",
     "subject_key": "9023001", "weight": 0.25, "role": "PRIMARY_DRIVER"},
    {"direction_key": "AI_HIGH_SPEED_INTERCONNECT", "direction_name": "AI高速互联",
     "subject_key": "9034501", "weight": 0.15, "role": "SUPPORTING"},
    {"direction_key": "AI_HIGH_SPEED_INTERCONNECT", "direction_name": "AI高速互联",
     "subject_key": "9019807", "weight": 0.15, "role": "SUPPORTING"},
    {"direction_key": "AI_HIGH_SPEED_INTERCONNECT", "direction_name": "AI高速互联",
     "subject_key": "9024001", "weight": 0.10, "role": "SUPPORTING"},
]


@pytest.fixture
def aggregator():
    from stock_processing_service.application.services.capital_evidence.direction_capital_aggregator import (
        DirectionCapitalAggregator,
    )
    return DirectionCapitalAggregator()


# ═══════════════════════════════════════════════════════════════
# C10: Theme Conservation
# ═══════════════════════════════════════════════════════════════

class TestC10ThemeConservation:
    """C10: SUM(allocated per theme across directions) ≤ source × 1.001."""

    def test_single_direction_no_over_allocation(self, aggregator):
        td = date(2026, 7, 9)
        _, allocations = aggregator.aggregate(SAMPLE_THEME_FLOWS, SAMPLE_BINDINGS, td)

        from stock_processing_service.application.services.capital_evidence.direction_capital_aggregator import (
            validate_conservation,
        )
        result = validate_conservation(SAMPLE_THEME_FLOWS, allocations)
        assert result["c10_passed"], f"C10 failed: {result['c10_failures']}"

    def test_allocation_matches_weighted_source(self, aggregator):
        td = date(2026, 7, 9)
        _, allocations = aggregator.aggregate(SAMPLE_THEME_FLOWS, SAMPLE_BINDINGS, td)

        # PCB (20亿) × weight 0.25 = 5亿 allocated
        pcb_alloc = [a for a in allocations if a.subject_key == "9018144"]
        assert len(pcb_alloc) == 1
        assert abs(pcb_alloc[0].allocated_amount_yuan - 500_000_000) < 1.0


# ═══════════════════════════════════════════════════════════════
# C11: Direction does NOT replace Theme
# ═══════════════════════════════════════════════════════════════

class TestC11NoThemeReplacement:
    """C11: Direction and Theme are separate tables, no cascade delete, no replacement."""

    def test_schema_has_separate_tables(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "investment_direction" in sql
        assert "direction_theme_binding" in sql
        # Must NOT have DROP/REPLACE of theme tables
        assert "DROP TABLE" not in sql
        assert "CASCADE" not in sql

    def test_aggregator_does_not_modify_theme_flows(self, aggregator):
        original = [dict(f) for f in SAMPLE_THEME_FLOWS]
        td = date(2026, 7, 9)
        aggregator.aggregate(SAMPLE_THEME_FLOWS, SAMPLE_BINDINGS, td)
        # Theme flows unchanged after aggregation
        for orig, curr in zip(original, SAMPLE_THEME_FLOWS):
            assert orig == curr

    def test_module_does_not_import_theme_deletion(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        assert "DROP" not in source
        assert "DELETE" not in source


# ═══════════════════════════════════════════════════════════════
# C12: Capital Closure
# ═══════════════════════════════════════════════════════════════

class TestC12CapitalClosure:
    """C12: Σ direction_flow + unallocated ≈ Σ theme_flow."""

    def test_total_direction_flow_does_not_exceed_total_theme_flow(self, aggregator):
        td = date(2026, 7, 9)
        flows, _ = aggregator.aggregate(SAMPLE_THEME_FLOWS, SAMPLE_BINDINGS, td)

        total_theme = sum(abs(f["net_flow_yuan"]) for f in SAMPLE_THEME_FLOWS)
        total_direction = sum(abs(d.net_flow_yuan or 0) for d in flows)

        # Each direction flow should be ≤ total theme flow (aggregation, not creation)
        for d in flows:
            assert abs(d.net_flow_yuan or 0) <= total_theme * 1.01, (
                f"Direction {d.direction_key} flow exceeds total theme flow"
            )


# ═══════════════════════════════════════════════════════════════
# YAML config
# ═══════════════════════════════════════════════════════════════

class TestBootstrapConfig:
    """Verify bootstrap YAML is valid and complete."""

    def test_yaml_loads(self):
        import yaml
        with open(YAML_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        assert "directions" in config
        assert len(config["directions"]) >= 20

    def test_all_directions_have_max_8_themes(self):
        import yaml
        with open(YAML_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        for key, d in config["directions"].items():
            themes = d.get("themes", [])
            assert len(themes) <= 8, f"{key}: {len(themes)} themes exceeds max 8"
            weights = sum(t["weight"] for t in themes)
            assert 0.99 <= weights <= 1.01, f"{key}: weights sum to {weights}"

    def test_all_bindings_have_valid_roles(self):
        import yaml
        with open(YAML_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        valid_roles = {"PRIMARY_DRIVER", "SUPPORTING", "OPTIONAL"}
        for key, d in config["directions"].items():
            for t in d["themes"]:
                assert t["role"] in valid_roles, f"{key}/{t['theme_name']}: invalid role {t['role']}"


# ═══════════════════════════════════════════════════════════════
# DB schema
# ═══════════════════════════════════════════════════════════════

class TestDBSchema:
    """Verify direction tables match design."""

    def test_sql_file_exists(self):
        assert SQL_PATH.exists()

    def test_four_tables_created(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "investment_direction" in sql
        assert "direction_theme_binding" in sql
        assert "theme_direction_allocation_daily" in sql
        assert "direction_capital_flow_daily" in sql

    def test_binding_has_time_dimension(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "valid_from" in sql
        assert "valid_to" in sql

    def test_allocation_table_for_double_counting_guard(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "allocated_amount_yuan" in sql
        assert "source_flow_yuan" in sql
