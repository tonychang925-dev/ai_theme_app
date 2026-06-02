from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.application.services.engine_report_adapter import EngineReportAdapter
from stock_processing_service.application.services.post_market_engine_report_composer import (
    PostMarketEngineReportComposer,
)
from stock_processing_service.application.services.pre_market_window import resolve_pre_market_window


class PreMarketEngineBridgeService:
    """Bridge yesterday's DailyReviewV2 engine output into pre-market consumers."""

    async def build(self, *, gateway: Any, trade_date: date) -> dict[str, Any]:
        window = await resolve_pre_market_window(trade_date, gateway=gateway)
        prev_row = await gateway.get_existing_post_market_recap_snapshot(window.prev_trade_date)

        engine_payload: dict[str, Any] = {}
        recap_doc: dict[str, Any] = {}
        legacy_payload: dict[str, Any] = {}

        if isinstance(prev_row, dict) and prev_row:
            legacy_payload = self._normalize_payload(prev_row)
            recap_doc = self._extract_recap_doc(legacy_payload)
            engine_payload = self._compose_engine_payload(recap_doc)

        if not engine_payload and isinstance(legacy_payload.get("daily_review_v2"), dict):
            engine_payload = dict(legacy_payload.get("daily_review_v2") or {})

        adapter = EngineReportAdapter({**recap_doc, **engine_payload})
        execution_plan_rows = await self._fetch_execution_plan_rows(gateway, trade_date)

        return {
            "ready": adapter.has_engine_data,
            "trade_date": trade_date.isoformat(),
            "source_trade_date": window.prev_trade_date.isoformat(),
            "window_source": window.source,
            "allow_trade": adapter.premkt_trading_permission().get("allow_trade", False),
            "trade_mode": adapter.premkt_trading_permission().get("trade_mode", "no_trade"),
            "position_limit": adapter.premkt_trading_permission().get("position_limit", 0),
            "no_trade_blocking_rule": adapter.premkt_trading_permission().get("no_trade_blocking_rule"),
            "next_day_strategy": adapter.premkt_trading_permission().get("next_day_strategy", ""),
            "engine_summary": adapter.notion_trade_conclusion(),
            "market_regime_review": engine_payload.get("market_regime_review")
            or legacy_payload.get("market_regime_review")
            or {},
            "mainline_daily_states": adapter.notion_mainline_states(),
            "post_market_decision_v2": engine_payload.get("post_market_decision_v2")
            or legacy_payload.get("post_market_decision_v2")
            or {},
            "observation_list": adapter.premkt_observation_list(),
            "d2_pending_list": adapter.premkt_d2_pending_list(),
            "risk_notes": adapter.premkt_risk_notes(),
            "execution_plan_rows": execution_plan_rows,
            "diagnostics": {
                **adapter.diagnostics(),
                "prev_snapshot_found": bool(prev_row),
                "execution_plan_count": len(execution_plan_rows),
                "window_source": window.source,
            },
        }

    @staticmethod
    def _normalize_payload(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("payload", "doc"):
            value = row.get(key)
            if isinstance(value, dict) and value:
                return value
        recap_doc = row.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            return {"recap_doc": recap_doc}
        return {}

    @staticmethod
    def _extract_recap_doc(payload: dict[str, Any]) -> dict[str, Any]:
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            return recap_doc
        if payload.get("engine_summary") or payload.get("post_market_decision_v2"):
            return payload
        return {}

    @staticmethod
    def _compose_engine_payload(recap_doc: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(recap_doc, dict) or not recap_doc:
            return {}
        try:
            composer = PostMarketEngineReportComposer()
            return composer.compose(recap_doc)
        except Exception:
            return {}

    @staticmethod
    async def _fetch_execution_plan_rows(gateway: Any, trade_date: date) -> list[dict[str, Any]]:
        fetcher = getattr(gateway, "fetch_pre_market_execution_plans", None)
        if not callable(fetcher):
            return []
        try:
            rows = await fetcher(trade_date.isoformat(), limit=20, include_avoid=False)
            return [dict(row) for row in rows or []]
        except Exception:
            return []
