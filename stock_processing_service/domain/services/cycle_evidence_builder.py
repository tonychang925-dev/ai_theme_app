from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import (
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
)


@dataclass(frozen=True)
class CycleEvidence:
    trade_date: date
    stock_id: str
    subject_key: str
    subject_name: str
    close_price: Decimal
    pct_chg: Decimal
    previous_state: str

    # Core score factors aligned with legacy v2 semantics.
    event_score: Decimal
    continuity_score: Decimal
    leader_score: Decimal
    relay_score: Decimal
    board_score: Decimal
    support_score: Decimal

    score_flags: dict[str, bool] = field(default_factory=dict)
    missing_flags: dict[str, bool] = field(default_factory=dict)


class CycleEvidenceBuilder:
    def build_evidences(
        self,
        bars: list[StockBarDTO],
        pool_rows: list[SubjectStockPoolDTO],
        context_rows: list[SubjectContextDTO],
        prior_rows: list[PriorSnapshotDTO],
    ) -> list[CycleEvidence]:
        context_by_subject = {row.subject_key: row for row in context_rows}
        prior_by_stock = {row.stock_id: row for row in prior_rows}
        bars_by_stock = {bar.stock_id: bar for bar in bars}

        evidences: list[CycleEvidence] = []
        for pool_row in pool_rows:
            stock_bar = bars_by_stock.get(pool_row.stock_id)
            if stock_bar is None:
                evidences.append(
                    CycleEvidence(
                        trade_date=pool_row.trade_date,
                        stock_id=pool_row.stock_id,
                        subject_key=pool_row.subject_key,
                        subject_name=pool_row.subject_name,
                        close_price=Decimal("0"),
                        pct_chg=Decimal("0"),
                        previous_state="unknown",
                        event_score=Decimal("0"),
                        continuity_score=Decimal("0"),
                        leader_score=Decimal("0"),
                        relay_score=Decimal("0"),
                        board_score=Decimal("0"),
                        support_score=Decimal("0"),
                        score_flags={"computed": False},
                        missing_flags={"bar_missing": True},
                    )
                )
                continue

            context = context_by_subject.get(pool_row.subject_key)
            prior = prior_by_stock.get(pool_row.stock_id)

            prev_state = "unknown"
            if prior:
                prev_state = str(prior.payload.get("final_cycle_state", "unknown"))

            tags = (context.theme_context_tags if context else []) or []
            rank = pool_row.pool_rank if pool_row.pool_rank is not None else 999
            rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
            pct = stock_bar.pct_chg

            event_score = Decimal(str(min(len(tags) * 18, 100)))
            continuity_score = Decimal("45")
            if prev_state in {"start", "fermentation", "acceleration", "divergence", "repair"}:
                continuity_score = Decimal("78")
            elif prev_state in {"fade_watch", "fade_confirmed"}:
                continuity_score = Decimal("58")

            leader_score = max(Decimal("0"), min(Decimal("100"), pct * Decimal("9") + Decimal("40")))
            relay_score = max(Decimal("0"), min(Decimal("100"), pct * Decimal("6") + Decimal("45")))
            board_score = max(Decimal("0"), min(Decimal("100"), Decimal(str(len(tags) * 14)) + rank_score * Decimal("0.4")))
            support_score = max(Decimal("0"), min(Decimal("100"), rank_score * Decimal("0.7") + continuity_score * Decimal("0.3")))

            evidences.append(
                CycleEvidence(
                    trade_date=stock_bar.trade_date,
                    stock_id=pool_row.stock_id,
                    subject_key=pool_row.subject_key,
                    subject_name=pool_row.subject_name,
                    close_price=stock_bar.close_price,
                    pct_chg=stock_bar.pct_chg,
                    previous_state=prev_state,
                    event_score=event_score,
                    continuity_score=continuity_score,
                    leader_score=leader_score,
                    relay_score=relay_score,
                    board_score=board_score,
                    support_score=support_score,
                    score_flags={"computed": True},
                    missing_flags={
                        "bar_missing": False,
                        "context_missing": context is None,
                        "prior_missing": prior is None,
                    },
                )
            )
        return evidences
