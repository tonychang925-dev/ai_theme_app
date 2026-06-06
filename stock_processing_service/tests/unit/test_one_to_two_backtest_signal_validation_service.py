from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_signal_validation_service import (
    OneToTwoBacktestSignalValidationService,
)


class _Client:
    def __init__(self, signals: list[dict[str, object]]) -> None:
        self.signals = signals
        self.calls: list[tuple[str, list[object]]] = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, list(params)))
        normalized = str(sql).strip().lower()
        if normalized.startswith("select * from strategy_signal_daily"):
            run_id, strategy_id, strategy_version = params
            return [
                dict(row)
                for row in self.signals
                if row.get("run_id") == run_id
                and row.get("strategy_id") == strategy_id
                and row.get("strategy_version") == strategy_version
            ]
        return []


class _Gateway:
    def __init__(self, signals: list[dict[str, object]]) -> None:
        self._client = _Client(signals)


class _ReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return SimpleNamespace(calendar_is_open=True)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids=None):
        stock_id = stock_ids[0]
        if stock_id == "600367.SH":
            return [
                SimpleNamespace(
                    stock_id="600367.SH",
                    open_price=10,
                    high_price=10,
                    low_price=10,
                    close_price=10,
                    limit_up_price=10,
                    open_board_count=0,
                )
            ]
        if stock_id == "600368.SH":
            return [
                SimpleNamespace(
                    stock_id="600368.SH",
                    open_price=9,
                    high_price=10,
                    low_price=9,
                    close_price=9.5,
                    limit_up_price=10,
                    open_board_count=1,
                )
            ]
        if stock_id == "600369.SH":
            return [
                SimpleNamespace(
                    stock_id="600369.SH",
                    open_price=9,
                    high_price=9.4,
                    low_price=8.8,
                    close_price=9,
                    limit_up_price=10,
                    open_board_count=0,
                )
            ]
        return []


def _signal(stock_id: str, trade_date: str = "2026-06-04") -> dict[str, object]:
    return {
        "signal_id": f"sig-{stock_id}",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "trade_date": trade_date,
        "stock_id": stock_id,
        "signal_level": "focus",
        "score": 93.2,
    }


def _signal_with_version(
    stock_id: str,
    strategy_version: str,
    trade_date: str = "2026-06-04",
) -> dict[str, object]:
    signal = _signal(stock_id, trade_date=trade_date)
    signal["strategy_version"] = strategy_version
    return signal


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_validation_labels_outcomes() -> None:
    gw = _Gateway([
        _signal("600367.SH"),
        _signal("600368.SH"),
        _signal("600369.SH"),
    ])
    service = OneToTwoBacktestSignalValidationService(_ReadPort(), gw)

    report = await service.validate("run-001")

    assert report["validated_count"] == 3
    assert report["written"] == 3
    delete_sql, delete_params = gw._client.calls[0]
    assert "DELETE FROM strategy_signal_validation" in delete_sql
    assert "strategy_id" in delete_sql
    assert "strategy_version" in delete_sql
    assert delete_params == ["run-001", "one_to_two", "one_to_two_v1.0_post_market_plan"]

    select_sql, select_params = gw._client.calls[1]
    assert "SELECT * FROM strategy_signal_daily" in select_sql
    assert "strategy_version" in select_sql
    assert select_params == ["run-001", "one_to_two", "one_to_two_v1.0_post_market_plan"]

    write_calls = gw._client.calls[2:]
    assert len(write_calls) == 3
    first_params = write_calls[0][1]
    second_params = write_calls[1][1]
    third_params = write_calls[2][1]
    assert first_params[17] == "A_SEALED_SECOND_BOARD_PROXY"
    assert first_params[18] == "daily_close_proxy"
    assert second_params[17] == "B_TOUCHED_BUT_BROKEN"
    assert second_params[18] == "daily_high_proxy"
    assert third_params[17] == "C_FAILED_NO_TOUCH"
    assert third_params[18] == "daily_close_proxy"


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_validation_missing_bar_is_d_no_data() -> None:
    gw = _Gateway([_signal("600370.SH")])
    service = OneToTwoBacktestSignalValidationService(_ReadPort(), gw)

    report = await service.validate("run-001")

    assert report["validated_count"] == 1
    params = gw._client.calls[2][1]
    assert params[17] == "D_NO_DATA"
    assert params[18] == "missing"
    assert params[33] == "missing_bar"


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_validation_delete_scoped_by_strategy_id() -> None:
    gw = _Gateway([_signal("600367.SH")])
    service = OneToTwoBacktestSignalValidationService(_ReadPort(), gw)

    await service.validate("run-001")

    delete_sql, delete_params = gw._client.calls[0]
    assert "DELETE FROM strategy_signal_validation" in delete_sql
    assert "strategy_id" in delete_sql
    assert "strategy_version" in delete_sql
    assert delete_params == ["run-001", "one_to_two", "one_to_two_v1.0_post_market_plan"]


@pytest.mark.asyncio
async def test_validation_loads_signals_scoped_by_strategy_version() -> None:
    gw = _Gateway([
        _signal_with_version("600367.SH", "one_to_two_v1.0_post_market_plan"),
        _signal_with_version("600368.SH", "one_to_two_v1.0_pre_market_plan"),
    ])
    service = OneToTwoBacktestSignalValidationService(_ReadPort(), gw)

    report = await service.validate("run-001")

    assert report["validated_count"] == 1
    delete_sql, delete_params = gw._client.calls[0]
    assert "strategy_version" in delete_sql
    assert delete_params == ["run-001", "one_to_two", "one_to_two_v1.0_post_market_plan"]
    select_sql, select_params = gw._client.calls[1]
    assert "strategy_version" in select_sql
    assert select_params == ["run-001", "one_to_two", "one_to_two_v1.0_post_market_plan"]
    write_calls = gw._client.calls[2:]
    assert len(write_calls) == 1
    assert write_calls[0][1][0] == "sig-600367.SH"
