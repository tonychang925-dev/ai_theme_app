from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services import StrongWatchService


def test_strong_watch_promote_pipeline() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 23)

    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="002000.SZ",
            stock_name="SampleA",
            pool_rank=1,
        ),
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="002001.SZ",
            stock_name="SampleB",
            pool_rank=40,
        ),
    ]

    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="002000.SZ",
            stock_name="SampleA",
            open_price=Decimal("10"),
            high_price=Decimal("11"),
            low_price=Decimal("9.8"),
            close_price=Decimal("10.9"),
            pre_close=Decimal("10"),
            pct_chg=Decimal("9"),
            volume=Decimal("10000"),
            amount=Decimal("100000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]

    promoted, watch_rows = service.build_promoted_pool(trade_date=trade_date, pool_rows=pool_rows, bars=bars)
    assert len(watch_rows) == 1
    assert len(promoted) == 1
    assert promoted[0].stock_id == "002000.SZ"
    assert promoted[0].metadata["candidate_source"] == "strong_watch_pool"
    assert "support_refs" in promoted[0].metadata
    assert promoted[0].metadata["support_type"] in {"ma_support", "prev_low_support", "platform_support"}


def test_strong_watch_two_stage_prune_roll_forward() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 23)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="002100.SZ",
            stock_name="WeakA",
            pool_rank=25,
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="002100.SZ",
            stock_name="WeakA",
            open_price=Decimal("10"),
            high_price=Decimal("10.1"),
            low_price=Decimal("9.2"),
            close_price=Decimal("9.3"),
            pre_close=Decimal("10"),
            pct_chg=Decimal("-7"),
            volume=Decimal("10000"),
            amount=Decimal("100000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]
    # first day enters weakening path
    promoted_d1, watch_d1 = service.build_promoted_pool(trade_date, pool_rows, bars)
    assert len(promoted_d1) == 0
    # roll-forward with weak_days accumulation
    promoted_d2, watch_d2 = service.build_promoted_pool(trade_date, pool_rows, bars, prior_active_rows=watch_d1)
    assert len(promoted_d2) == 0
    assert all(row.watch_status in {"weakening", "removed"} for row in watch_d2)
    for row in watch_d2:
        if row.watch_status == "removed":
            assert row.prune_mode in {"immediate", "delayed"}
            assert row.removed_reason
