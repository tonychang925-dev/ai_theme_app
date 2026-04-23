from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_processing_service.contracts.events import (
    REJECT_LOW_AUCTION_STRENGTH,
    REJECT_NEGATIVE_OPENING,
    REJECT_NO_AUCTION_DATA,
    REJECT_WEAK_AUCTION_AMOUNT,
)
from stock_processing_service.domain.services.w2s_auction_scorer import W2SAuctionScorer
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate


@dataclass(frozen=True)
class W2SConfirmedPick:
    stock_id: str
    candidate_level: str
    confirm_level: str
    confirm_score: Decimal
    approved: bool
    reject_reason_code: str | None
    evidence_rules: list[str]


class W2SConfirmService:
    def __init__(self, auction_scorer: W2SAuctionScorer | None = None) -> None:
        self._scorer = auction_scorer or W2SAuctionScorer()

    def confirm(
        self,
        candidates: list[W2SCandidate],
        auctions: list[StockAuctionDTO],
    ) -> list[W2SConfirmedPick]:
        candidate_by_stock = {c.stock_id: c for c in candidates}
        auctions_by_stock = {a.stock_id: a for a in auctions}

        picks: list[W2SConfirmedPick] = []
        for stock_id, candidate in candidate_by_stock.items():
            auction = auctions_by_stock.get(stock_id)
            if auction is None:
                picks.append(
                    W2SConfirmedPick(
                        stock_id=stock_id,
                        candidate_level=candidate.candidate_level,
                        confirm_level="X",
                        confirm_score=Decimal("0"),
                        approved=False,
                        reject_reason_code=REJECT_NO_AUCTION_DATA,
                        evidence_rules=["reject:no_auction_data"],
                    )
                )
                continue

            scored = self._scorer.score_one(auction)
            approved = scored.decision in {"A", "B", "C"}
            reject_reason_code = None
            if not approved:
                open_pct = auction.auction_open_pct or Decimal("0")
                amount = auction.auction_amount or Decimal("0")
                if open_pct < Decimal("-2"):
                    reject_reason_code = REJECT_NEGATIVE_OPENING
                elif amount < Decimal("500000"):
                    reject_reason_code = REJECT_WEAK_AUCTION_AMOUNT
                else:
                    reject_reason_code = REJECT_LOW_AUCTION_STRENGTH
            picks.append(
                W2SConfirmedPick(
                    stock_id=stock_id,
                    candidate_level=candidate.candidate_level,
                    confirm_level=scored.decision,
                    confirm_score=scored.final_score,
                    approved=approved,
                    reject_reason_code=reject_reason_code,
                    evidence_rules=candidate.evidence_rules + scored.evidence_rules,
                )
            )

        picks.sort(key=lambda p: p.confirm_score, reverse=True)
        return picks
