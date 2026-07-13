"""PR4.2.30 Capital Intelligence source audit guard.

TC-ID: PR4.2.30-capital-intelligence-source-audit

This locks business semantics and source ownership before any producer is
implemented. It intentionally tests documentation, not production code.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Capital_Intelligence_Source_Audit.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_capital_intelligence_source_audit_document_exists() -> None:
    """TC-ID: PR4.2.30-source-audit-doc-exists."""
    assert DOC_PATH.exists()
    content = _doc()
    assert "PR4.2.30 Capital Intelligence Source Audit" in content
    assert "Audit Only" in content
    assert "ThemeCapitalIntelligenceProducer" in content
    assert "ShortTermCapitalProducer" in content
    assert "Data Source Capability Matrix" in content


def test_active_capital_is_frozen_and_separate_from_intelligence() -> None:
    """TC-ID: PR4.2.30-active-capital-layer-separation."""
    content = _doc()
    assert "PR4.2.28 Active Capital Recovery" in content
    assert "value_yi: 2664.84" in content
    assert "method: board_pool_zt_zb_v1" in content
    assert "Capital Intelligence is a separate interpretation layer" in content
    assert "These layers must not be merged" in content


def test_capital_data_layer_model_is_explicit() -> None:
    """TC-ID: PR4.2.30-capital-layer-model."""
    content = _doc()
    assert "Capital Evidence Layer" in content
    assert "Capital Intelligence Layer" in content
    assert "Capital Calibration Layer" in content
    assert "observable / vendor-defined facts" in content
    assert "analyst-style judgement" in content
    assert "truth label" in content


def test_data_source_capability_matrix_prioritizes_evidence_not_conclusions() -> None:
    """TC-ID: PR4.2.30-source-capability-matrix."""
    content = _doc()
    assert "individual stock fund flow" in content
    assert "Eastmoney fund flow via a-stock-data adapter" in content
    assert "concept/theme fund flow" in content
    assert "Eastmoney concept/theme fund flow via a-stock-data adapter" in content
    assert "dragon tiger" in content
    assert "analyst report" in content
    assert "never production fallback" in content


def test_institution_style_is_theme_intelligence_not_seat_rows() -> None:
    """TC-ID: PR4.2.30-institution-style-semantics."""
    content = _doc()
    assert "`capital.institution_style[]` | medium-term capital preference by industry/theme" in content
    assert "dragon-tiger institution seat rows" in content
    assert "theme_cycle_judgement_v2" in content
    assert "theme_strength_snapshot" in content
    assert "subject_daily_feature" in content
    assert "theme_capital_flow" in content
    assert "stock_fund_flow_snapshot" in content
    assert "theme_flow_snapshot" in content


def test_hot_money_style_is_short_attack_not_stock_role() -> None:
    """TC-ID: PR4.2.30-hot-money-style-semantics."""
    content = _doc()
    assert "`capital.hot_money_style[]` | short-term attack direction by theme/event" in content
    assert "limit_up.categories" in content
    assert "strong_stock_watch_history" in content
    assert "structured_event_layer" in content
    assert "stock role is not participant identity" in content
    assert "stock_fund_flow_snapshot" in content


def test_forbidden_paths_are_locked() -> None:
    """TC-ID: PR4.2.30-forbidden-paths."""
    content = _doc()
    assert 'money_flow_enhanced.role_label == "龙头"\n  -> institution_style' in content
    assert 'money_flow_enhanced.role_label == "龙头"\n  -> hot_money_style' in content
    assert "theme_capital_flow\n  -> active_amount" in content
    assert "theme_capital_flow\n  -> hot_money_style" in content
    assert "eastmoney_fund_flow.main_net_inflow > 0\n  -> institution_style" in content
    assert "eastmoney_fund_flow.main_net_inflow > 0\n  -> hot_money_style" in content
    assert "dragon_tiger rows missing\n  -> infer from money_flow_enhanced / role_label / theme stage" in content
    assert "analyst_report.active_capital_yi\n  -> production active_amount" in content


def test_dragon_tiger_is_evidence_layer_only() -> None:
    """TC-ID: PR4.2.30-dragon-tiger-evidence-only."""
    content = _doc()
    assert "DragonTigerSnapshot" in content
    assert "evidence_only" in content
    assert "It must not become the only style producer" in content
    assert "confidence adjustment" in content


def test_future_sequence_requires_evidence_layer_before_style_producers() -> None:
    """TC-ID: PR4.2.30-next-pr-sequence."""
    content = _doc()
    assert "PR4.2.31 Capital Evidence Layer" in content
    assert "FundFlowEvidenceAdapter" in content
    assert "ThemeFlowEvidenceAdapter" in content
    assert "PR4.2.32 InstitutionStyleProducer" in content
    assert "PR4.2.33 HotMoneyStyleProducer" in content
