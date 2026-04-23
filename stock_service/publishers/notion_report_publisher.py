from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from stock_service.models import MarketReport


@dataclass(frozen=True)
class NotionPublishResult:
    page_id: str
    page_url: str
    action: str
    report_id: str


class NotionReportPublisher:
    """
    将每日 MarketReport 发布到 Notion 数据库中，每个交易日一页。

    关键特性：
    - 使用 database_id，而不是固定 page_id
    - 使用 report_id=report_type:trade_date 做幂等
    - 默认 archive_and_recreate，避免重复 append
    - 适配 Notion Calendar 视图：要求数据库有日期字段
    """

    def __init__(
        self,
        token: str,
        database_id: str,
        client=None,
        *,
        title_property: str = "标题",
        trade_date_property: str = "复盘日期",
        report_type_property: str = "报告类型",
        report_id_property: str = "report_id",
        summary_property: str = "摘要",
        status_property: str = "状态",
        overwrite_mode: str = "archive_and_recreate",
        page_size: int = 10,
    ):
        if not token and client is None:
            raise ValueError("missing NOTION_TOKEN")
        if not database_id:
            raise ValueError("missing NOTION_DATABASE_ID")

        if client is None:
            from notion_client import Client
            client = Client(auth=token)

        self.client = client
        self.database_id = database_id
        self.title_property = title_property
        self.trade_date_property = trade_date_property
        self.report_type_property = report_type_property
        self.report_id_property = report_id_property
        self.summary_property = summary_property
        self.status_property = status_property
        self.overwrite_mode = overwrite_mode
        self.page_size = max(int(page_size), 1)

    @classmethod
    def from_env(cls, client=None) -> "NotionReportPublisher":
        return cls(
            token=os.getenv("NOTION_TOKEN", "").strip(),
            database_id=os.getenv("NOTION_DATABASE_ID", "").strip(),
            client=client,
            title_property=os.getenv("NOTION_PROP_TITLE", "标题").strip() or "标题",
            trade_date_property=os.getenv("NOTION_PROP_TRADE_DATE", "复盘日期").strip() or "复盘日期",
            report_type_property=os.getenv("NOTION_PROP_REPORT_TYPE", "报告类型").strip() or "报告类型",
            report_id_property=os.getenv("NOTION_PROP_REPORT_ID", "report_id").strip() or "report_id",
            summary_property=os.getenv("NOTION_PROP_SUMMARY", "摘要").strip() or "摘要",
            status_property=os.getenv("NOTION_PROP_STATUS", "状态").strip() or "状态",
        )

    @staticmethod
    def _truncate_text(text: str, limit: int = 1800) -> str:
        return (text or "")[:limit]

    @staticmethod
    def _rich_text(text: str) -> list[dict]:
        return [{"type": "text", "text": {"content": NotionReportPublisher._truncate_text(text)}}]

    @staticmethod
    def _chunk_blocks(blocks: list[dict], size: int = 100) -> list[list[dict]]:
        return [blocks[i:i + size] for i in range(0, len(blocks), size)]

    @staticmethod
    def build_blocks(report: MarketReport) -> list[dict]:
        blocks: list[dict] = []

        blocks.append(
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": NotionReportPublisher._rich_text(report.title),
                },
            }
        )

        if report.summary:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": NotionReportPublisher._rich_text(report.summary),
                    },
                }
            )

        highlights = list(getattr(report, "highlights", []) or [])
        if highlights:
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": NotionReportPublisher._rich_text("核心要点"),
                    },
                }
            )
            for item in highlights:
                text = str(item or "").strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": NotionReportPublisher._rich_text(text),
                        },
                    }
                )

        for heading, items in report.sections:
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": NotionReportPublisher._rich_text(heading),
                    },
                }
            )
            for item in items:
                text = str(item or "").strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": NotionReportPublisher._rich_text(text),
                        },
                    }
                )
        return blocks

    def _report_id(self, report: MarketReport) -> str:
        return f"{report.report_type}:{report.trade_date}"

    def _query_existing_page(self, report_id: str) -> Optional[dict]:
        payload = {
            "filter": {
                "property": self.report_id_property,
                "rich_text": {"equals": report_id},
            },
            "page_size": self.page_size,
        }
        resp = self.client.databases.query(database_id=self.database_id, **payload)
        results = resp.get("results") or []
        return results[0] if results else None

    def _archive_page(self, page_id: str) -> None:
        self.client.pages.update(page_id=page_id, archived=True)

    def _create_page(self, report: MarketReport, report_id: str) -> dict:
        properties = {
            self.title_property: {
                "title": self._rich_text(report.title),
            },
            self.trade_date_property: {
                "date": {"start": report.trade_date},
            },
            self.report_type_property: {
                "select": {"name": report.report_type},
            },
            self.report_id_property: {
                "rich_text": self._rich_text(report_id),
            },
            self.summary_property: {
                "rich_text": self._rich_text(report.summary or "--"),
            },
            self.status_property: {
                "select": {"name": "已发布"},
            },
        }
        return self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
        )

    def _append_children(self, page_id: str, blocks: list[dict]) -> None:
        for chunk in self._chunk_blocks(blocks, size=100):
            self.client.blocks.children.append(block_id=page_id, children=chunk)

    def publish_report(self, report: MarketReport) -> NotionPublishResult:
        report_id = self._report_id(report)
        existing = self._query_existing_page(report_id)

        action = "created"
        if existing:
            if self.overwrite_mode == "archive_and_recreate":
                self._archive_page(existing["id"])
                action = "recreated"
            else:
                return NotionPublishResult(
                    page_id=existing["id"],
                    page_url=existing.get("url", ""),
                    action="exists",
                    report_id=report_id,
                )

        page = self._create_page(report, report_id)
        blocks = self.build_blocks(report)
        self._append_children(page["id"], blocks)

        return NotionPublishResult(
            page_id=page["id"],
            page_url=page.get("url", ""),
            action=action,
            report_id=report_id,
        )
