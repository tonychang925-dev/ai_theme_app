from __future__ import annotations

from stock_service.models import MarketReport
from stock_service.publishers.notion_report_publisher import NotionReportPublisher


class _FakeChildren:
    def __init__(self):
        self.calls = []

    def append(self, *, block_id, children):
        self.calls.append({"block_id": block_id, "children": children})


class _FakeBlocks:
    def __init__(self):
        self.children = _FakeChildren()


class _FakeClient:
    def __init__(self):
        self.blocks = _FakeBlocks()


def _report() -> MarketReport:
    return MarketReport(
        report_type="pre_market",
        trade_date="2026-04-01",
        title="2026-04-01 盘前必读",
        summary="基于题材与股票快照生成。",
        highlights=["亮点1"],
        sections=[
            ("隔夜/当日重点题材事件", ["09:30 创新药：驱动事件"]),
            ("关注题材与龙头", ["创新药：龙头 广生堂，涨停 3 家"]),
        ],
    )


def test_build_blocks_contains_heading_and_section_items():
    blocks = NotionReportPublisher.build_blocks(_report())

    assert blocks[0]["type"] == "heading_2"
    assert blocks[1]["type"] == "paragraph"
    assert any(item["type"] == "heading_3" for item in blocks)
    assert any(item["type"] == "bulleted_list_item" for item in blocks)


def test_publish_report_uses_client_append():
    client = _FakeClient()
    publisher = NotionReportPublisher(token="", page_id="page123", client=client)

    publisher.publish_report(_report())

    assert len(client.blocks.children.calls) == 1
    call = client.blocks.children.calls[0]
    assert call["block_id"] == "page123"
    assert len(call["children"]) >= 4
