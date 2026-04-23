from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import StockAuctionDTO


@dataclass(frozen=True)
class AuctionScore:
    stock_id: str
    auction_score: Decimal
    risk_score: Decimal
    final_score: Decimal
    decision: str
    evidence_rules: list[str]


class W2SAuctionScorer:
    def score_one(self, auction: StockAuctionDTO) -> AuctionScore:
        open_pct = auction.auction_open_pct or Decimal("0")
        auction_amt = auction.auction_amount or Decimal("0")
        tail_vwap = auction.tail_auction_vwap or Decimal("0")

        open_signal = max(Decimal("0"), min(Decimal("100"), open_pct * Decimal("10") + Decimal("50")))
        amount_signal = max(Decimal("0"), min(Decimal("100"), auction_amt / Decimal("1000000") * Decimal("20")))
        tail_signal = max(Decimal("0"), min(Decimal("100"), tail_vwap * Decimal("5")))
        auction_score = open_signal * Decimal("0.5") + amount_signal * Decimal("0.3") + tail_signal * Decimal("0.2")

        risk = Decimal("0")
        evidence = [f"open_pct={open_pct}", f"auction_amount={auction_amt}"]
        if open_pct < Decimal("-2"):
            risk += Decimal("25")
            evidence.append("risk:open_pct_lt_-2")
        if auction_amt < Decimal("500000"):
            risk += Decimal("15")
            evidence.append("risk:auction_amount_lt_500k")

        final = auction_score - risk
        if final >= Decimal("75"):
            decision = "A"
        elif final >= Decimal("65"):
            decision = "B"
        elif final >= Decimal("55"):
            decision = "C"
        else:
            decision = "X"

        return AuctionScore(
            stock_id=auction.stock_id,
            auction_score=auction_score,
            risk_score=risk,
            final_score=final,
            decision=decision,
            evidence_rules=evidence,
        )
