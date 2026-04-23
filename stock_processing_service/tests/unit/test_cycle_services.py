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
            payload={"mainline_state": "mainline_active"},
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
    assert evidences[0].previous_state == "acceleration"
    assert any(str(item).startswith("subject_positive_ratio=") for item in evidences[0].support_refs)

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


def test_cycle_pipeline_subject_diffusion_evidence() -> None:
    builder = CycleEvidenceBuilder()
    bars, pool, context, prior = _base_rows(pct="8.0", pool_rank=1)
    bars.append(
        StockBarDTO(
            trade_date=date(2026, 4, 23),
            stock_id="000002.SZ",
            stock_name="PingAn2",
            open_price=Decimal("9"),
            high_price=Decimal("10"),
            low_price=Decimal("8.9"),
            close_price=Decimal("9.9"),
            pre_close=Decimal("9"),
            pct_chg=Decimal("10.0"),
            volume=Decimal("90000"),
            amount=Decimal("800000"),
            limit_up_price=Decimal("9.9"),
            limit_down_price=Decimal("8.1"),
        )
    )
    pool.append(
        SubjectStockPoolDTO(
            trade_date=date(2026, 4, 23),
            subject_key="robotics",
            subject_name="Robotics",
            stock_id="000002.SZ",
            stock_name="PingAn2",
            pool_rank=2,
        )
    )
    prior.append(
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="000002.SZ",
            snapshot_version="v0",
            payload={"final_cycle_state": "repair"},
        )
    )
    evidences = builder.build_evidences(bars, pool, context, prior)
    e1 = next(e for e in evidences if e.stock_id == "000001.SZ")
    assert any(item == "subject_diffusion_positive" for item in e1.support_refs)
    assert e1.score_flags["relay_score_fallback"] is False


def test_cycle_pipeline_external_evidence_override() -> None:
    builder = CycleEvidenceBuilder()
    bars, pool, context, prior = _base_rows(pct="1.0", pool_rank=10)
    pool[0].metadata.update(
        {
            "leader_score": "92",
            "relay_score": "88",
            "board_score": "85",
            "support_score": "77",
            "event_score": "66",
        }
    )
    evidences = builder.build_evidences(bars, pool, context, prior)
    e = evidences[0]
    assert e.leader_score == Decimal("92")
    assert e.relay_score == Decimal("88")
    assert e.board_score == Decimal("85")
    assert e.support_score == Decimal("77")
    assert e.event_score == Decimal("66")
    assert e.score_flags["leader_score_external"] is True
    assert e.score_flags["relay_score_external"] is True
    assert e.score_flags["board_score_external"] is True
    assert e.score_flags["support_score_external"] is True


def test_cycle_pipeline_context_external_evidence_override() -> None:
    builder = CycleEvidenceBuilder()
    bars, pool, context, prior = _base_rows(pct="1.0", pool_rank=10)
    context[0].metadata.update(
        {
            "event_continuity_score": "61",
            "leader_alive_score": "81",
            "relay_strength_score": "73",
            "diffusion_score": "69",
        }
    )
    evidences = builder.build_evidences(bars, pool, context, prior)
    e = evidences[0]
    assert e.event_score == Decimal("61")
    assert e.leader_score == Decimal("81")
    assert e.relay_score == Decimal("73")
    assert e.board_score == Decimal("69")
    assert e.score_flags["event_score_external"] is True
    assert e.score_flags["leader_score_external"] is True


def test_cycle_state_sensitivity_to_evidence_gap() -> None:
    builder = CycleEvidenceBuilder()
    judger = CycleJudgementService()

    # Baseline: same stock with regular evidence.
    bars, pool, context, prior = _base_rows(pct="6.0", pool_rank=1)
    normal_evidence = builder.build_evidences(bars, pool, context, prior)[0]
    normal_state = judger.judge_many([normal_evidence])[0].final_cycle_state

    # Evidence-gap scenario: same input frame, but explicit weak external evidence injected.
    pool_weak = [
        SubjectStockPoolDTO(
            trade_date=pool[0].trade_date,
            subject_key=pool[0].subject_key,
            subject_name=pool[0].subject_name,
            stock_id=pool[0].stock_id,
            stock_name=pool[0].stock_name,
            pool_rank=pool[0].pool_rank,
            metadata={
                "leader_score": "20",
                "relay_score": "20",
                "board_score": "22",
                "support_score": "20",
                "event_score": "10",
            },
        )
    ]
    prior_weak = [
        PriorSnapshotDTO(
            trade_date=date(2026, 4, 22),
            stock_id="000001.SZ",
            snapshot_version="v0",
            payload={"final_cycle_state": "fade_watch"},
        )
    ]
    weak_evidence = builder.build_evidences(bars, pool_weak, context, prior_weak)[0]
    weak_judgement = judger.judge_many([weak_evidence])[0]

    # We expect a meaningful state shift under evidence degradation.
    assert weak_judgement.final_cycle_state in {"fade_watch", "fade_confirmed"}
    assert weak_judgement.fade_confirmed_evidence_count >= 3
    assert normal_state != weak_judgement.final_cycle_state
