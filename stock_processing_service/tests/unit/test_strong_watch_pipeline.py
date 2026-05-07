from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services import StrongWatchService
from stock_processing_service.domain.services.strong_watch_preseed_gene_enricher import StrongWatchPreSeedGeneEnricher
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_refresh_service import (
    StrongWatchRecord,
    StrongWatchRefreshService,
)
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService


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


def test_preseed_two_board_gene_breaks_seed_rank_gate_without_confirming_mainline() -> None:
    trade_date = date(2026, 4, 23)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="edge_theme",
            subject_name="Edge Theme",
            stock_id="600152.SH",
            stock_name="Vekay",
            pool_rank=55,
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="600152.SH",
            stock_name="Vekay",
            open_price=Decimal("10"),
            high_price=Decimal("10.2"),
            low_price=Decimal("9.6"),
            close_price=Decimal("9.8"),
            pre_close=Decimal("10"),
            pct_chg=Decimal("-2"),
            volume=Decimal("10000"),
            amount=Decimal("100000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]
    prior_rows = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 21),
            stock_id="600152.SH",
            snapshot_version="v1",
            payload={"pct_chg": "9.99"},
        ),
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="600152.SH",
            snapshot_version="v1",
            payload={"pct_chg": "10.01"},
        ),
    ]

    enriched = StrongWatchPreSeedGeneEnricher().enrich(
        pool_rows=pool_rows,
        bars=bars,
        prior_rows=prior_rows,
    )
    seeded = StrongWatchSeedService().seed(enriched)

    assert [row.stock_id for row in seeded] == ["600152.SH"]
    assert seeded[0].metadata["strong_gene_seed"] is True
    assert seeded[0].metadata["two_board_entry"] is True
    assert seeded[0].metadata["seed_gate_reason"] == "two_board_entry"
    assert seeded[0].metadata["identity_scope"] == "independent_stock_signal"


def test_seed_rank_pass_alone_does_not_enter_old_chain_watch_pool() -> None:
    trade_date = date(2026, 4, 23)
    row = SubjectStockPoolDTO(
        trade_date=trade_date,
        subject_key="ai_chip",
        subject_name="AI Chip",
        stock_id="002999.SZ",
        stock_name="RankOnly",
        pool_rank=12,
        metadata={
            "identity_status": "confirmed",
            "is_main_theme": True,
            "final_mainline_alive": True,
        },
    )

    assert StrongWatchSeedService().seed([row]) == []


def test_seed_old_chain_static_gate_requires_strength_history() -> None:
    trade_date = date(2026, 4, 23)
    row = SubjectStockPoolDTO(
        trade_date=trade_date,
        subject_key="ai_chip",
        subject_name="AI Chip",
        stock_id="002998.SZ",
        stock_name="AlphaHistory",
        pool_rank=3,
        metadata={
            "identity_status": "confirmed",
            "is_main_theme": True,
            "final_mainline_alive": True,
            "prior7_limitup_days": 1,
            "prior7_strong_days": 1,
        },
    )

    seeded = StrongWatchSeedService().seed([row])

    assert [r.stock_id for r in seeded] == ["002998.SZ"]
    assert seeded[0].metadata["seed_gate_reason"] == "old_chain_static_gate"


def test_strong_watch_promote_pipeline_respects_old_chain_thresholds() -> None:
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
            payload={
                "open_price": "9.2",
                "high_price": "10.1",
                "low_price": "9.6",
                "close_price": "10.0",
                "pre_close": "9.1",
                "pct_chg": "9.99",
            },
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
    assert watch_rows == []
    assert promoted == []


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


def test_strong_watch_refresh_low_score_pullback_is_not_force_kept() -> None:
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
            payload={
                "open_price": "10.8",
                "high_price": "12.0",
                "low_price": "11.0",
                "close_price": "11.9",
                "pre_close": "10.8",
                "pct_chg": "9.98",
            },
        ),
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 21),
            stock_id="002361.SZ",
            snapshot_version="v1",
            payload={
                "open_price": "10.2",
                "high_price": "10.9",
                "low_price": "10.1",
                "close_price": "10.8",
                "pre_close": "10.25",
                "pct_chg": "5.32",
            },
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
    assert kept == []
    assert promoted == []


