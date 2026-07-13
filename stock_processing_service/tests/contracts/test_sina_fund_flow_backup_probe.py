"""PR4.2.31d Sina fund-flow backup probe contract tests."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Sina_Fund_Flow_Backup_Probe.md"
SCRIPT_PATH = PROJECT_ROOT / "stock_processing_service" / "scripts" / "probe_sina_fund_flow_fields.py"


def test_sina_fund_flow_backup_probe_doc_exists() -> None:
    """TC-ID: PR4.2.31d-sina-backup-probe-doc-exists."""
    assert DOC_PATH.exists()
    content = DOC_PATH.read_text(encoding="utf-8")
    assert "source_name: sina_fund_flow" in content
    assert "production_write_allowed: false" in content
    assert "Evidence Freshness Contract" in content


def test_sina_fund_flow_backup_probe_is_probe_only() -> None:
    """TC-ID: PR4.2.31d-sina-backup-probe-only."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "upsert_stock_fund_flow_snapshot_rows" not in source
    assert "ReviewDocument" not in source
    assert "institution_attention" not in source
    assert "hot_money_style" not in source
    assert '"production_write_allowed": False' in source


def test_sina_fund_flow_forbidden_paths_are_documented() -> None:
    """TC-ID: PR4.2.31d-sina-backup-forbidden-paths."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "sina_fund_flow.net_inflow_yuan > 0\n  -> institution_attention" in content
    assert "sina_fund_flow.large_net_inflow_yuan > 0\n  -> hot_money_style" in content
    assert "sina_fund_flow\n  -> ReviewDocument.capital.institution" in content
    assert "eastmoney_fund_flow failed\n  -> silently overwrite with sina_fund_flow" in content
