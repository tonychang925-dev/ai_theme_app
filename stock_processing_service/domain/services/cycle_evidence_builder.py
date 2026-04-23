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
    support_score: Decimal
    momentum_score: Decimal
    continuity_score: Decimal
    context_score: Decimal
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

        evidences: list[CycleEvidence] = []
        for pool_row in pool_rows:
            stock_bar = next((b for b in bars if b.stock_id == pool_row.stock_id), None)
            if stock_bar is None:
                evidences.append(
                    CycleEvidence(
                        trade_date=pool_row.trade_date,
                        stock_id=pool_row.stock_id,
                        subject_key=pool_row.subject_key,
                        subject_name=pool_row.subject_name,
                        close_price=Decimal("0"),
                        pct_chg=Decimal("0"),
                        support_score=Decimal("0"),
                        momentum_score=Decimal("0"),
                        continuity_score=Decimal("0"),
                        context_score=Decimal("0"),
                        score_flags={"computed": False},
                        missing_flags={"bar_missing": True},
                    )
                )
                continue

            context = context_by_subject.get(pool_row.subject_key)
            prior = prior_by_stock.get(pool_row.stock_id)

            pct = stock_bar.pct_chg
            pool_rank = pool_row.pool_rank if pool_row.pool_rank is not None else 999
            support_score = Decimal("100") / Decimal(str(max(pool_rank, 1)))
            momentum_score = max(Decimal("0"), min(Decimal("100"), pct * Decimal("10") + Decimal("50")))

            continuity = Decimal("50")
            if prior:
                prev_state = str(prior.payload.get("final_cycle_state", ""))
                if prev_state in {"mainline_active", "repair"}:
                    continuity = Decimal("80")
                elif prev_state:
                    continuity = Decimal("60")

            context_score = Decimal("40")
            if context and context.theme_context_tags:
                context_score = Decimal(str(min(len(context.theme_context_tags) * 15, 100)))

            evidences.append(
                CycleEvidence(
                    trade_date=stock_bar.trade_date,
                    stock_id=pool_row.stock_id,
                    subject_key=pool_row.subject_key,
                    subject_name=pool_row.subject_name,
                    close_price=stock_bar.close_price,
                    pct_chg=stock_bar.pct_chg,
                    support_score=support_score,
                    momentum_score=momentum_score,
                    continuity_score=continuity,
                    context_score=context_score,
                    score_flags={"computed": True},
                    missing_flags={
                        "bar_missing": False,
                        "context_missing": context is None,
                        "prior_missing": prior is None,
                    },
                )
            )
        return evidences
