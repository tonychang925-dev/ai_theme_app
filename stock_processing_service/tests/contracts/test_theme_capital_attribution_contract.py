"""PR4.2.32a Theme Capital Attribution Engine — Contract Tests.

Contracts verified:
  C1: Weight sum ≤ 1.0 per stock
  C2: Idempotent replay
  C3: PRIMARY priority (PRIMARY gets 0.60, RELATED splits 0.40)
  C6: No forbidden fields
  C8: Attribution conservation (Σ theme_flow ≈ Σ stock_flow)
  C9: Coverage transparency (flow_coverage_ratio populated)
"""

from __future__ import annotations

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
    / "theme_capital_attribution.py"
)
SQL_PATH = (
    PROJECT_ROOT
    / "database_service"
    / "scripts"
    / "create_theme_attribution_tables.sql"
)

# ── Sample data ──

SAMPLE_BINDINGS: list[dict] = [
    # 中科曙光 (603019.SH): 1 PRIMARY + 2 RELATED
    {"trade_date": "2026-07-09", "stock_code": "603019.SH", "subject_key": "9014001",
     "theme_name": "国产算力", "role": "PRIMARY"},
    {"trade_date": "2026-07-09", "stock_code": "603019.SH", "subject_key": "9023001",
     "theme_name": "液冷服务器", "role": "RELATED"},
    {"trade_date": "2026-07-09", "stock_code": "603019.SH", "subject_key": "9034501",
     "theme_name": "AI服务器", "role": "RELATED"},
    # 北京君正 (300223.SZ): 1 PRIMARY + 1 RELATED
    {"trade_date": "2026-07-09", "stock_code": "300223.SZ", "subject_key": "9015778",
     "theme_name": "存储芯片", "role": "PRIMARY"},
    {"trade_date": "2026-07-09", "stock_code": "300223.SZ", "subject_key": "9045601",
     "theme_name": "AI硬件", "role": "RELATED"},
    # 埃斯顿 (002747.SZ): no role flag → equal split
    {"trade_date": "2026-07-09", "stock_code": "002747.SZ", "subject_key": "9014636",
     "theme_name": "人形机器人", "role": ""},
    {"trade_date": "2026-07-09", "stock_code": "002747.SZ", "subject_key": "9056701",
     "theme_name": "工业自动化", "role": ""},
]

SAMPLE_FLOWS: list[dict] = [
    {"trade_date": "2026-07-09", "ts_code": "603019.SH",
     "order_size_flow_amount_yuan": 1000000000.00,   # +10亿
     "buy_lg_amount_yuan": 600000000.00, "sell_lg_amount_yuan": 200000000.00,
     "buy_elg_amount_yuan": 400000000.00, "sell_elg_amount_yuan": 100000000.00},
    {"trade_date": "2026-07-09", "ts_code": "300223.SZ",
     "order_size_flow_amount_yuan": 540000000.00,    # +5.4亿
     "buy_lg_amount_yuan": 300000000.00, "sell_lg_amount_yuan": 100000000.00,
     "buy_elg_amount_yuan": 250000000.00, "sell_elg_amount_yuan": 50000000.00},
    {"trade_date": "2026-07-09", "ts_code": "002747.SZ",
     "order_size_flow_amount_yuan": -200000000.00,   # -2亿
     "buy_lg_amount_yuan": 100000000.00, "sell_lg_amount_yuan": 150000000.00,
     "buy_elg_amount_yuan": 50000000.00, "sell_elg_amount_yuan": 50000000.00},
    # Unattributed: stock with flow but no binding
    {"trade_date": "2026-07-09", "ts_code": "000566.SZ",
     "order_size_flow_amount_yuan": 50000000.00,
     "buy_lg_amount_yuan": 30000000.00, "sell_lg_amount_yuan": 10000000.00,
     "buy_elg_amount_yuan": 20000000.00, "sell_elg_amount_yuan": 10000000.00},
]