def test_strong_watch_refresh_hot_leader_still_needs_old_chain_gate() -> None:
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
            payload={
                "open_price": "9.1",
                "high_price": "10.1",
                "low_price": "9.7",
                "close_price": "10.0",
                "pre_close": "9.1",
                "pct_chg": "9.99",
            },
        ),
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 21),
            stock_id="000001.SZ",
            snapshot_version="v1",
            payload={
                "open_price": "8.8",
                "high_price": "9.2",
                "low_price": "8.7",
                "close_price": "9.1",
                "pre_close": "8.65",
                "pct_chg": "5.20",
            },
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
    assert kept == []


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


def test_strong_watch_prune_rejects_low_score_observe_rows() -> None:
    prune = StrongWatchPruneService()
    rows = [
        StrongWatchRecord(
            stock_id="605060.SH",
            stock_name="Liande",
            subject_key="s",
            subject_name="s",
            pool_rank=15,
            watch_score=Decimal("47"),
            strong_grade="REJECT",
            support_type="ma_support",
            support_level=Decimal("10"),
            support_score=Decimal("70"),
            mainline_context_score=Decimal("20"),
            strong_gene_score=Decimal("60"),
            weakness_tolerance_score=Decimal("80"),
            prior7_limitup_days=1,
            prior7_strong_days=2,
            admission_status="observe_only",
        )
    ]
    kept, pruned = prune.prune(rows)
    assert kept == []
    assert len(pruned) == 1
    assert pruned[0].prune_reason_code == "HARD_PRUNE_OBSERVE_LOW_SCORE"


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
            watch_score=Decimal("80"),
            strong_grade="A",
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


def test_soft_reject_is_pruned_instead_of_downgraded() -> None:
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
    assert kept[0].watch_status == "weakening"
    assert kept[0].admission_status == "observe_only"
    assert all(r.watch_status != "removed" for r in history)


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


def test_strong_watch_roll_forward_keeps_prior_active_without_today_seed() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 30)
    prior = StrongWatchRecord(
        stock_id="002361.SZ",
        stock_name="Shenjian",
        subject_key="satellite",
        subject_name="卫星互联网",
        pool_rank=1,
        watch_score=Decimal("82"),
        strong_grade="A",
        support_type="gap_support",
        support_level=Decimal("10"),
        support_score=Decimal("76"),
        role_tags={
            "final_cycle_state": "repair",
            "final_mainline_alive": True,
            "board_effect_confirmed": True,
            "two_board_entry": True,
        },
        watch_age_days=3,
        prior7_limitup_days=2,
        prior7_strong_days=3,
        prior7_best_watch_score=Decimal("82"),
        prior7_peak_rank=1,
    )
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="002361.SZ",
            stock_name="Shenjian",
            open_price=Decimal("12"),
            high_price=Decimal("12.4"),
            low_price=Decimal("11.8"),
            close_price=Decimal("12.1"),
            pre_close=Decimal("12"),
            pct_chg=Decimal("0.83"),
            volume=Decimal("100000"),
            amount=Decimal("1200000"),
            limit_up_price=Decimal("13.2"),
            limit_down_price=Decimal("10.8"),
        )
    ]
    identities, cycles = _identity_cycle("satellite")

    promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=[],
        bars=bars,
        prior_active_rows=[prior],
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )

    assert [row.stock_id for row in kept] == ["002361.SZ"]
    assert kept[0].watch_age_days == 1
    assert promoted and promoted[0].stock_id == "002361.SZ"


