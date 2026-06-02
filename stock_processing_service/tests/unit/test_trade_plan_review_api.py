from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from stock_processing_service import api_app
from stock_processing_service.integrations.notion.notion_trade_plan_repository import NotionTradePlanPage


class _Repository:
    def __init__(self, page: NotionTradePlanPage | None) -> None:
        self.page = page

    def get_plan_by_dates(self, *, trade_date: str, plan_date: str):
        return self.page


class _Gateway:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return self.row


def _page() -> NotionTradePlanPage:
    return NotionTradePlanPage(
        page_id="page-1",
        page_url="https://notion.so/page-1",
        trade_date="2026-05-29",
        plan_date="2026-06-01",
        title="计划",
        report_id="trade_plan:2026-05-29:2026-06-01",
        review_id="trade_plan_review:2026-05-29:2026-06-01",
        latest_review_version=0,
        text="仓位上限：三成\n止损 / 止盈条件：跌破支撑止损\n不买条件：高开过多放弃\n今日主线：机器人",
    )


def _snapshot() -> dict:
    return {
        "trade_date": date(2026, 5, 29),
        "snapshot_version": "unit",
        "payload": {"recap_doc": {"top_candidates": [{"subject_name": "机器人"}]}},
    }


@pytest.mark.asyncio
async def test_review_trade_plan_api_dry_run_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=_Gateway(_snapshot())), raising=False)
    monkeypatch.setattr(
        api_app.NotionTradePlanRepository,
        "from_env",
        classmethod(lambda cls: _Repository(_page())),
    )

    result = await api_app.review_trade_plan(
        api_app.TradePlanReviewPayload(trade_date="2026-05-29", plan_date="2026-06-01", dry_run=True)
    )

    assert result["ok"] is True
    assert result["review_status"] == "通过"
    assert result["notion_updated"] is False


@pytest.mark.asyncio
async def test_review_trade_plan_api_missing_plan_maps_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=_Gateway(_snapshot())), raising=False)
    monkeypatch.setattr(
        api_app.NotionTradePlanRepository,
        "from_env",
        classmethod(lambda cls: _Repository(None)),
    )

    with pytest.raises(HTTPException) as exc:
        await api_app.review_trade_plan(
            api_app.TradePlanReviewPayload(trade_date="2026-05-29", plan_date="2026-06-01")
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_review_trade_plan_api_missing_snapshot_maps_424(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app.app, "state", SimpleNamespace(gateway=_Gateway(None)), raising=False)
    monkeypatch.setattr(
        api_app.NotionTradePlanRepository,
        "from_env",
        classmethod(lambda cls: _Repository(_page())),
    )

    with pytest.raises(HTTPException) as exc:
        await api_app.review_trade_plan(
            api_app.TradePlanReviewPayload(trade_date="2026-05-29", plan_date="2026-06-01")
        )

    assert exc.value.status_code == 424
