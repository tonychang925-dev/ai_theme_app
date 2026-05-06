from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.leader_evidence_builder import LeaderEvidenceBuilder
from stock_processing_service.domain.services.theme_cycle_evidence_daily_builder import ThemeCycleEvidenceDailyBuilder


def _pool(
    stock_id: str,
    *,
    rank: int,
    pct_chg: str,
    is_leader: bool = False,
    limit_up: bool = False,
    leader_score: str | None = None,
) -> SubjectStockPoolDTO:
    metadata = {
        "leader_signal_source": "db_pool_fields",
        "pool_rank": rank,
        "rank_order": rank,
        "pct_chg": pct_chg,
        "limit_up": limit_up,
        "is_leader": is_leader,
    }
    if leader_score is not None:
        metadata["leader_score"] = leader_score
    return SubjectStockPoolDTO(
        trade_date=date(2026, 4, 15),
        subject_key="s1",
        subject_name="联德题材",
        stock_id=stock_id,
        stock_name=stock_id,
        pool_rank=rank,
        metadata=metadata,
    )


def _bar(stock_id: str, pct_chg: str) -> StockBarDTO:
    return StockBarDTO(
        trade_date=date(2026, 4, 15),
        stock_id=stock_id,
        stock_name=stock_id,
        open_price=Decimal("10"),
        high_price=Decimal("11"),
        low_price=Decimal("9"),
        close_price=Decimal("10"),
        pre_close=Decimal("10"),
        pct_chg=Decimal(pct_chg),
        volume=Decimal("1000"),
        amount=Decimal("10000"),
        limit_up_price=Decimal("11"),
        limit_down_price=Decimal("9"),
    )


def test_leader_evidence_infers_alive_score_from_db_pool_fields() -> None:
    rows = [
        _pool("605060.SH", rank=1, pct_chg="5.66", is_leader=True),
        _pool("600000.SH", rank=2, pct_chg="1.2"),
        _pool("600001.SH", rank=3, pct_chg="-0.5"),
    ]
    bars = {row.stock_id: _bar(row.stock_id, str(row.metadata["pct_chg"])) for row in rows}

    evidence = LeaderEvidenceBuilder().build(rows=rows, bars_by_stock=bars)

    assert evidence.leader_score_source == "db_pool_fields_inferred"
    assert evidence.leader_stock_id == "605060.SH"
    assert evidence.leader_alive_score == Decimal("80")
    assert evidence.leader_breakdown_flag is False
    assert evidence.leader_breakdown_reason == "db_pool_fields_inferred_alive"
    assert evidence.front_row_alive_count == 2


def test_leader_evidence_prefers_existing_pool_metadata_score() -> None:
    rows = [
        _pool("605060.SH", rank=1, pct_chg="5.66", is_leader=True),
        _pool("600000.SH", rank=2, pct_chg="1.2", leader_score="91"),
    ]
    bars = {row.stock_id: _bar(row.stock_id, str(row.metadata["pct_chg"])) for row in rows}

    evidence = LeaderEvidenceBuilder().build(rows=rows, bars_by_stock=bars)

    assert evidence.leader_score_source == "pool_metadata"
    assert evidence.leader_stock_id == "600000.SH"
    assert evidence.leader_alive_score == Decimal("91")


def test_theme_cycle_evidence_daily_builder_uses_leader_evidence_builder() -> None:
    rows = [
        _pool("605060.SH", rank=1, pct_chg="5.66", is_leader=True),
        _pool("600000.SH", rank=2, pct_chg="1.2"),
    ]
    bars = [_bar(row.stock_id, str(row.metadata["pct_chg"])) for row in rows]

    built = ThemeCycleEvidenceDailyBuilder().build_many(
        trade_date=date(2026, 4, 15),
        pool_rows=rows,
        bars=bars,
        heat_scores={},
        previous_states={},
    )[0]

    assert built.leader_alive_score == Decimal("80")
    assert built.leader_breakdown_flag is False
    assert built.evidence_json["leader_layer"]["leader_score_source"] == "db_pool_fields_inferred"
    assert built.evidence_json["leader_layer"]["leader_stock_id"] == "605060.SH"