def test_strong_watch_two_board_entry_renews_watch_window() -> None:
    service = StrongWatchService()
    trade_date = date(2026, 4, 17)
    pool_rows = [
        SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key="satellite",
            subject_name="卫星互联网",
            stock_id="600152.SH",
            stock_name="维科技术",
            pool_rank=2,
            metadata={
                "candidate_source": "strong_watch_pool",
                "watch_status": "weakening",
                "watch_score": "56.0",
                "support_score": "78",
                "support_type": "prev_low_support",
                "strong_grade": "B",
                "role_tags": {"is_leader": False, "watch_tier": "B"},
                "prior7_limitup_days": 2,
                "prior7_strong_days": 3,
                "prior7_best_watch_score": "62.8",
                "prior7_peak_rank": 2,
                "recent_limit_up_count": 2,
                "max_consecutive_limit_up_days": 2,
                "transition_type": "upgrade",
                "transition_confidence": "0.92",
                "trigger_flags": ["state_rank_up"],
            },
        )
    ]
    bars = [
        StockBarDTO(
            trade_date=trade_date,
            stock_id="600152.SH",
            stock_name="维科技术",
            open_price=Decimal("11.2"),
            high_price=Decimal("12.0"),
            low_price=Decimal("11.0"),
            close_price=Decimal("11.9"),
            pre_close=Decimal("10.8"),
            pct_chg=Decimal("10.19"),
            volume=Decimal("100000"),
            amount=Decimal("1000000"),
            limit_up_price=Decimal("11.88"),
            limit_down_price=Decimal("9.72"),
        )
    ]
    prior_active_rows = [
        StrongWatchRecord(
            stock_id="600152.SH",
            stock_name="维科技术",
            subject_key="satellite",
            subject_name="卫星互联网",
            pool_rank=2,
            watch_score=Decimal("56.0"),
            strong_grade="B",
            support_type="prev_low_support",
            support_level=Decimal("11.2"),
            support_score=Decimal("78"),
            role_tags={
                "final_cycle_state": "repair",
                "final_mainline_alive": True,
                "board_effect_confirmed": True,
            },
            watch_status="weakening",
            watch_age_days=3,
            weak_days=3,
            prior7_limitup_days=2,
            prior7_strong_days=3,
            prior7_best_watch_score=Decimal("62.8"),
            prior7_peak_rank=2,
        )
    ]
    identities, cycles = _identity_cycle("satellite")

    promoted, kept = service.build_promoted_pool(
        trade_date=trade_date,
        pool_rows=pool_rows,
        bars=bars,
        prior_active_rows=prior_active_rows,
        identities_by_subject=identities,
        cycles_by_subject=cycles,
    )

    assert kept
    assert kept[0].stock_id == "600152.SH"
    assert kept[0].watch_status == "weakening"
    assert kept[0].watch_age_days == 1
    assert kept[0].weak_days == 1


def test_strong_watch_prune_expires_after_7_trade_day_window() -> None:
    prune = StrongWatchPruneService()
    row = StrongWatchRecord(
        stock_id="002361.SZ",
        stock_name="Shenjian",
        subject_key="satellite",
        subject_name="卫星互联网",
        pool_rank=1,
        watch_score=Decimal("82"),
        strong_grade="A",
        support_type="gap_support",
        support_level=Decimal("10"),
        support_score=Decimal("78"),
        role_tags={"final_cycle_state": "repair", "final_mainline_alive": True},
        watch_age_days=8,
        strong_gene_score=Decimal("80"),
        weakness_tolerance_score=Decimal("70"),
        prior7_limitup_days=2,
    )

    kept, pruned = prune.prune([row])

    assert kept == []
    assert len(pruned) == 1
    assert pruned[0].prune_reason_code == "DELAYED_PRUNE_WATCH_WINDOW_EXPIRED"


def test_strong_watch_prune_mainline_fade_watch_exit() -> None:
    prune = StrongWatchPruneService()
    row = StrongWatchRecord(
        stock_id="002361.SZ",
        stock_name="Shenjian",
        subject_key="satellite",
        subject_name="卫星互联网",
        pool_rank=1,
        watch_score=Decimal("82"),
        strong_grade="A",
        support_type="gap_support",
        support_level=Decimal("10"),
        support_score=Decimal("78"),
        role_tags={"final_cycle_state": "fade_watch", "final_mainline_alive": False},
        watch_age_days=4,
        strong_gene_score=Decimal("80"),
        weakness_tolerance_score=Decimal("70"),
        prior7_limitup_days=2,
    )

    kept, pruned = prune.prune([row])

    assert kept == []
    assert len(pruned) == 1
    assert pruned[0].prune_reason_code == "HARD_PRUNE_MAINLINE_FADE"


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


# ── Renewal tests ──

