from __future__ import annotations

import pytest

import frontend_bff.repositories.bff_repository as bff_repo_module
from frontend_bff.repositories.bff_repository import FrontendBffRepository


def test_extract_tables_from_sql() -> None:
    repo = FrontendBffRepository(database_url="postgresql://unused")
    sql = """
    SELECT *
    FROM weak_to_strong_candidate_pool c
    JOIN subject_stock_daily_snapshot s ON s.stock_id = c.stock_id
    """
    tables = repo._extract_tables(sql)
    assert "weak_to_strong_candidate_pool" in tables
    assert "subject_stock_daily_snapshot" in tables


def test_audit_only_mode_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FrontendBffRepository(database_url="postgresql://unused")
    monkeypatch.setattr(bff_repo_module, "BFF_AUDIT_PROCESS_TABLE_READ", True)
    monkeypatch.setattr(bff_repo_module, "BFF_STRICT_FROZEN_OBJECT_READ", False)

    repo._audit_and_guard_sql(
        endpoint="test.audit_only",
        sql="SELECT * FROM weak_to_strong_candidate_pool",
    )


def test_strict_mode_blocks_process_table_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FrontendBffRepository(database_url="postgresql://unused")
    monkeypatch.setattr(bff_repo_module, "BFF_AUDIT_PROCESS_TABLE_READ", True)
    monkeypatch.setattr(bff_repo_module, "BFF_STRICT_FROZEN_OBJECT_READ", True)

    with pytest.raises(PermissionError):
        repo._audit_and_guard_sql(
            endpoint="test.strict",
            sql="SELECT * FROM weak_to_strong_candidate_pool",
        )


def test_strict_mode_allows_frozen_object_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FrontendBffRepository(database_url="postgresql://unused")
    monkeypatch.setattr(bff_repo_module, "BFF_AUDIT_PROCESS_TABLE_READ", True)
    monkeypatch.setattr(bff_repo_module, "BFF_STRICT_FROZEN_OBJECT_READ", True)

    repo._audit_and_guard_sql(
        endpoint="test.strict.frozen",
        sql="SELECT * FROM post_market_recap_snapshot",
    )
