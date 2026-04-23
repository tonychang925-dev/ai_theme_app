from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_processing_service.contracts.events import (
    REJECT_NO_AUCTION_DATA,
    REJECT_WEAK_AUCTION_AMOUNT,
)
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate
from stock_processing_service.domain.services.w2s_confirm_service import W2SConfirmService


def test_reject_reason_no_auction_data() -> None:
    svc = W2SConfirmService()
    candidates = [
        W2SCandidate(
            trade_date="2026-04-23",
            stock_id="000001.SZ",
            stock_name="A",
            subject_key="s1",
            subject_name="S1",
            support_score=Decimal("70"),
            momentum_score=Decimal("70"),
            candidate_score=Decimal("70"),
            candidate_level="B",
            candidate_source="strong_watch_pool",
            evidence_rules=["x"],
        )
    ]
    picks = svc.confirm(candidates=candidates, auctions=[])
    assert len(picks) == 1
    assert picks[0].approved is False
    assert picks[0].reject_reason_code == REJECT_NO_AUCTION_DATA


def test_reject_reason_weak_auction_amount() -> None:
    svc = W2SConfirmService()
    candidates = [
        W2SCandidate(
            trade_date="2026-04-23",
            stock_id="000001.SZ",
            stock_name="A",
            subject_key="s1",
            subject_name="S1",
            support_score=Decimal("70"),
            momentum_score=Decimal("70"),
            candidate_score=Decimal("70"),
            candidate_level="B",
            candidate_source="strong_watch_pool",
            evidence_rules=["x"],
        )
    ]
    auctions = [
        StockAuctionDTO(
            trade_date=date(2026, 4, 23),
            stock_id="000001.SZ",
            auction_open_pct=Decimal("0.5"),
            auction_amount=Decimal("100000"),
            tail_auction_vwap=Decimal("10"),
        )
    ]
    picks = svc.confirm(candidates=candidates, auctions=auctions)
    assert len(picks) == 1
    assert picks[0].approved is False
    assert picks[0].reject_reason_code == REJECT_WEAK_AUCTION_AMOUNT
