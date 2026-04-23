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


def test_cycle_pipeline_basic() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()
    transition = StateTransitionService()

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
            pct_chg=Decimal("8.0"),
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
            pool_rank=1,
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
            payload={"final_cycle_state": "mainline_active"},
        )
    ]

    evidences = builder.build_evidences(bars, pool, context, prior)
    assert len(evidences) == 1
    assert evidences[0].missing_flags["bar_missing"] is False

    judgements = judger.judge_many(evidences)
    assert len(judgements) == 1
    assert judgements[0].final_cycle_state in {
        "mainline_active",
        "repair",
        "fade_watch",
        "fade_confirmed",
        "observed",
    }

    transitions = transition.build_transitions(
        {judgements[0].stock_id: judgements[0].final_cycle_state},
        {"000001.SZ": "mainline_active"},
    )
    assert len(transitions) == 1
