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
    support_refs: list[str] = field(default_factory=list)

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
                        support_refs=[],
                        score_flags={
                            "computed": False,
                            "event_score_fallback": True,
                            "leader_score_fallback": True,
                            "relay_score_fallback": True,
                            "board_score_fallback": True,
                            "support_score_fallback": True,
                        },
                        missing_flags={
                            "bar_missing": True,
                            "context_missing": context_by_subject.get(pool_row.subject_key) is None,
                            "prior_missing": prior_by_stock.get(pool_row.stock_id) is None,
                            "subject_pool_missing": False,
                        },
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

            event_score = Decimal(str(min(len(tags) * 18, 100))) if tags else Decimal("8")
            continuity_score = Decimal("45")
            if prev_state in {"start", "fermentation", "acceleration", "divergence", "repair"}:
                continuity_score = Decimal("78")
            elif prev_state in {"fade_watch", "fade_confirmed"}:
                continuity_score = Decimal("58")

            leader_score = max(Decimal("0"), min(Decimal("100"), pct * Decimal("9") + Decimal("40")))
            relay_score = max(Decimal("0"), min(Decimal("100"), pct * Decimal("6") + Decimal("45")))
            board_score = max(Decimal("0"), min(Decimal("100"), Decimal(str(len(tags) * 14)) + rank_score * Decimal("0.4")))
            support_score = max(Decimal("0"), min(Decimal("100"), rank_score * Decimal("0.7") + continuity_score * Decimal("0.3")))

            support_refs: list[str] = []
            if rank <= 3:
                support_refs.append("pool_rank_top3")
            if continuity_score >= Decimal("70"):
                support_refs.append("prior_state_continuity")
            if pct >= Decimal("0"):
                support_refs.append("non_negative_pct")
            if not support_refs:
                support_refs.append("fallback_support")

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
                    support_refs=support_refs,
                    score_flags={
                        "computed": True,
                        "event_score_fallback": not bool(tags),
                        "leader_score_fallback": False,
                        "relay_score_fallback": False,
                        "board_score_fallback": False,
                        "support_score_fallback": False,
                    },
                    missing_flags={
                        "bar_missing": False,
                        "context_missing": context is None,
                        "prior_missing": prior is None,
                        "subject_pool_missing": False,
                    },
                )
            )
        return evidences