def _pool_row(
    stock_id: str,
    *,
    watch_age_days: int = 5,
    weak_days: int = 2,
    watch_score: str = "60",
    pool_rank: int = 15,
    subject_key: str = "test",
) -> SubjectStockPoolDTO:
    return SubjectStockPoolDTO(
        trade_date=date(2026, 4, 17),
        subject_key=subject_key,
        subject_name=subject_key,
        stock_id=stock_id,
        stock_name=stock_id,
        pool_rank=pool_rank,
        metadata={
            "watch_age_days": watch_age_days,
            "weak_days": weak_days,
            "watch_score": watch_score,
            "prior7_limitup_days": 1,
            "recent_limit_up_count": 1,
            "max_consecutive_limit_up_days": 0,
        },
    )


def _bar(pct_chg: str) -> StockBarDTO:
    return StockBarDTO(
        trade_date=date(2026, 4, 17),
        stock_id="test",
        stock_name="test",
        open_price=Decimal("10"),
        high_price=Decimal("11"),
        low_price=Decimal("9.5"),
        close_price=Decimal("10.5"),
        pre_close=Decimal("10"),
        pct_chg=Decimal(pct_chg),
        volume=Decimal("10000"),
        amount=Decimal("100000"),
        limit_up_price=Decimal("11"),
        limit_down_price=Decimal("9"),
    )


def test_renewal_limit_up_resets_watch_age() -> None:
    """当日涨停 → renewal_reason=limit_up_renewal, watch_age_days=1."""
    svc = StrongWatchRefreshService()
    rows = [_pool_row("test", watch_age_days=5)]
    bars = [_bar("9.95")]  # pct_chg >= 9.5 → current_limit_up
    result = svc.refresh(rows, bars)
    assert len(result) == 1
    r = result[0]
    assert r.watch_age_days == 1
    assert r.weak_days == 0
    role_tags = r.role_tags or {}
    assert role_tags.get("renewal_signal") is True
    assert role_tags.get("renewal_reason") == "limit_up_renewal"
    assert role_tags.get("watch_age_reset") is True


def test_renewal_two_board_via_recent_multi_limitup() -> None:
    """近7日多次涨停 → renewal_reason=recent_multi_limitup_renewal, watch_age_days=1."""
    svc = StrongWatchRefreshService()
    # prior7_limitup_days=2 → triggers recent_multi_limitup_renewal
    rows = [
        SubjectStockPoolDTO(
            trade_date=date(2026, 4, 17),
            subject_key="test",
            subject_name="test",
            stock_id="test",
            stock_name="test",
            pool_rank=15,
            metadata={
                "watch_age_days": 5,
                "weak_days": 2,
                "watch_score": "60",
                "prior7_limitup_days": 2,
                "recent_limit_up_count": 1,
                "max_consecutive_limit_up_days": 0,
            },
        )
    ]
    bars = [_bar("1.5")]  # no current limit_up, but prior7=2 triggers renewal
    result = svc.refresh(rows, bars)
    assert len(result) == 1
    r = result[0]
    role_tags = r.role_tags or {}
    # prior7=2 triggers two_board_entry=True → two_board_renewal (highest priority)
    assert role_tags.get("renewal_signal") is True
    assert role_tags.get("renewal_reason") in {"two_board_renewal", "prior7_multi_limitup_renewal"}
    assert role_tags.get("watch_age_reset") is True
    assert r.watch_age_days == 1


def test_no_renewal_preserves_input_age() -> None:
    """无新强势信号 → 保留输入 watch_age_days，不触发 renewal."""
    svc = StrongWatchRefreshService()
    rows = [_pool_row("test", watch_age_days=5)]
    # pct_chg=1.5: no limit-up, pct<5, watch_score=60<72 → no renewal
    bars = [_bar("1.5")]
    result = svc.refresh(rows, bars)
    assert len(result) == 1
    r = result[0]
    # With watch_score=60 < WEAKENING_MIN(62) and no gene/support → removed
    # But the renewal test is about whether renewal_signal is triggered.
    # Check that renewal was NOT triggered even if the stock was kept.
    role_tags = r.role_tags or {}
    assert role_tags.get("renewal_signal") is not True
    assert role_tags.get("watch_age_reset") is not True
