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


def test_universe_builder_routes_formal_observe_blocked() -> None:
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
    assert sorted(r.stock_id for r in result.observe_rows) == ["B", "C"]
    assert [r.stock_id for r in result.blocked_rows] == ["D"]
    assert result.formal_count == 1
    assert result.observe_count == 2
    assert result.blocked_count == 1
    assert result.diagnostics["A"]["identity_confirmed_pass"] is True
    assert result.diagnostics["C"]["cycle_alive_pass"] is False


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
