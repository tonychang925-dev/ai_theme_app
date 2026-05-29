from __future__ import annotations

from typing import Any

from stock_processing_service.integrations.notion.notion_client_adapter import NotionClientAdapter


RICH_TEXT_BLOCK_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "callout",
    "quote",
}


class NotionPageReader:
    def __init__(self, client: NotionClientAdapter) -> None:
        self._client = client

    def read_page_as_text(self, page_id: str) -> str:
        lines = self._read_children_lines(page_id, depth=0)
        return "\n".join(line for line in lines if line.strip()).strip()

    def _read_children_lines(self, block_id: str, *, depth: int) -> list[str]:
        lines: list[str] = []
        cursor: str | None = None
        while True:
            data = self._client.retrieve_block_children(block_id, start_cursor=cursor)
            for block in data.get("results") or []:
                lines.extend(self._block_to_lines(block, depth=depth))
                if block.get("has_children"):
                    lines.extend(self._read_children_lines(str(block.get("id") or ""), depth=depth + 1))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return lines

    def _block_to_lines(self, block: dict[str, Any], *, depth: int) -> list[str]:
        block_type = str(block.get("type") or "")
        if block_type in RICH_TEXT_BLOCK_TYPES:
            text = self._plain_text(block.get(block_type, {}).get("rich_text") or [])
            if not text:
                return []
            prefix = "  " * depth
            if block_type in {"bulleted_list_item", "to_do"}:
                return [f"{prefix}- {text}"]
            if block_type == "numbered_list_item":
                return [f"{prefix}1. {text}"]
            return [f"{prefix}{text}"]
        if block_type == "divider":
            return []
        return [f"{'  ' * depth}[unsupported block: {block_type}]"]

    @staticmethod
    def _plain_text(rich_text: list[dict[str, Any]]) -> str:
        return "".join(str(item.get("plain_text") or item.get("text", {}).get("content") or "") for item in rich_text).strip()

