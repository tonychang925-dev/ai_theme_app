from __future__ import annotations

from stock_service.models import PreMarketAuctionSignal
from stock_service.services.auction_signal_validation_service import (
    AuctionSignalValidationService,
    AuctionValidationMarketInput,
)


def _signal(level: str, action: str = "watch") -> PreMarketAuctionSignal:
    return PreMarketAuctionSignal(
        trade_date="2026-04-03",
        stock_id="600339.SH",
        stock_name="中油工程",
        subject_key="9012345",
        theme_name="石油",
        role_label="龙二",
        auction_signal_score=72.5,
        auction_signal_level=level,
        signal_type="卡位加强",
        leader_status="",
        action_today=action,
    )


def test_strong_signal_validates_on_limit_up():
    service = AuctionSignalValidationService()
    result = service.build_validation(
        _signal("strong", "act"),
        AuctionValidationMarketInput(close_pct=10.02, close_price=12.1, hit_limit_up=True, close_rank_order=1, close_is_leader=True),
    )
    assert result.signal_validated is True
    assert result.validation_result == "confirmed_strong"


def test_watch_signal_fails_on_negative_close():
    service = AuctionSignalValidationService()
    result = service.build_validation(
        _signal("watch", "watch"),
        AuctionValidationMarketInput(close_pct=-1.2, close_price=11.0, hit_limit_up=False, close_rank_order=4, close_is_leader=False),
    )
    assert result.signal_validated is False
    assert result.validation_result == "watch_failed"


def test_invalid_signal_confirmed_when_close_weak():
    service = AuctionSignalValidationService()
    result = service.build_validation(
        _signal("invalid", "avoid"),
        AuctionValidationMarketInput(close_pct=-3.5, close_price=10.3, hit_limit_up=False, close_rank_order=8, close_is_leader=False),
    )
    assert result.signal_validated is True
    assert result.validation_result == "reject_confirmed"


def test_validation_marks_pending_when_daily_result_missing():
    service = AuctionSignalValidationService()
    result = service.build_validation(
        _signal("watch", "watch"),
        AuctionValidationMarketInput(
            close_pct=0.0,
            close_price=0.0,
            hit_limit_up=False,
            close_rank_order=0,
            close_is_leader=False,
            has_daily_result=False,
        ),
    )
    assert result.signal_validated is False
    assert result.validation_result == "pending_daily_result"
