from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService


def _bar(stock_id: str, pct_chg: str) -> StockBarDTO:
    return StockBarDTO(
        trade_date=date(2026, 4, 23),
        stock_id=stock_id,
        stock_name="S",
        open_price=Decimal("10"),
        high_price=Decimal("11"),
        low_price=Decimal("9.5"),
        close_price=Decimal("10.5"),
        pre_close=Decimal("10"),
        pct_chg=Decimal(pct_chg),
        volume=Decimal("1000"),
        amount=Decimal("100000"),
        limit_up_price=Decimal("11"),
        limit_down_price=Decimal("9"),
    )


def _pool(
    stock_id: str,
    rank: int,
    *,
    watch_score: str,
    support_score: str,
    strong_grade: str = "A",
    prior7_limitup_days: int = 0,
    prior7_strong_days: int = 0,
) -> SubjectStockPoolDTO:
    return SubjectStockPoolDTO(
        trade_date=date(2026, 4, 23),
        subject_key="k",
        subject_name="n",
        stock_id=stock_id,
        stock_name="S",
        pool_rank=rank,
        metadata={
            "candidate_source": "strong_watch_pool",
            "watch_score": watch_score,
            "support_score": support_score,
            "support_type": "ma_support",
            "strong_grade": strong_grade,
            "support_refs": ["x1", "x2"],
            "role_tags": {"is_leader": rank == 1, "watch_tier": strong_grade},
            "prior7_limitup_days": prior7_limitup_days,
            "prior7_strong_days": prior7_strong_days,
        },
    )


def test_w2s_candidate_service_builds_formal_and_observe_only() -> None:
    svc = W2SCandidateService()
    bars = [
        _bar("A.SZ", "-1.5"),
        _bar("B.SZ", "1.0"),
    ]
    pool_rows = [
        _pool("A.SZ", 1, watch_score="92", support_score="88", strong_grade="S", prior7_limitup_days=2, prior7_strong_days=3),
        _pool("B.SZ", 1, watch_score="65", support_score="58", strong_grade="B", prior7_limitup_days=0, prior7_strong_days=1),
    ]
    prior = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="A.SZ",
            snapshot_version="v1",
            payload={"final_cycle_state": "repair"},
        )
    ]

    out = svc.build_candidates(bars=bars, pool_rows=pool_rows, prior_rows=prior)
    assert len(out) == 2
    by_id = {x.stock_id: x for x in out}
    assert by_id["A.SZ"].candidate_level == "formal"
    assert by_id["B.SZ"].candidate_level == "observe_only"
    assert any(rule.startswith("watch_score=") for rule in by_id["A.SZ"].evidence_rules)
    assert any(rule.startswith("support_hit_score=") for rule in by_id["A.SZ"].evidence_rules)


def test_w2s_candidate_service_rejects_weak_watch_inputs() -> None:
    svc = W2SCandidateService()
    bars = [_bar("C.SZ", "-2.0")]
    pool_rows = [
        _pool("C.SZ", 3, watch_score="35", support_score="40", strong_grade="REJECT"),
    ]
    out = svc.build_candidates(bars=bars, pool_rows=pool_rows, prior_rows=[])
    assert out == []