@pytest.fixture
def resolver():
    from stock_processing_service.application.services.capital_evidence.theme_capital_attribution import (
        StockThemeWeightResolver,
    )
    return StockThemeWeightResolver()


@pytest.fixture
def engine():
    from stock_processing_service.application.services.capital_evidence.theme_capital_attribution import (
        ThemeCapitalAttributionEngine,
    )
    return ThemeCapitalAttributionEngine()


# ═══════════════════════════════════════════════════════════════
# C1: Weight sum ≤ 1.0 per stock
# ═══════════════════════════════════════════════════════════════

class TestC1WeightConstraint:
    """C1: SUM(weight) per stock ≤ 1.0."""

    def test_primary_related_split_sums_to_one(self, resolver):
        attributions = resolver.resolve(SAMPLE_BINDINGS)
        by_stock: dict[str, float] = {}
        for a in attributions:
            by_stock[a.stock_code] = by_stock.get(a.stock_code, 0.0) + a.weight

        for code, total in by_stock.items():
            assert 0.999 <= total <= 1.001, (
                f"Stock {code}: total weight = {total}, expected ~1.0"
            )

    def test_individual_weights_non_negative(self, resolver):
        attributions = resolver.resolve(SAMPLE_BINDINGS)
        for a in attributions:
            assert a.weight >= 0.0, f"Negative weight: {a.stock_code}/{a.subject_key} = {a.weight}"


# ═══════════════════════════════════════════════════════════════
# C2: Idempotent replay
# ═══════════════════════════════════════════════════════════════

class TestC2Idempotent:
    """C2: Same inputs → same outputs."""

    def test_resolver_is_deterministic(self, resolver):
        a1 = resolver.resolve(SAMPLE_BINDINGS)
        a2 = resolver.resolve(SAMPLE_BINDINGS)
        assert len(a1) == len(a2)
        for x, y in zip(a1, a2):
            assert x.weight == y.weight
            assert x.subject_key == y.subject_key

    def test_engine_is_deterministic(self, resolver, engine):
        attrs = resolver.resolve(SAMPLE_BINDINGS)
        t1, u1 = engine.attribute(SAMPLE_FLOWS, attrs)
        t2, u2 = engine.attribute(SAMPLE_FLOWS, attrs)
        assert len(t1) == len(t2)
        for x, y in zip(t1, t2):
            assert x.net_flow_yuan == y.net_flow_yuan
            assert x.subject_key == y.subject_key
        assert len(u1) == len(u2)
        for x, y in zip(u1, u2):
            assert x.stock_code == y.stock_code
            assert x.net_flow_yuan == y.net_flow_yuan


# ═══════════════════════════════════════════════════════════════
# C3: PRIMARY priority
# ═══════════════════════════════════════════════════════════════

class TestC3PrimaryPriority:
    """C3: PRIMARY gets 0.60, RELATED splits remaining 0.40."""

    def test_primary_gets_60_pct(self, resolver):
        attributions = resolver.resolve(SAMPLE_BINDINGS)
        # 中科曙光: 1 PRIMARY + 2 RELATED
        zg = [a for a in attributions if a.stock_code == "603019.SH"]
        primary = [a for a in zg if a.weight > 0.5]
        related = [a for a in zg if a.weight < 0.5]

        assert len(primary) == 1
        assert primary[0].weight == 0.60
        assert primary[0].subject_key == "9014001"
        assert len(related) == 2
        for r in related:
            assert r.weight == 0.20

    def test_no_role_falls_back_to_equal_split(self, resolver):
        attributions = resolver.resolve(SAMPLE_BINDINGS)
        # 埃斯顿: no role → equal split
        ast = [a for a in attributions if a.stock_code == "002747.SZ"]
        assert len(ast) == 2
        for a in ast:
            assert a.weight == 0.50


# ═══════════════════════════════════════════════════════════════
# C6: No forbidden fields
# ═══════════════════════════════════════════════════════════════

