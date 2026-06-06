from __future__ import annotations

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_contract_service import (
    OneToTwoBacktestContractService,
)


def test_one_to_two_backtest_contract_freeze_success() -> None:
    contract = OneToTwoBacktestContractService().freeze(("2026-06-04", "2026-06-05"))

    assert contract["strategy_id"] == "one_to_two"
    assert contract["strategy_version"] == "one_to_two_v1.0_post_market_plan"
    assert contract["signal_session"] == "post_market"
    assert contract["future_leak_guard_passed"] is True
    assert contract["blocked_dependency"] == ["Layer C", "D1"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"strategy_version": "other"}, "strategy_version"),
        ({"signal_session": "intraday"}, "signal_session"),
    ],
)
def test_one_to_two_backtest_contract_rejects_fixed_field_drift(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        OneToTwoBacktestContractService().freeze(("2026-06-04", "2026-06-05"), **kwargs)


def test_one_to_two_backtest_contract_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="invalid trade_date_range"):
        OneToTwoBacktestContractService().freeze(("2026-06-05", "2026-06-04"))

