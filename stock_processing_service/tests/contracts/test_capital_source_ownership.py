"""PR4.2.20d Capital Intelligence source ownership guard.

TC-ID: PR4.2.20d-capital-source-ownership

This test locks the audit-only contract for Capital Intelligence. It does not
exercise production code. It prevents future agents from collapsing analyst
capital style back into dragon-tiger seat rows or stock role labels.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Capital_Intelligence_Source_Ownership.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_capital_intelligence_audit_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "Capital Intelligence Source Ownership" in content
    assert "ThemeCapitalIntelligenceProducer" in content
    assert "ShortTermCapitalProducer" in content
    assert "DragonTigerSnapshot" in content


def test_seat_money_summary_is_evidence_not_style_source() -> None:
    content = _doc()
    assert "seat_money_summary\n  -> capital.evidence.dragon_tiger" in content
    assert "seat_money_summary\n  -> institution_style" in content
    assert "seat_money_summary\n  -> hot_money_style" in content


def test_role_label_is_not_capital_identity() -> None:
    content = _doc()
    assert "`role_label` is stock role, not participant type" in content
    assert 'money_flow_enhanced.role_label == "龙头"\n  -> institution_style' in content
    assert 'money_flow_enhanced.role_label == "龙头"\n  -> hot_money_style' in content


def test_theme_capital_flow_is_not_hot_money_identity() -> None:
    content = _doc()
    assert "theme_capital_flow" in content
    assert "not hot-money identity by itself" in content
    assert "theme_capital_flow\n  -> hot_money_style" in content


def test_dragon_tiger_is_supporting_evidence_only() -> None:
    content = _doc()
    assert "Capital Intelligence Producers may use it as supporting evidence" in content
    assert "capital.evidence.dragon_tiger" in content
    assert "dragon_tiger missing\n  -> infer from money_flow_enhanced / role_label / theme stage" in content
