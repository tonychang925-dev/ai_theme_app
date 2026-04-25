from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services import StrongWatchService
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


def _identity_cycle(subject_key: str) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    return (
        {
            subject_key: {
                "identity_status": "confirmed",
                "is_main_theme": True,
                "rule_version": "test",
            }
        },
        {
            subject_key: {
                "final_cycle_state": "repair",
                "final_mainline_alive": True,
            }
        },
    )


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
    identities, cycles = _identity_cycle("ai_chip")
    promoted, watch_rows = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )
    assert len(watch_rows) == 1
    assert len(promoted) == 1
    assert promoted[0].stock_id == "002000.SZ"
    assert promoted[0].metadata["candidate_source"] == "strong_watch_pool"
    assert "support_refs" in promoted[0].metadata
    assert promoted[0].metadata["support_type"] in {
        "ma_support",
        "prev_low_support",
        "platform_support",
        "gap_support",
        "previous_close",
    }


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
    identities, cycles = _identity_cycle("ai_chip")
    promoted_d1, watch_d1 = service.build_promoted_pool(
        trade_date,
        pool_rows,
        bars,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )
    assert len(promoted_d1) == 0
    # roll-forward with weak_days accumulation
    promoted_d2, watch_d2 = service.build_promoted_pool(
        trade_date,
        pool_rows,
        bars,
        prior_active_rows=watch_d1,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )
    assert len(promoted_d2) == 0
    assert all(row.watch_status in {"weakening", "removed"} for row in watch_d2)
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

    identities, cycles = _identity_cycle("ai_chip")
    promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
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
    identities, cycles = _identity_cycle("ai_chip")
    _promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
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
    assert kept[0].watch_status == "weakening"
    assert kept[0].kept_because == "weakening_keep_gene_and_support"


def test_promote_only_formal_admission_rows() -> None:
    promote = StrongWatchPromoteService()
    trade_date = date(2026, 4, 23)
    rows = [
        StrongWatchRecord(
            stock_id="002361.SZ",
            stock_name="Shenjian",
            subject_key="s1",
            subject_name="s1",
            pool_rank=5,
            watch_score=Decimal("72"),
            strong_grade="B",
            support_type="gap_support",
            support_level=Decimal("15"),
            support_score=Decimal("80"),
            admission_status="formal",
        ),
        StrongWatchRecord(
            stock_id="605060.SH",
            stock_name="Liande",
            subject_key="s2",
            subject_name="s2",
            pool_rank=6,
            watch_score=Decimal("70"),
            strong_grade="B",
            support_type="prev_low_support",
            support_level=Decimal("20"),
            support_score=Decimal("72"),
            admission_status="observe_only",
        ),
    ]
    promoted = promote.promote(trade_date, rows)
    assert len(promoted) == 1
    assert promoted[0].stock_id == "002361.SZ"
    assert promoted[0].metadata["admission_status"] == "formal"


def test_soft_reject_downgraded_to_observe_only_not_pruned() -> None:
    class _FakeRefresh:
        def refresh(self, seeded_rows, bars, prior_rows=None, history_bars=None):
            return [
                StrongWatchRecord(
                    stock_id="300001.SZ",
                    stock_name="SoftReject",
                    subject_key="ai_chip",
                    subject_name="AI Chip",
                    pool_rank=5,
                    watch_score=Decimal("70"),
                    strong_grade="B",
                    support_type="prev_low_support",
                    support_level=Decimal("10"),
                    support_score=Decimal("72"),
                    mainline_context_score=Decimal("65"),
                    strong_gene_score=Decimal("58"),
                    weakness_tolerance_score=Decimal("74"),
                    prior7_limitup_days=0,
                    prior7_strong_days=1,
                    role_tags={
                        "is_leader": False,
                        "final_mainline_alive": False,
                        "board_effect_confirmed": False,
                        "recent_limit_up_count": 0,
                        "two_board_entry": False,
                    },
                )
            ]

    service = StrongWatchService(refresh_service=_FakeRefresh())
    trade_date = date(2026, 4, 23)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="ai_chip",
            subject_name="AI Chip",
            stock_id="300001.SZ",
            stock_name="SoftReject",
            pool_rank=5,
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="300001.SZ",
            stock_name="SoftReject",
            open_price=Decimal("10"),
            high_price=Decimal("10.1"),
            low_price=Decimal("9.7"),
            close_price=Decimal("9.8"),
            pre_close=Decimal("10"),
            pct_chg=Decimal("-2"),
            volume=Decimal("100000"),
            amount=Decimal("900000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]
    identities, cycles = _identity_cycle("ai_chip")
    promoted, kept, history = service.build_promoted_pool_with_history(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )
    assert promoted == []
    assert len(kept) == 1
    assert kept[0].admission_status == "observe_only"
    assert kept[0].watch_status == "weakening"
    assert kept[0].kept_because == "admission_soft_reject_observe_only"
    assert any(r.watch_status == "weakening" for r in history)


def test_strong_watch_prune_hard_prune_fade_confirmed() -> None:
    prune = StrongWatchPruneService()
    row = StrongWatchRecord(
        stock_id="002361.SZ",
        stock_name="Shenjian",
        subject_key="9019807",
        subject_name="卫星互联网",
        pool_rank=1,
        watch_score=Decimal("82"),
        strong_grade="A",
        support_type="gap_support",
        support_level=Decimal("15.0"),
        support_score=Decimal("78"),
        role_tags={"final_cycle_state": "fade_confirmed", "fade_confirmed": True},
    )
    kept, pruned = prune.prune([row])
    assert kept == []
    assert len(pruned) == 1
    assert pruned[0].watch_status == "removed"
    assert pruned[0].prune_reason_code == "HARD_PRUNE_FADE_CONFIRMED"


def test_strong_watch_prune_observe_low_score_immediate_remove() -> None:
    prune = StrongWatchPruneService()
    row = StrongWatchRecord(
        stock_id="002019.SZ",
        stock_name="亿帆医药",
        subject_key="9049134",
        subject_name="创新药出海",
        pool_rank=12,
        watch_score=Decimal("31.3"),
        strong_grade="REJECT",
        support_type="previous_low",
        support_level=Decimal("10.0"),
        support_score=Decimal("52"),
        admission_status="observe_only",
        watch_status="weakening_keep",
    )
    kept, pruned = prune.prune([row])
    assert kept == []
    assert len(pruned) == 1
    assert pruned[0].prune_reason_code == "HARD_PRUNE_OBSERVE_LOW_SCORE"
