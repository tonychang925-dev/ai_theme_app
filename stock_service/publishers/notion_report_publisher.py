from __future__ import annotations

from stock_service.models import MarketReport


class NotionReportPublisher:
    def __init__(self, token: str, page_id: str, client=None):
        if not token and client is None:
            raise ValueError("missing NOTION_TOKEN")
        if not page_id:
            raise ValueError("missing NOTION_REPORT_PAGE_ID")
        if client is None:
            from notion_client import Client

            client = Client(auth=token)
        self.client = client
        self.page_id = page_id

    @staticmethod
    def build_blocks(report: MarketReport) -> list[dict]:
        blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": report.title}}],
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": report.summary}}],
                },
            },
        ]
        for heading, items in report.sections:
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": heading}}],
                    },
                }
            )
            for item in items[:20]:
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": item[:1800]}}],
                        },
                    }
                )
        return blocks

    def publish_report(self, report: MarketReport) -> None:
        blocks = self.build_blocks(report)
        self.client.blocks.children.append(block_id=self.page_id, children=blocks)
