from __future__ import annotations

from datetime import date

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_universe import StrongWatchUniverseBuilder


def _row(stock_id: str, subject_key: str) -> SubjectStockPoolDTO:
    return SubjectStockPoolDTO(
        trade_date=date(2026, 4, 7),
        subject_key=subject_key,
        subject_name=f"主题{subject_key}",
        stock_id=stock_id,
        stock_name=f"股票{stock_id}",
        pool_rank=3,
        metadata={},
    )


def test_universe_builder_routes_formal_diagnostic_blocked_by_default() -> None:
    builder = StrongWatchUniverseBuilder()
    pool_rows = [
        _row("A", "S1"),
        _row("B", "S2"),
        _row("C", "S3"),
        _row("D", ""),  # missing subject key => blocked
    ]
    identities = {
        "S1": {"identity_status": "confirmed", "is_main_theme": True},
        "S2": {"identity_status": "observed", "is_main_theme": True},
        "S3": {"identity_status": "confirmed", "is_main_theme": True},
    }
    cycles = {
        "S1": {"final_cycle_state": "repair", "final_mainline_alive": True},
        "S2": {"final_cycle_state": "repair", "final_mainline_alive": True},
        "S3": {"final_cycle_state": "fade_confirmed", "final_mainline_alive": False},
    }

    result = builder.build_universe(
        pool_rows=pool_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )

    assert [r.stock_id for r in result.formal_rows] == ["A"]
    assert result.observe_rows == []
    assert sorted(r.stock_id for r in result.blocked_rows) == ["B", "C", "D"]
    assert result.formal_count == 1
    assert result.observe_count == 0
    assert result.blocked_count == 3
    assert result.diagnostics["A"]["identity_confirmed_pass"] is True
    assert result.diagnostics["C"]["cycle_alive_pass"] is False
    assert result.diagnostics["B"]["universe_status"] == "diagnostic_only"
    assert result.diagnostics["B"]["entry_path"] == "observe_diagnostic"


def test_universe_builder_can_still_emit_legacy_non_formal_observe_when_explicitly_enabled() -> None:
    builder = StrongWatchUniverseBuilder(allow_observe_when_not_formal=True)
    pool_rows = [_row("B", "S2"), _row("C", "S3")]
    identities = {
        "S2": {"identity_status": "observed", "is_main_theme": True},
        "S3": {"identity_status": "confirmed", "is_main_theme": True},
    }
    cycles = {
        "S2": {"final_cycle_state": "repair", "final_mainline_alive": True},
        "S3": {"final_cycle_state": "fade_confirmed", "final_mainline_alive": False},
    }

    result = builder.build_universe(
        pool_rows=pool_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )

    assert sorted(r.stock_id for r in result.observe_rows) == ["B", "C"]
    assert result.blocked_rows == []


def test_universe_builder_routes_independent_leader_gene_to_observe_without_layer_ab() -> None:
    builder = StrongWatchUniverseBuilder()
    row = SubjectStockPoolDTO(
        trade_date=date(2026, 4, 23),
        subject_key="S9",
        subject_name="新主题",
        stock_id="600152.SH",
        stock_name="维科技术",
        pool_rank=55,
        metadata={
            "strong_gene_seed": True,
            "two_board_entry": True,
            "strong_gene_seed_reason": "two_board_entry",
            "identity_scope": "independent_stock_signal",
        },
    )

    result = builder.build_universe(
        pool_rows=[row],
        identities_by_subject={},
        cycles_by_subject={},
    )

    assert result.formal_rows == []
    assert [r.stock_id for r in result.observe_rows] == ["600152.SH"]
    assert result.blocked_rows == []
    assert result.diagnostics["600152.SH"]["entry_path"] == "independent_leader"
    assert result.diagnostics["600152.SH"]["universe_reason"] == "independent_leader_without_layer_ab"


def test_universe_builder_strict_blocks_non_formal() -> None:
    builder = StrongWatchUniverseBuilder(allow_observe_when_not_formal=False)
    pool_rows = [_row("A", "S1"), _row("B", "S2")]
    identities = {
        "S1": {"identity_status": "confirmed", "is_main_theme": True},
        "S2": {"identity_status": "confirmed", "is_main_theme": False},
    }
    cycles = {
        "S1": {"final_cycle_state": "repair", "final_mainline_alive": True},
        "S2": {"final_cycle_state": "repair", "final_mainline_alive": True},
    }

    result = builder.build_universe(
        pool_rows=pool_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )

    assert [r.stock_id for r in result.formal_rows] == ["A"]
    assert result.observe_rows == []
    assert [r.stock_id for r in result.blocked_rows] == ["B"]


def test_universe_builder_strict_still_keeps_independent_leader_gene_observe() -> None:
    builder = StrongWatchUniverseBuilder(allow_observe_when_not_formal=False)
    row = _row("B", "S2")
    row = SubjectStockPoolDTO(
        trade_date=row.trade_date,
        subject_key=row.subject_key,
        subject_name=row.subject_name,
        stock_id=row.stock_id,
        stock_name=row.stock_name,
        pool_rank=55,
        metadata={"strong_gene_seed": True, "two_board_entry": True},
    )
    result = builder.build_universe(
        pool_rows=[row],
        identities_by_subject={"S2": {"identity_status": "observed", "is_main_theme": False}},
        cycles_by_subject={"S2": {"final_cycle_state": "divergence", "final_mainline_alive": False}},
    )

    assert result.formal_rows == []
    assert [r.stock_id for r in result.observe_rows] == ["B"]
    assert result.blocked_rows == []
    assert result.diagnostics["B"]["entry_path"] == "independent_leader"


def test_universe_builder_blocks_when_identity_contract_missing() -> None:
    builder = StrongWatchUniverseBuilder()
    pool_rows = [_row("A", "S1")]
    identities = {
        "S1": {"identity_status": "confirmed"},  # missing is_main_theme
    }
    cycles = {
        "S1": {"final_cycle_state": "repair", "final_mainline_alive": True},
    }
    result = builder.build_universe(
        pool_rows=pool_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )
    assert [r.stock_id for r in result.blocked_rows] == ["A"]
    assert result.diagnostics["A"]["universe_reason"] == "contract_missing_identity_fields"
