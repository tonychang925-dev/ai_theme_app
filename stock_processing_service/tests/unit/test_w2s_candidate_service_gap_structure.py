from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService


def _bar(stock_id: str, stock_name: str, pct_chg: str = "-2.0") -> StockBarDTO:
    return StockBarDTO(
        trade_date=date(2026, 4, 7),
        stock_id=stock_id,
        stock_name=stock_name,
        open_price=Decimal("15.10"),
        high_price=Decimal("15.20"),
        low_price=Decimal("14.80"),
        close_price=Decimal("14.95"),
        pre_close=Decimal("15.20"),
        pct_chg=Decimal(pct_chg),
        volume=Decimal("1000000"),
        amount=Decimal("10000000"),
        limit_up_price=Decimal("16.72"),
        limit_down_price=Decimal("13.68"),
    )


def _pool_row(stock_id: str, pool_rank: int, metadata: dict) -> SubjectStockPoolDTO:
    return SubjectStockPoolDTO(
        trade_date=date(2026, 4, 7),
        stock_id=stock_id,
        stock_name=stock_id,
        subject_key="9019807",
        subject_name="卫星互联网",
        pool_rank=pool_rank,
        metadata={"candidate_source": "strong_watch_pool", **metadata},
    )


def _prior(stock_id: str, state: str = "repair") -> PriorSnapshotDTO:
    return PriorSnapshotDTO(
        trade_date=date(2026, 4, 6),
        stock_id=stock_id,
        snapshot_version="v1",
        payload={"final_cycle_state": state},
    )


def test_gap_strict_scores_higher_than_gap_soft() -> None:
    svc = W2SCandidateService()
    bars = [_bar("A001.SZ", "严格缺口"), _bar("A002.SZ", "软缺口")]
    rows = [
        _pool_row(
            "A001.SZ",
            3,
            {
                "watch_status": "weakening_keep",
                "watch_score": "62",
                "strong_grade": "B",
                "support_score": "78",
                "support_type": "gap_support",
                "gap_hit": True,
                "gap_hit_mode": "strict",
                "gap_source": "gap_structure",
                "role_tags": {"watch_tier": "B", "two_board_entry": True},
                "prior7_limitup_days": 0,
                "prior7_strong_days": 1,
            },
        ),
        _pool_row(
            "A002.SZ",
            4,
            {
                "watch_status": "weakening_keep",
                "watch_score": "62",
                "strong_grade": "B",
                "support_score": "78",
                "support_type": "gap_support",
                "gap_hit": True,
                "gap_hit_mode": "soft",
                "gap_source": "gap_structure",
                "role_tags": {"watch_tier": "B", "two_board_entry": True},
                "prior7_limitup_days": 0,
                "prior7_strong_days": 1,
            },
        ),
    ]
    out = svc.build_candidates(bars=bars, pool_rows=rows, prior_rows=[_prior("A001.SZ"), _prior("A002.SZ")])
    by_id = {c.stock_id: c for c in out}
    assert by_id["A001.SZ"].candidate_score > by_id["A002.SZ"].candidate_score
    assert by_id["A001.SZ"].gap_structure_bonus > by_id["A002.SZ"].gap_structure_bonus


def test_gap_repair_bonus_applies_for_soft_gap_with_repair() -> None:
    svc = W2SCandidateService()
    out = svc.build_candidates(
        bars=[_bar("002361.SZ", "神剑股份", pct_chg="-2.8")],
        pool_rows=[
            _pool_row(
                "002361.SZ",
                12,
                {
                    "watch_status": "weakening_keep",
                    "watch_score": "58",
                    "strong_grade": "B",
                    "support_score": "80",
                    "support_type": "gap_support",
                    "gap_hit": True,
                    "gap_hit_mode": "soft",
                    "gap_source": "gap_structure",
                    "role_tags": {"watch_tier": "B", "two_board_entry": True},
                    "prior7_limitup_days": 0,
                    "prior7_strong_days": 1,
                },
            )
        ],
        prior_rows=[_prior("002361.SZ", "repair")],
    )
    assert out
    c = out[0]
    assert c.support_type == "gap_support"
    assert c.gap_hit is True
    assert c.gap_hit_mode == "soft"
    assert c.gap_repair_bonus > 0


def test_formal_ranking_prioritizes_gap_over_prev_low() -> None:
    svc = W2SCandidateService()
    bars = [_bar("G001.SZ", "严格缺口"), _bar("G002.SZ", "软缺口"), _bar("P001.SZ", "前低支撑")]
    rows = [
        _pool_row(
            "G001.SZ",
            5,
            {
                "watch_status": "weakening_keep",
                "watch_score": "60",
                "strong_grade": "B",
                "support_score": "78",
                "support_type": "gap_support",
                "gap_hit": True,
                "gap_hit_mode": "strict",
                "gap_source": "gap_structure",
                "role_tags": {"watch_tier": "B", "two_board_entry": True},
                "prior7_limitup_days": 0,
                "prior7_strong_days": 1,
            },
        ),
        _pool_row(
            "G002.SZ",
            6,
            {
                "watch_status": "weakening_keep",
                "watch_score": "60",
                "strong_grade": "B",
                "support_score": "78",
                "support_type": "gap_support",
                "gap_hit": True,
                "gap_hit_mode": "soft",
                "gap_source": "gap_structure",
                "role_tags": {"watch_tier": "B", "two_board_entry": True},
                "prior7_limitup_days": 0,
                "prior7_strong_days": 1,
            },
        ),
        _pool_row(
            "P001.SZ",
            7,
            {
                "watch_status": "weakening_keep",
                "watch_score": "62",
                "strong_grade": "B",
                "support_score": "82",
                "support_type": "prev_low_support",
                "gap_hit": False,
                "gap_hit_mode": "miss",
                "gap_source": "",
                "role_tags": {"watch_tier": "B", "two_board_entry": True},
                "prior7_limitup_days": 0,
                "prior7_strong_days": 1,
            },
        ),
    ]
    out = svc.build_candidates(
        bars=bars,
        pool_rows=rows,
        prior_rows=[_prior("G001.SZ"), _prior("G002.SZ"), _prior("P001.SZ")],
    )
    ranked_ids = [c.stock_id for c in out if c.candidate_level == "formal"]
    assert ranked_ids.index("G001.SZ") < ranked_ids.index("G002.SZ")
    assert ranked_ids[:2] == ["G001.SZ", "G002.SZ"]


def test_non_gap_gets_no_gap_bonus() -> None:
    svc = W2SCandidateService()
    out = svc.build_candidates(
        bars=[_bar("P002.SZ", "普通前低票", pct_chg="-2.5")],
        pool_rows=[
            _pool_row(
                "P002.SZ",
                8,
                {
                    "watch_status": "weakening_keep",
                    "watch_score": "60",
                    "strong_grade": "B",
                    "support_score": "80",
                    "support_type": "prev_low_support",
                    "gap_hit": False,
                    "gap_hit_mode": "miss",
                    "gap_source": "",
                    "role_tags": {"watch_tier": "B", "two_board_entry": True},
                    "prior7_limitup_days": 0,
                    "prior7_strong_days": 1,
                },
            )
        ],
        prior_rows=[_prior("P002.SZ", "repair")],
    )
    assert out
    c = out[0]
    assert c.gap_structure_bonus == 0
    assert c.gap_repair_bonus == 0
