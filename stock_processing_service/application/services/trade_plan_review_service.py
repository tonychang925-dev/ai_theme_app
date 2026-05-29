from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from stock_processing_service.application.services.trade_plan_review_context_builder import (
    TradePlanReviewContextBuilder,
)
from stock_processing_service.application.services.trade_plan_review_rule_engine import (
    TradePlanReviewRuleEngine,
)
from stock_processing_service.integrations.notion.notion_trade_plan_repository import (
    NotionTradePlanRepository,
)


class TradePlanReviewService:
    def __init__(
        self,
        *,
        repository: NotionTradePlanRepository,
        gateway: Any,
        context_builder: TradePlanReviewContextBuilder | None = None,
        rule_engine: TradePlanReviewRuleEngine | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._context_builder = context_builder or TradePlanReviewContextBuilder()
        self._rule_engine = rule_engine or TradePlanReviewRuleEngine()

    async def review(self, *, trade_date: date, plan_date: date, dry_run: bool = True) -> dict[str, Any]:
        plan = self._repository.get_plan_by_dates(
            trade_date=trade_date.isoformat(),
            plan_date=plan_date.isoformat(),
        )
        if plan is None:
            return {
                "ok": False,
                "error_code": "TRADE_PLAN_NOT_FOUND",
                "message": "Notion trade plan page not found",
                "trade_date": trade_date.isoformat(),
                "plan_date": plan_date.isoformat(),
            }

        context = await self._context_builder.build(gateway=self._gateway, trade_date=trade_date)
        if context is None:
            return {
                "ok": False,
                "error_code": "POST_MARKET_RECAP_SNAPSHOT_MISSING",
                "message": "post_market_recap_snapshot not found",
                "trade_date": trade_date.isoformat(),
                "plan_date": plan_date.isoformat(),
                "page_id": plan.page_id,
            }

        review_doc = self._rule_engine.evaluate(plan_text=plan.text, context=context)
        return {
            "ok": True,
            "trade_date": trade_date.isoformat(),
            "plan_date": plan_date.isoformat(),
            "page_id": plan.page_id,
            "page_url": plan.page_url,
            "review_id": plan.review_id or f"trade_plan_review:{trade_date.isoformat()}:{plan_date.isoformat()}",
            "latest_review_version": plan.latest_review_version,
            "review_status": review_doc["review_status"],
            "risk_level": review_doc["risk_level"],
            "review_score": review_doc["review_score"],
            "summary": review_doc["summary"],
            "notion_updated": False,
            "dry_run": dry_run,
            "trade_plan": asdict(plan),
            "context": {
                "snapshot_version": context.get("snapshot_version"),
                "summary": context.get("summary"),
                "theme_terms": context.get("theme_terms"),
            },
            "review_doc": review_doc,
        }
