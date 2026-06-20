from __future__ import annotations

from stock_processing_service.publishers.notion_post_market_recap_publisher import (
    NotionPostMarketRecapPublisher,
)


def _heading_text(block: dict[str, object]) -> str | None:
    if block.get("type") != "heading_2":
        return None
    payload = block.get("heading_2")
    if not isinstance(payload, dict):
        return None
    rich_text = payload.get("rich_text")
    if not isinstance(rich_text, list) or not rich_text:
        return None
    first = rich_text[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    if not isinstance(text, dict):
        return None
    content = text.get("content")
    return str(content) if content is not None else None


def test_notion_post_market_recap_publisher_places_daily_recap_story_first() -> None:
    payload = {"recap_doc": {}}
    blocks = NotionPostMarketRecapPublisher.build_blocks(payload, "2026-06-17")

    headings = [text for block in blocks if (text := _heading_text(block))]
    expected = [
        "今日复盘要点",
        "涨停热点总览",
        "股价新高与行业趋势",
        "机构席位和游资动向",
        "次日观察与交易建议",
    ]

    start = headings.index("今日复盘要点")
    assert headings[start : start + len(expected)] == expected
    assert headings.index("一、复盘概览") > headings.index("次日观察与交易建议")
