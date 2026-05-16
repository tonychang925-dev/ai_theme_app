from __future__ import annotations

from typing import Any


class NotionBlockBuilder:
    """共享 Notion block 构建工具，内置截断和分批。

    Notion API 约束:
    - rich_text text.content 上限 2000 字符
    - 单次 append children 最多 100 个 block
    """

    RICH_TEXT_LIMIT = 2000
    APPEND_CHUNK_SIZE = 100

    @staticmethod
    def _truncate(text: str, limit: int | None = None) -> str:
        limit = limit or NotionBlockBuilder.RICH_TEXT_LIMIT
        value = str(text or "")
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    @staticmethod
    def _rich_text(text: str, limit: int | None = None) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": {"content": NotionBlockBuilder._truncate(text, limit=limit)},
            }
        ]

    @classmethod
    def heading_1(cls, text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": cls._rich_text(text, limit=120)},
        }

    @classmethod
    def heading_2(cls, text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": cls._rich_text(text, limit=120)},
        }

    @classmethod
    def heading_3(cls, text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": cls._rich_text(text, limit=120)},
        }

    @classmethod
    def paragraph(cls, text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": cls._rich_text(text)},
        }

    @classmethod
    def callout(cls, text: str, icon: str = "📌", color: str = "default") -> dict[str, Any]:
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": cls._rich_text(text),
                "icon": {"type": "emoji", "emoji": icon},
                "color": color,
            },
        }

    @classmethod
    def bullet(cls, text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": cls._rich_text(text)},
        }

    @classmethod
    def divider(cls) -> dict[str, Any]:
        return {"object": "block", "type": "divider", "divider": {}}

    @classmethod
    def table(
        cls,
        headers: list[str],
        rows: list[list[str]],
        *,
        header_limit: int = 80,
        cell_limit: int = 400,
    ) -> list[dict[str, Any]]:
        """构造 Notion table block + table_rows。

        返回以 table block 开头，后接 table_row 的 block 列表。
        Notion 要求 table_width 与每行 cells 数量一致。
        """
        if not headers:
            headers = ["--"]
        table_width = len(headers)

        # table block
        blocks: list[dict[str, Any]] = [
            {
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": table_width,
                    "has_column_header": True,
                    "has_row_header": False,
                },
            }
        ]

        # header row
        blocks.append(cls._table_row(headers, limit=header_limit))

        # data rows
        for row in rows:
            # pad or truncate to match table_width
            cells = list(row)
            while len(cells) < table_width:
                cells.append("--")
            cells = cells[:table_width]
            blocks.append(cls._table_row(cells, limit=cell_limit))

        return blocks

    @classmethod
    def _table_row(cls, cells: list[str], limit: int = 400) -> dict[str, Any]:
        """构造单个 Notion table_row block。"""
        return {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [[{"type": "text", "text": {"content": cls._truncate(str(c or "--"), limit=limit)}}] for c in cells]
            },
        }

    @classmethod
    def toggle(cls, title: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": cls._rich_text(title, limit=120),
                "children": children,
            },
        }

    @classmethod
    def empty_paragraph(cls, text: str = "暂无数据") -> dict[str, Any]:
        return cls.paragraph(text)

    @classmethod
    def chunk_blocks(cls, blocks: list[dict[str, Any]], size: int | None = None) -> list[list[dict[str, Any]]]:
        size = size or cls.APPEND_CHUNK_SIZE
        return [blocks[i : i + size] for i in range(0, len(blocks), size)]

    @classmethod
    def summary_stat_line(cls, label: str, value: int | str) -> str:
        return f"{label}：{value}"
