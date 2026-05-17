#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def normalize_notion_id(value: str) -> str:
    """
    支持用户粘贴：
    - 纯 id
    - 带横杠 id
    - Notion 页面 URL
    """
    text = (value or "").strip()
    if not text:
        return ""

    # 如果是 URL，取 ? 前最后一段
    if "notion.so" in text:
        text = text.split("?")[0].rstrip("/").split("/")[-1]

    # 页面标题后面常拼接 32 位 id，例如 AI-Reports-3047...
    raw = text.replace("-", "")
    if len(raw) >= 32:
        raw = raw[-32:]

    if len(raw) != 32:
        return text

    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_reports_database(
    *,
    token: str,
    parent_page_id: str,
    database_title: str,
    is_inline: bool = False,
) -> dict[str, Any]:
    url = f"{NOTION_API_BASE}/databases"

    payload = {
        "parent": {
            "type": "page_id",
            "page_id": parent_page_id,
        },
        "title": [
            {
                "type": "text",
                "text": {
                    "content": database_title,
                },
            }
        ],
        "is_inline": is_inline,
        "icon": {
            "type": "emoji",
            "emoji": "\U0001f4ca",
        },
        "properties": {
            "\u6807\u9898": {
                "title": {},
            },
            "\u4ea4\u6613\u65e5\u671f": {
                "date": {},
            },
            "\u62a5\u544a\u7c7b\u578b": {
                "select": {
                    "options": [
                        {"name": "post_market_recap", "color": "blue"},
                        {"name": "pre_market_brief", "color": "green"},
                    ]
                }
            },
            "report_id": {
                "rich_text": {},
            },
            "snapshot_version": {
                "rich_text": {},
            },
            "\u6458\u8981": {
                "rich_text": {},
            },
            "\u72b6\u6001": {
                "select": {
                    "options": [
                        {"name": "\u5df2\u53d1\u5e03", "color": "green"},
                        {"name": "\u8349\u7a3f", "color": "yellow"},
                        {"name": "\u5931\u8d25", "color": "red"},
                    ]
                }
            },
        },
    }

    resp = requests.post(url, headers=notion_headers(token), json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Notion create database failed: status={resp.status_code}, body={resp.text}"
        )
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Notion reports database for ai_theme_app.")
    parser.add_argument(
        "--parent-page-id",
        default=os.getenv("NOTION_PARENT_PAGE_ID", ""),
        help="Parent Notion page id or page URL. Env: NOTION_PARENT_PAGE_ID",
    )
    parser.add_argument(
        "--title",
        default=os.getenv("NOTION_REPORTS_DATABASE_TITLE", "reports"),
        help="Database title. Default: reports",
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Create database inline under parent page.",
    )
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token:
        print("[ERROR] missing NOTION_TOKEN", file=sys.stderr)
        return 2

    parent_page_id = normalize_notion_id(args.parent_page_id)
    if not parent_page_id:
        print("[ERROR] missing NOTION_PARENT_PAGE_ID or --parent-page-id", file=sys.stderr)
        return 2

    print(f"[INFO] parent_page_id={parent_page_id}")
    print(f"[INFO] database_title={args.title}")

    db = create_reports_database(
        token=token,
        parent_page_id=parent_page_id,
        database_title=args.title,
        is_inline=bool(args.inline),
    )

    database_id = db.get("id", "")
    url = db.get("url", "")

    print("\n[OK] Notion reports database created")
    print(f"NOTION_DATABASE_ID={database_id}")
    print(f"NOTION_DATABASE_URL={url}")

    print("\nAdd these to your SPS environment:")
    print(f"export NOTION_DATABASE_ID='{database_id}'")
    print("export NOTION_PROP_TITLE='标题'")
    print("export NOTION_PROP_TRADE_DATE='交易日期'")
    print("export NOTION_PROP_REPORT_TYPE='报告类型'")
    print("export NOTION_PROP_REPORT_ID='report_id'")
    print("export NOTION_PROP_SNAPSHOT_VERSION='snapshot_version'")
    print("export NOTION_PROP_SUMMARY='摘要'")
    print("export NOTION_PROP_STATUS='状态'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
