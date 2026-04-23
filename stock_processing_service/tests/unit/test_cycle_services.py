from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import (
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
)
from stock_processing_service.domain.services import (
    CycleEvidenceBuilder,
    CycleJudgementService,
    StateTransitionService,
)


def _base_rows(pct: str = "8.0", pool_rank: int = 1):
    bars = [
        StockBarDTO(
            trade_date=date(2026, 4, 23),
            stock_id="000001.SZ",
            stock_name="PingAn",
            open_price=Decimal("10"),
            high_price=Decimal("11"),
            low_price=Decimal("9.8"),
            close_price=Decimal("10.8"),
            pre_close=Decimal("10"),
            pct_chg=Decimal(pct),
            volume=Decimal("100000"),
            amount=Decimal("1000000"),
            limit_up_price=Decimal("11"),
            limit_down_price=Decimal("9"),
        )
    ]
    pool = [
        SubjectStockPoolDTO(
            trade_date=date(2026, 4, 23),
            subject_key="robotics",
            subject_name="Robotics",
            stock_id="000001.SZ",
            stock_name="PingAn",
            pool_rank=pool_rank,
        )
    ]
    context = [
        SubjectContextDTO(
            trade_date=date(2026, 4, 23),
            subject_key="robotics",
            subject_name="Robotics",
            theme_context_tags=["policy", "volume"],
        )
    ]
    prior = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="000001.SZ",
            snapshot_version="v0",
            payload={"final_cycle_state": "divergence"},
        )
    ]
    return bars, pool, context, prior


def test_cycle_pipeline_normal() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()
    transition = StateTransitionService()

    bars, pool, context, prior = _base_rows(pct="8.0", pool_rank=1)

    evidences = builder.build_evidences(bars, pool, context, prior)
    assert len(evidences) == 1
    assert evidences[0].missing_flags["bar_missing"] is False
    assert evidences[0].missing_flags["subject_pool_missing"] is False
    assert evidences[0].score_flags["computed"] is True
    assert isinstance(evidences[0].support_refs, list) and len(evidences[0].support_refs) >= 1

    judgements = judger.judge_many(evidences)
    assert len(judgements) == 1
    assert judgements[0].final_cycle_state in {
        "start",
        "fermentation",
        "acceleration",
        "divergence",
        "repair",
        "fade_watch",
        "fade_confirmed",
    }

    transitions = transition.build_transitions(
        {judgements[0].stock_id: judgements[0].final_cycle_state},
        {"000001.SZ": "divergence"},
    )
    assert len(transitions) == 1


def test_cycle_pipeline_boundary_fade_confirmed_requires_multi_evidence() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()

    bars, pool, context, prior = _base_rows(pct="-8.0", pool_rank=99)
    prior[0] = PriorSnapshotDTO(
        trade_date=date(2026, 4, 22),
        stock_id="000001.SZ",
        snapshot_version="v0",
        payload={"final_cycle_state": "fade_watch"},
    )

    evidences = builder.build_evidences(bars, pool, context, prior)
    judgement = judger.judge_many(evidences)[0]
    if judgement.final_cycle_state == "fade_confirmed":
        assert judgement.fade_confirmed_evidence_count >= 3


def test_cycle_pipeline_missing_evidence() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()

    _, pool, context, prior = _base_rows()
    evidences = builder.build_evidences([], pool, context, prior)
    assert evidences[0].missing_flags["bar_missing"] is True
    assert evidences[0].missing_flags["subject_pool_missing"] is False
    assert evidences[0].score_flags["event_score_fallback"] is True

    judgement = judger.judge_many(evidences)[0]
    assert judgement.final_cycle_state in {"start", "fade_watch", "fade_confirmed"}


def test_cycle_pipeline_extreme_weak_evidence() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()

    bars, pool, context, prior = _base_rows(pct="-12.0", pool_rank=120)
    context = []
    prior = []
    evidences = builder.build_evidences(bars, pool, context, prior)
    e = evidences[0]
    assert e.score_flags["event_score_fallback"] is True
    assert e.missing_flags["context_missing"] is True
    assert e.missing_flags["prior_missing"] is True

    judgement = judger.judge_many(evidences)[0]
    assert judgement.final_cycle_state in {"fade_watch", "fade_confirmed", "start"}
