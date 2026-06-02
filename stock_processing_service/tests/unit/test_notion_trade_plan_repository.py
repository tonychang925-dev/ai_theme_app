from __future__ import annotations

from stock_processing_service.integrations.notion.notion_trade_plan_repository import (
    NotionTradePlanRepository,
)


class _Client:
    def __init__(self) -> None:
        self.query_body = None

    def query_database(self, database_id, body):
        self.query_body = body
        return {
            "results": [
                {
                    "id": "page-1",
                    "url": "https://notion.so/page-1",
                    "properties": {
                        "标题": {
                            "title": [{"plain_text": "标题"}],
                        },
                        "report_id": {
                            "rich_text": [{"plain_text": "trade_plan:2026-05-29:2026-06-01"}],
                        },
                        "review_id": {
                            "rich_text": [{"plain_text": "trade_plan_review:2026-05-29:2026-06-01"}],
                        },
                        "latest_review_version": {
                            "number": 2,
                        },
                    },
                }
            ]
        }

    def retrieve_block_children(self, block_id, *, start_cursor=None):
        return {
            "results": [
                {
                    "id": "block-1",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"plain_text": "一、今日交易总结"}]},
                    "has_children": False,
                },
                {
                    "id": "block-2",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"plain_text": "仓位上限：三成"}]},
                    "has_children": False,
                },
            ],
            "has_more": False,
        }


def test_notion_trade_plan_repository_queries_by_dates_and_reads_text() -> None:
    client = _Client()
    repo = NotionTradePlanRepository(database_id="db-1", client=client)

    page = repo.get_plan_by_dates(trade_date="2026-05-29", plan_date="2026-06-01")

    assert page is not None
    assert page.page_id == "page-1"
    assert page.latest_review_version == 2
    assert "仓位上限：三成" in page.text
    assert client.query_body["filter"]["and"][0]["date"]["equals"] == "2026-05-29"
    assert client.query_body["filter"]["and"][1]["date"]["equals"] == "2026-06-01"
