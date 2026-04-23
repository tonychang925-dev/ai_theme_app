from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services import StrongWatchService
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


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

    prior_rows = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="002000.SZ",
            snapshot_version="v1",
            payload={"pct_chg": "9.99"},
        )
    ]
    promoted, watch_rows = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
    )
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
    assert all(row.watch_status in {"weakening", "weakening_keep", "removed"} for row in watch_d2)
    for row in watch_d2:
        if row.watch_status == "removed":
            assert row.prune_mode in {"immediate", "delayed"}
            assert row.removed_reason


def test_strong_watch_refresh_keeps_prior7_weak_pullback() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 23)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="002361.SZ",
            stock_name="Shenjian",
            pool_rank=12,
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="002361.SZ",
            stock_name="Shenjian",
            open_price=Decimal("12"),
            high_price=Decimal("12.2"),
            low_price=Decimal("11.3"),
            close_price=Decimal("11.5"),
            pre_close=Decimal("11.9"),
            pct_chg=Decimal("-3.36"),
            volume=Decimal("100000"),
            amount=Decimal("1200000"),
            limit_up_price=Decimal("13.09"),
            limit_down_price=Decimal("10.71"),
        )
    ]
    prior_rows = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="002361.SZ",
            snapshot_version="v1",
            payload={"pct_chg": "9.98"},
        ),
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 21),
            stock_id="002361.SZ",
            snapshot_version="v1",
            payload={"pct_chg": "5.32"},
        ),
    ]

    promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
    )
    assert kept
    row = kept[0]
    assert row.strong_grade in {"B", "B_KEEP", "A"}
    assert row.watch_status != "removed"
    assert row.strong_gene_score > Decimal("40")
    assert row.weakness_tolerance_score >= Decimal("45")
    assert promoted


def test_strong_watch_refresh_does_not_overreward_hot_leader() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 23)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="000001.SZ",
            stock_name="HotLeader",
            pool_rank=1,
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="000001.SZ",
            stock_name="HotLeader",
            open_price=Decimal("10"),
            high_price=Decimal("10.8"),
            low_price=Decimal("9.9"),
            close_price=Decimal("10.5"),
            pre_close=Decimal("10"),
            pct_chg=Decimal("5"),
            volume=Decimal("100000"),
            amount=Decimal("1000000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]
    prior_rows = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="000001.SZ",
            snapshot_version="v1",
            payload={"pct_chg": "9.99"},
        ),
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 21),
            stock_id="000001.SZ",
            snapshot_version="v1",
            payload={"pct_chg": "5.20"},
        ),
    ]
    _promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
    )
    assert kept
    row = kept[0]
    assert row.weakness_tolerance_score <= Decimal("36")
    assert row.watch_score < Decimal("86")


def test_strong_watch_prune_removes_invalid_weak_without_gene_support() -> None:
    prune = StrongWatchPruneService()
    rows = [
        StrongWatchRecord(
            stock_id="300000.SZ",
            stock_name="BadWeak",
            subject_key="s",
            subject_name="s",
            pool_rank=20,
            watch_score=Decimal("35"),
            strong_grade="REJECT",
            support_type="ma_support",
            support_level=Decimal("10"),
            support_score=Decimal("30"),
            mainline_context_score=Decimal("5"),
            strong_gene_score=Decimal("10"),
            weakness_tolerance_score=Decimal("18"),
        )
    ]
    kept, pruned = prune.prune(rows)
    assert not kept
    assert pruned
    assert pruned[0].watch_status == "removed"
    assert pruned[0].prune_reason_code in {"HARD_PRUNE_WEAK_GENE", "HARD_PRUNE_SUPPORT_BREAK", "HARD_PRUNE_INVALID_WEAK"}


def test_strong_watch_prune_keeps_b_keep_with_gene_and_support() -> None:
    prune = StrongWatchPruneService()
    rows = [
        StrongWatchRecord(
            stock_id="605060.SH",
            stock_name="Liande",
            subject_key="s",
            subject_name="s",
            pool_rank=15,
            watch_score=Decimal("47"),
            strong_grade="B_KEEP",
            support_type="ma_support",
            support_level=Decimal("10"),
            support_score=Decimal("70"),
            mainline_context_score=Decimal("20"),
            strong_gene_score=Decimal("60"),
            weakness_tolerance_score=Decimal("80"),
            prior7_limitup_days=1,
            prior7_strong_days=2,
        )
    ]
    kept, pruned = prune.prune(rows)
    assert not pruned
    assert kept
    assert kept[0].watch_status == "weakening_keep"
    assert kept[0].kept_because == "weakening_keep_gene_and_support"
