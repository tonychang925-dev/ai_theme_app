"""PR4.2.31f Tushare Moneyflow Evidence Adapter — Contract Tests.

Verify all 6 acceptance contracts:
  C1: Unit conversion (万元 → 元)
  C2: No recomputation of net_mf_amount from buckets
  C3: No forbidden fields (institution, hot_money, smart_money, main_force)
  C4: Evidence replayable (same input → same output)
  C5: Semantic metadata (order_size_flow, not_owner_identity)
  C6: Source provenance (source_name, source_version, collected_at)
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "tushare_moneyflow.py"
)
SQL_PATH = PROJECT_ROOT / "database_service" / "scripts" / "create_stock_fund_flow_daily.sql"

# ── Sample Tushare moneyflow API row for 300223.SZ on 2026-07-09 ──

SAMPLE_ROW: dict = {
    "ts_code": "300223.SZ",
    "trade_date": "20260709",
    "buy_elg_amount": 223664.99,
    "sell_elg_amount": 219924.16,
    "buy_elg_vol": 97267,
    "sell_elg_vol": 96036,
    "buy_lg_amount": 285301.67,
    "sell_lg_amount": 280688.43,
    "buy_lg_vol": 124317,
    "sell_lg_vol": 122228,
    "buy_md_amount": 285636.78,
    "sell_md_amount": 313053.66,
    "buy_md_vol": 124459,
    "sell_md_vol": 136301,
    "buy_sm_amount": 182330.80,
    "sell_sm_amount": 163268.01,
    "buy_sm_vol": 79497,
    "sell_sm_vol": 70975,
    "net_mf_amount": 54615.01,
    "net_mf_vol": 23609,
}


@pytest.fixture
def normalizer():
    from stock_processing_service.application.services.capital_evidence.tushare_moneyflow import (
        TushareMoneyflowNormalizer,
    )
    return TushareMoneyflowNormalizer()


def _row_to_hash(evidence) -> str:
    """Stable hash of normalized evidence for replay comparison."""
    payload = evidence.to_row()
    # Remove non-deterministic fields before hashing
    payload.pop("collected_at", None)
    payload.pop("diagnostics", None)
    payload.pop("raw_json", None)
    # Convert date objects to ISO string for JSON serialization
    payload["trade_date"] = (
        payload["trade_date"].isoformat()
        if hasattr(payload["trade_date"], "isoformat")
        else str(payload["trade_date"])
    )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════
# C1: Unit conversion — 万元 → 元
# ═══════════════════════════════════════════════════════════════

class TestC1UnitConversion:
    """C1: Tushare 54615.01 万元 → DB 546150100 元."""

    def test_net_mf_amount_converted_from_wan_to_yuan(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)

        # 54615.01 万元 × 10000 = 546150100 元
        assert evidence.order_size_flow_amount_yuan == 546150100.00

    def test_bucket_amounts_converted_from_wan_to_yuan(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)

        # 223664.99 万元 → 2236649900.00 元
        assert evidence.buy_elg_amount_yuan == 2236649900.00
        assert evidence.sell_elg_amount_yuan == 2199241600.00

    def test_null_amount_stays_null(self, normalizer):
        row = {**SAMPLE_ROW, "net_mf_amount": None}
        evidence = normalizer.normalize_row(row)
        assert evidence.order_size_flow_amount_yuan is None

    def test_vol_fields_preserved_as_is(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.buy_elg_vol_shou == 97267.0
        assert evidence.sell_elg_vol_shou == 96036.0


# ═══════════════════════════════════════════════════════════════
# C2: No recomputation of net_mf_amount from buckets
# ═══════════════════════════════════════════════════════════════

class TestC2NoRecomputation:
    """C2: net_amount != sum(bucket buys - bucket sells)."""

    def test_normalizer_does_not_recompute_net_from_buckets(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)

        # If we naively summed bucket nets:
        bucket_net = (
            (evidence.buy_elg_amount_yuan or 0) - (evidence.sell_elg_amount_yuan or 0)
            + (evidence.buy_lg_amount_yuan or 0) - (evidence.sell_lg_amount_yuan or 0)
            + (evidence.buy_md_amount_yuan or 0) - (evidence.sell_md_amount_yuan or 0)
            + (evidence.buy_sm_amount_yuan or 0) - (evidence.sell_sm_amount_yuan or 0)
        )
        # The L2-based net is different from the naive sum
        assert evidence.order_size_flow_amount_yuan != bucket_net

    def test_normalizer_source_code_has_no_bucket_sum_logic(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        # Must not contain any expression that sums buy - sell across buckets
        forbidden_patterns = [
            "buy_elg + buy_lg + buy_md + buy_sm - sell_elg - sell_lg - sell_md - sell_sm",
        ]
        for pattern in forbidden_patterns:
            pattern_compact = pattern.replace(" ", "")
            source_compact = source.replace(" ", "").replace("\n", "")
            assert pattern_compact not in source_compact, f"Forbidden recomputation: {pattern}"


# ═══════════════════════════════════════════════════════════════
# C3: No forbidden fields
# ═══════════════════════════════════════════════════════════════

class TestC3ForbiddenFields:
    """C3: Zero occurrences of institution, hot_money, smart_money, main_force."""

    FORBIDDEN = ("institution", "hot_money", "smart_money", "main_force")

    def test_evidence_dataclass_has_no_forbidden_fields(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        import ast
        tree = ast.parse(source)
        # Extract all field names and variable assignments from the module
        field_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                field_names.add(node.target.id)
            if isinstance(node, ast.FunctionDef):
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                field_names.add(target.id)
                            elif isinstance(target, ast.Attribute):
                                field_names.add(target.attr)
        # Forbidden words must not appear as field/variable names
        for word in self.FORBIDDEN:
            for name in field_names:
                assert word not in name.lower(), (
                    f"Forbidden term '{word}' found in field/variable: '{name}'"
                )

    def test_evidence_row_dict_has_no_forbidden_keys(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        row = evidence.to_row()
        for key in row:
            for word in self.FORBIDDEN:
                assert word not in key.lower(), f"Forbidden term in field name: {key}"


# ═══════════════════════════════════════════════════════════════
# C4: Evidence replayable
# ═══════════════════════════════════════════════════════════════

class TestC4Replayable:
    """C4: Same (trade_date, ts_code) → same snapshot every time."""

    def test_same_input_produces_same_output(self, normalizer):
        e1 = normalizer.normalize_row(SAMPLE_ROW)
        e2 = normalizer.normalize_row(SAMPLE_ROW)
        assert _row_to_hash(e1) == _row_to_hash(e2)

    def test_different_inputs_produce_different_outputs(self, normalizer):
        e1 = normalizer.normalize_row(SAMPLE_ROW)
        e2 = normalizer.normalize_row({**SAMPLE_ROW, "net_mf_amount": 99999.99})
        assert _row_to_hash(e1) != _row_to_hash(e2)


# ═══════════════════════════════════════════════════════════════
# C5: Semantic metadata
# ═══════════════════════════════════════════════════════════════

class TestC5SemanticMetadata:
    """C5: Every row carries semantic_type: order_size_flow, not_owner_identity: true."""

    def test_evidence_carries_semantic_type(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.semantic_type == "order_size_flow"

    def test_evidence_carries_not_owner_identity(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.not_owner_identity is True

    def test_to_row_includes_semantic_metadata(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        row = evidence.to_row()
        assert row["semantic_type"] == "order_size_flow"
        assert row["not_owner_identity"] is True

    def test_diagnostics_declares_identity_inference_false(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.diagnostics["identity_inference"] is False
        assert evidence.diagnostics["participant_type"] == "unknown"


# ═══════════════════════════════════════════════════════════════
# C6: Source provenance
# ═══════════════════════════════════════════════════════════════

class TestC6SourceProvenance:
    """C6: Every row carries source_name, source_version, collected_at."""

    def test_evidence_carries_source_name(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.source_name == "tushare"

    def test_evidence_carries_source_endpoint(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.source_endpoint == "moneyflow"

    def test_evidence_carries_source_version(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.source_version == "tushare_moneyflow_v1"

    def test_evidence_carries_collected_at(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        assert evidence.collected_at
        assert "T" in evidence.collected_at  # ISO 8601

    def test_to_row_includes_all_provenance_fields(self, normalizer):
        evidence = normalizer.normalize_row(SAMPLE_ROW)
        row = evidence.to_row()
        assert row["source_name"] == "tushare"
        assert row["source_endpoint"] == "moneyflow"
        assert row["source_version"] == "tushare_moneyflow_v1"
        assert "T" in row["collected_at"]


# ═══════════════════════════════════════════════════════════════
# DB schema contract
# ═══════════════════════════════════════════════════════════════

class TestDBSchema:
    """Verify stock_fund_flow_daily table schema matches the evidence contract."""

    def test_sql_file_exists(self):
        assert SQL_PATH.exists(), f"Missing: {SQL_PATH}"

    def test_table_has_buy_sell_direction_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "buy_elg_amount_yuan" in sql
        assert "sell_elg_amount_yuan" in sql
        assert "buy_lg_amount_yuan" in sql
        assert "sell_lg_amount_yuan" in sql

    def test_table_has_order_size_flow_not_net_amount(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "order_size_flow_amount_yuan" in sql
        # Must NOT use misleading field names
        assert "net_amount_yuan" not in sql
        assert "main_force" not in sql.lower()

    def test_table_has_source_provenance_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "source_name" in sql
        assert "source_version" in sql
        assert "collected_at" in sql

    def test_table_has_semantic_metadata_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "semantic_type" in sql
        assert "not_owner_identity" in sql

    def test_table_has_unique_identity_constraint(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "uq_stock_fund_flow_daily_identity" in sql
        assert "PRIMARY KEY" in sql
