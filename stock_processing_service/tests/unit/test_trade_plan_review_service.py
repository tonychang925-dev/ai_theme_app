from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.trade_plan_review_service import TradePlanReviewService
from stock_processing_service.integrations.notion.notion_trade_plan_repository import NotionTradePlanPage


class _Repository:
    def __init__(self, page: NotionTradePlanPage | None) -> None:
        self.page = page
        self.calls: list[tuple[str, str]] = []

    def get_plan_by_dates(self, *, trade_date: str, plan_date: str):
        self.calls.append((trade_date, plan_date))
        return self.page


class _Gateway:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return self.row


def _page(text: str) -> NotionTradePlanPage:
    return NotionTradePlanPage(
        page_id="page-1",
        page_url="https://notion.so/page-1",
        trade_date="2026-05-29",
        plan_date="2026-06-01",
        title="2026-05-29 交易总结与 2026-06-01 交易计划",
        report_id="trade_plan:2026-05-29:2026-06-01",
        review_id="trade_plan_review:2026-05-29:2026-06-01",
        latest_review_version=0,
        text=text,
    )


@pytest.mark.asyncio
async def test_trade_plan_review_dry_run_returns_review_doc() -> None:
    plan_text = """
一、今日市场理解
- 今日主线：机器人
四、明日交易计划
- 买入条件：机器人题材竞价强于大盘
- 不买条件：高开过多放弃
- 仓位上限：三成以内
三、持仓复盘
- 止损 / 止盈条件：跌破关键支撑止损
"""
    gateway = _Gateway(
        {
            "trade_date": date(2026, 5, 29),
            "snapshot_version": "unit",
            "payload": {
                "recap_doc": {
                    "candidate_count": 2,
                    "strong_watch_input_count": 10,
                    "top_candidates": [{"subject_name": "机器人"}],
                }
            },
        }
    )
    service = TradePlanReviewService(repository=_Repository(_page(plan_text)), gateway=gateway)

    result = await service.review(trade_date=date(2026, 5, 29), plan_date=date(2026, 6, 1), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["notion_updated"] is False
    assert result["review_status"] == "通过"
    assert result["risk_level"] == "低"
    assert result["review_doc"]["review_score"] == 100
    assert result["context"]["theme_terms"] == ["机器人"]


@pytest.mark.asyncio
async def test_trade_plan_review_template_labels_without_content_require_fix() -> None:
    plan_text = """
三、持仓复盘
- 止损 / 止盈条件：
四、明日交易计划
- 不买条件：
- 仓位上限：
"""
    gateway = _Gateway(
        {
            "trade_date": date(2026, 5, 29),
            "snapshot_version": "unit",
            "payload": {"recap_doc": {"top_candidates": [{"subject_name": "机器人"}]}},
        }
    )
    service = TradePlanReviewService(repository=_Repository(_page(plan_text)), gateway=gateway)

    result = await service.review(trade_date=date(2026, 5, 29), plan_date=date(2026, 6, 1), dry_run=True)

    assert result["ok"] is True
    assert result["review_status"] == "不建议执行"
    assert "缺少明确仓位上限" in result["review_doc"]["must_fix"]
    assert "缺少明确止损或止盈条件" in result["review_doc"]["must_fix"]
    assert "缺少必须放弃或不买条件" in result["review_doc"]["must_fix"]


@pytest.mark.asyncio
async def test_trade_plan_review_missing_plan_returns_not_found() -> None:
    service = TradePlanReviewService(repository=_Repository(None), gateway=_Gateway({}))

    result = await service.review(trade_date=date(2026, 5, 29), plan_date=date(2026, 6, 1), dry_run=True)

    assert result["ok"] is False
    assert result["error_code"] == "TRADE_PLAN_NOT_FOUND"


@pytest.mark.asyncio
async def test_trade_plan_review_missing_snapshot_returns_424_payload() -> None:
    service = TradePlanReviewService(
        repository=_Repository(_page("仓位上限：三成")),
        gateway=_Gateway(None),
    )

    result = await service.review(trade_date=date(2026, 5, 29), plan_date=date(2026, 6, 1), dry_run=True)

    assert result["ok"] is False
    assert result["error_code"] == "POST_MARKET_RECAP_SNAPSHOT_MISSING"
    assert result["page_id"] == "page-1"
