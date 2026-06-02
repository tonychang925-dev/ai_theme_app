from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from stock_processing_service.integrations.notion.notion_client_adapter import NotionClientAdapter
from stock_processing_service.integrations.notion.notion_page_reader import NotionPageReader


@dataclass(frozen=True)
class NotionTradePlanPage:
    page_id: str
    page_url: str
    trade_date: str
    plan_date: str
    title: str
    report_id: str
    review_id: str
    latest_review_version: int
    text: str


class NotionTradePlanRepository:
    def __init__(
        self,
        *,
        database_id: str,
        client: NotionClientAdapter,
        title_property: str = "标题",
        trade_date_property: str = "交易日期",
        plan_date_property: str = "计划日期",
        report_id_property: str = "report_id",
        review_id_property: str = "review_id",
        latest_review_version_property: str = "latest_review_version",
    ) -> None:
        if not database_id:
            raise ValueError("missing NOTION_TRADING_PLANS_DATABASE_ID")
        self._database_id = database_id
        self._client = client
        self._reader = NotionPageReader(client)
        self._title_prop = title_property
        self._trade_date_prop = trade_date_property
        self._plan_date_prop = plan_date_property
        self._report_id_prop = report_id_property
        self._review_id_prop = review_id_property
        self._latest_review_version_prop = latest_review_version_property

    @classmethod
    def from_env(cls, client: NotionClientAdapter | None = None) -> "NotionTradePlanRepository":
        return cls(
            database_id=os.getenv("NOTION_TRADING_PLANS_DATABASE_ID", "").strip(),
            client=client or NotionClientAdapter.from_env(),
            title_property=os.getenv("NOTION_TRADE_PLAN_PROP_TITLE", "标题").strip() or "标题",
            trade_date_property=os.getenv("NOTION_TRADE_PLAN_PROP_TRADE_DATE", "交易日期").strip() or "交易日期",
            plan_date_property=os.getenv("NOTION_TRADE_PLAN_PROP_PLAN_DATE", "计划日期").strip() or "计划日期",
            report_id_property=os.getenv("NOTION_TRADE_PLAN_PROP_REPORT_ID", "report_id").strip() or "report_id",
            review_id_property=os.getenv("NOTION_TRADE_PLAN_PROP_REVIEW_ID", "review_id").strip() or "review_id",
            latest_review_version_property=(
                os.getenv("NOTION_TRADE_PLAN_PROP_LATEST_REVIEW_VERSION", "latest_review_version").strip()
                or "latest_review_version"
            ),
        )

    def get_plan_by_dates(self, *, trade_date: str, plan_date: str) -> NotionTradePlanPage | None:
        body = {
            "filter": {
                "and": [
                    {"property": self._trade_date_prop, "date": {"equals": trade_date}},
                    {"property": self._plan_date_prop, "date": {"equals": plan_date}},
                ]
            },
            "sorts": [{"property": self._trade_date_prop, "direction": "descending"}],
            "page_size": 2,
        }
        resp = self._client.query_database(self._database_id, body)
        results = resp.get("results") or []
        if not results:
            return None
        return self._to_trade_plan_page(results[0], trade_date=trade_date, plan_date=plan_date)

    def _to_trade_plan_page(self, page: dict[str, Any], *, trade_date: str, plan_date: str) -> NotionTradePlanPage:
        properties = page.get("properties") if isinstance(page.get("properties"), dict) else {}
        page_id = str(page.get("id") or "")
        return NotionTradePlanPage(
            page_id=page_id,
            page_url=str(page.get("url") or ""),
            trade_date=trade_date,
            plan_date=plan_date,
            title=self._title(properties.get(self._title_prop)),
            report_id=self._rich_text(properties.get(self._report_id_prop)),
            review_id=self._rich_text(properties.get(self._review_id_prop)),
            latest_review_version=self._number(properties.get(self._latest_review_version_prop)),
            text=self._reader.read_page_as_text(page_id),
        )

    @staticmethod
    def _title(prop: dict[str, Any] | None) -> str:
        items = (prop or {}).get("title") or []
        return "".join(str(item.get("plain_text") or item.get("text", {}).get("content") or "") for item in items).strip()

    @staticmethod
    def _rich_text(prop: dict[str, Any] | None) -> str:
        items = (prop or {}).get("rich_text") or []
        return "".join(str(item.get("plain_text") or item.get("text", {}).get("content") or "") for item in items).strip()

    @staticmethod
    def _number(prop: dict[str, Any] | None) -> int:
        value = (prop or {}).get("number")
        try:
            return int(value or 0)
        except Exception:
            return 0
