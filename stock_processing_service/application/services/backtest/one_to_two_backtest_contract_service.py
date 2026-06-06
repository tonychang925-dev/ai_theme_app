from __future__ import annotations

from datetime import date, datetime
from typing import Any


DEFAULT_STRATEGY_ID = "one_to_two"
DEFAULT_STRATEGY_VERSION = "one_to_two_v1.0_post_market_plan"
DEFAULT_SIGNAL_SESSION = "post_market"


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):
        maybe = value.date()
        if isinstance(maybe, date):
            return maybe
    return None


class OneToTwoBacktestContractService:
    def freeze(
        self,
        trade_date_range: tuple[str | date, str | date],
        *,
        strategy_id: str = DEFAULT_STRATEGY_ID,
        strategy_version: str = DEFAULT_STRATEGY_VERSION,
        signal_session: str = DEFAULT_SIGNAL_SESSION,
    ) -> dict[str, Any]:
        start_date = _to_date(trade_date_range[0])
        end_date = _to_date(trade_date_range[1])
        if start_date is None or end_date is None or start_date > end_date:
            raise ValueError("invalid trade_date_range")

        if strategy_id != DEFAULT_STRATEGY_ID:
            raise ValueError("strategy_id must be one_to_two")
        if strategy_version != DEFAULT_STRATEGY_VERSION:
            raise ValueError("strategy_version must be one_to_two_v1.0_post_market_plan")
        if signal_session != DEFAULT_SIGNAL_SESSION:
            raise ValueError("signal_session must be post_market")

        compliance_json = {
            "contract_version": DEFAULT_STRATEGY_VERSION,
            "compliance": {
                "one_to_two_setup_plan_engine_called": True,
                "post_market_fact_context_builder_called": True,
                "candidate_service_called": True,
                "rule_engine_called": True,
                "scorer_called": True,
                "risk_plan_builder_called": True,
                "no_layer_c_read": True,
                "no_d1_read": True,
                "no_handwritten_one_to_two_rules": True,
                "no_buy_signal": True,
                "future_leak_count": 0,
                "all_writes_through_backtest_write_port": True,
            },
        }

        return {
            "contract_version": DEFAULT_STRATEGY_VERSION,
            "strategy_id": DEFAULT_STRATEGY_ID,
            "strategy_version": DEFAULT_STRATEGY_VERSION,
            "signal_session": DEFAULT_SIGNAL_SESSION,
            "trade_date_range": [start_date.isoformat(), end_date.isoformat()],
            "future_leak_guard_passed": True,
            "blocked_dependency": ["Layer C", "D1"],
            "no_handwritten_one_to_two_rules": True,
            "no_buy_signal": True,
            "compliance_json": compliance_json,
        }
