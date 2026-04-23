from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO
from stock_processing_service.contracts.snapshots import (
    StockAbnormalEvent,
    StockDailySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)
from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence
from stock_processing_service.domain.services.cycle_judgement_service import CycleJudgement
from stock_processing_service.domain.services.state_transition_service import StateTransition


@dataclass(frozen=True)
class DailyProjectionBundle:
    daily_rows: list[StockDailySnapshot]
    subject_daily_rows: list[SubjectStockDailySnapshot]
    abnormal_rows: list[StockAbnormalEvent]
    leaderboard_rows: list[ThemeStockLeaderboard]


class DailySnapshotProjector:
    def project(
        self,
        *,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        evidences: list[CycleEvidence],
        judgements: list[CycleJudgement],
        bars_by_stock: dict[str, StockBarDTO],
        transition_by_stock: dict[str, StateTransition],
    ) -> tuple[list[StockDailySnapshot], list[SubjectStockDailySnapshot]]:
        daily_rows: list[StockDailySnapshot] = []
        subject_daily_rows: list[SubjectStockDailySnapshot] = []

        for evidence, judgement in zip(evidences, judgements):
            bar = bars_by_stock.get(evidence.stock_id)
            if bar is None:
                continue
            transition = transition_by_stock.get(evidence.stock_id)
            daily_rows.append(
                StockDailySnapshot(
                    trade_date=trade_date,
                    stock_id=evidence.stock_id,
                    stock_name=bar.stock_name,
                    close_price=bar.close_price,
                    pct_chg=bar.pct_chg,
                    volume=bar.volume,
                    amount=bar.amount,
                    limit_up_price=bar.limit_up_price,
                    limit_down_price=bar.limit_down_price,
                    snapshot_version=snapshot_version,
                    batch_id=batch_id,
                    trace_id=trace_id,
                    source_trace_id=trace_id,
                    labels={"final_cycle_state": judgement.final_cycle_state},
                    score_breakdown={
                        "mainline_strength_score": str(judgement.mainline_strength_score),
                        "fade_watch_score": str(judgement.fade_watch_score),
                        "fade_confirmed_score": str(judgement.fade_confirmed_score),
                        "divergence_score": str(judgement.divergence_score),
                        "repair_score": str(judgement.repair_score),
                        "transition_type": transition.transition_type if transition else "unknown",
                    },
                )
            )
            subject_daily_rows.append(
                SubjectStockDailySnapshot(
                    trade_date=trade_date,
                    subject_key=evidence.subject_key,
                    stock_id=evidence.stock_id,
                    subject_name=evidence.subject_name,
                    in_pool_flag=True,
                    pool_rank=None,
                    support_score=evidence.support_score,
                    snapshot_version=snapshot_version,
                    batch_id=batch_id,
                    trace_id=trace_id,
                    source_trace_id=trace_id,
                    role_tags={"mainline_alive": judgement.final_mainline_alive},
                    evidence_rules=["cycle_judgement_v1"],
                )
            )

        return daily_rows, subject_daily_rows


class AbnormalEventProjector:
    def project(
        self,
        *,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        evidences: list[CycleEvidence],
        judgements: list[CycleJudgement],
    ) -> list[StockAbnormalEvent]:
        rows: list[StockAbnormalEvent] = []
        for evidence, judgement in zip(evidences, judgements):
            if judgement.divergence_score < Decimal("20") and judgement.fade_confirmed_score < Decimal("55"):
                continue
            rows.append(
                StockAbnormalEvent(
                    trade_date=trade_date,
                    stock_id=evidence.stock_id,
                    event_type="cycle_divergence",
                    event_score=judgement.divergence_score,
                    evidence_rules=["divergence>=20_or_fade_confirmed>=55"],
                    raw_metrics={
                        "divergence_score": str(judgement.divergence_score),
                        "fade_confirmed_score": str(judgement.fade_confirmed_score),
                    },
                    snapshot_version=snapshot_version,
                    batch_id=batch_id,
                    trace_id=trace_id,
                    source_trace_id=trace_id,
                )
            )
        return rows


class LeaderboardProjector:
    def project(
        self,
        *,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        judgements: list[CycleJudgement],
    ) -> list[ThemeStockLeaderboard]:
        grouped_subject: dict[str, list[tuple[str, Decimal, str]]] = defaultdict(list)
        for j in judgements:
            grouped_subject[j.subject_key].append((j.stock_id, j.mainline_strength_score, j.subject_name))

        rows: list[ThemeStockLeaderboard] = []
        for subject_key, scored in grouped_subject.items():
            scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
            for idx, (stock_id, score, _subject_name) in enumerate(scored_sorted, start=1):
                rows.append(
                    ThemeStockLeaderboard(
                        trade_date=trade_date,
                        subject_key=subject_key,
                        stock_id=stock_id,
                        leaderboard_rank=idx,
                        leader_score=score,
                        score_breakdown={"mainline_strength_score": str(score)},
                        snapshot_version=snapshot_version,
                        batch_id=batch_id,
                        trace_id=trace_id,
                        source_trace_id=trace_id,
                        role_name="leader" if idx == 1 else None,
                    )
                )
        return rows