class TestC6ForbiddenFields:
    """C6: Zero occurrences of institution, hot_money, main_force."""

    FORBIDDEN = ("institution", "hot_money", "main_force")

    def test_module_has_no_forbidden_terms(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        import ast
        tree = ast.parse(source)
        field_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                field_names.add(node.target.id)
        for word in self.FORBIDDEN:
            for name in field_names:
                assert word not in name.lower(), f"Forbidden '{word}' in field: {name}"


# ═══════════════════════════════════════════════════════════════
# C8: Attribution conservation
# ═══════════════════════════════════════════════════════════════

class TestC8Conservation:
    """C8: ABS(SUM(theme_flow) - SUM(stock_flow)) < epsilon."""

    def test_money_is_conserved(self, resolver, engine):
        attrs = resolver.resolve(SAMPLE_BINDINGS)
        theme_flows, unattributed = engine.attribute(SAMPLE_FLOWS, attrs)

        total_stock_flow = sum(
            f["order_size_flow_amount_yuan"] for f in SAMPLE_FLOWS
            if f.get("order_size_flow_amount_yuan") is not None
        )
        total_theme_flow = sum(
            (tf.net_flow_yuan or 0.0) for tf in theme_flows
        )
        total_unattributed = sum(
            (u.net_flow_yuan or 0.0) for u in unattributed
        )

        total_output = total_theme_flow + total_unattributed
        epsilon = 1e-6 * abs(total_stock_flow) + 0.01  # float tolerance

        assert abs(total_output - total_stock_flow) < epsilon, (
            f"Conservation violation: stock={total_stock_flow}, "
            f"theme={total_theme_flow}, unattributed={total_unattributed}, "
            f"diff={abs(total_output - total_stock_flow)}"
        )

    def test_unattributed_stocks_are_tracked(self, resolver, engine):
        attrs = resolver.resolve(SAMPLE_BINDINGS)
        _, unattributed = engine.attribute(SAMPLE_FLOWS, attrs)

        # 000566.SZ has flow but no binding → must be in unattributed
        codes = {u.stock_code for u in unattributed}
        assert "000566.SZ" in codes
        u = next(u for u in unattributed if u.stock_code == "000566.SZ")
        assert u.reason == "no_theme_binding"


# ═══════════════════════════════════════════════════════════════
# C9: Coverage transparency
# ═══════════════════════════════════════════════════════════════

class TestC9CoverageTransparency:
    """C9: Every theme_flow has flow_coverage_ratio populated."""

    def test_all_theme_flows_have_coverage(self, resolver, engine):
        attrs = resolver.resolve(SAMPLE_BINDINGS)
        theme_flows, _ = engine.attribute(SAMPLE_FLOWS, attrs)

        for tf in theme_flows:
            assert tf.flow_coverage_ratio >= 0.0
            assert tf.attributed_stock_count > 0
            assert tf.stock_count > 0

    def test_positive_stock_count_is_reasonable(self, resolver, engine):
        attrs = resolver.resolve(SAMPLE_BINDINGS)
        theme_flows, _ = engine.attribute(SAMPLE_FLOWS, attrs)

        for tf in theme_flows:
            assert tf.positive_stock_count <= tf.attributed_stock_count


# ═══════════════════════════════════════════════════════════════
# DB schema contract
# ═══════════════════════════════════════════════════════════════

class TestDBSchema:
    """Verify attribution tables match design spec."""

    def test_sql_file_exists(self):
        assert SQL_PATH.exists(), f"Missing: {SQL_PATH}"

    def test_attribution_table_has_weight_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "weight" in sql
        assert "attribution_version" in sql
        assert "confidence" in sql
        assert "PRIMARY KEY (trade_date, stock_code, subject_key, attribution_version)" in sql

    def test_flow_table_has_coverage_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "flow_coverage_ratio" in sql
        assert "attributed_stock_count" in sql
        assert "flow_type" in sql
        assert "ATTRIBUTED_ORDER_FLOW" in sql

    def test_unattributed_table_exists(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        assert "unattributed_capital_daily" in sql
        assert "reason" in sql
