#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def normalize_notion_id(value: str) -> str:
    """
    Accepts:
    - plain page id
    - dashed page id
    - Notion page URL
    """
    text = (value or "").strip()
    if not text:
        return ""

    if "notion.so" in text:
        text = text.split("?")[0].rstrip("/").split("/")[-1]

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


def build_trading_plans_database_payload(
    *,
    parent_page_id: str,
    database_title: str,
    is_inline: bool = False,
) -> dict[str, Any]:
    return {
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
            "emoji": "\U0001f4dd",
        },
        "properties": {
            "\u6807\u9898": {
                "title": {},
            },
            "\u4ea4\u6613\u65e5\u671f": {
                "date": {},
            },
            "\u8ba1\u5212\u65e5\u671f": {
                "date": {},
            },
            "\u8ba1\u5212\u72b6\u6001": {
                "select": {
                    "options": [
                        {"name": "\u8349\u7a3f", "color": "default"},
                        {"name": "\u5f85\u5ba1\u6838", "color": "yellow"},
                        {"name": "\u5df2\u5ba1\u6838", "color": "green"},
                        {"name": "\u5df2\u6267\u884c", "color": "blue"},
                        {"name": "\u5df2\u590d\u76d8", "color": "purple"},
                    ]
                }
            },
            "\u5ba1\u6838\u72b6\u6001": {
                "select": {
                    "options": [
                        {"name": "\u672a\u5ba1\u6838", "color": "default"},
                        {"name": "\u901a\u8fc7", "color": "green"},
                        {"name": "\u6709\u6761\u4ef6\u901a\u8fc7", "color": "yellow"},
                        {"name": "\u4e0d\u5efa\u8bae\u6267\u884c", "color": "orange"},
                        {"name": "\u9ad8\u98ce\u9669", "color": "red"},
                    ]
                }
            },
            "\u5ba1\u6838\u5206": {
                "number": {
                    "format": "number",
                }
            },
            "\u98ce\u9669\u7b49\u7ea7": {
                "select": {
                    "options": [
                        {"name": "\u4f4e", "color": "green"},
                        {"name": "\u4e2d", "color": "yellow"},
                        {"name": "\u9ad8", "color": "orange"},
                        {"name": "\u6781\u9ad8", "color": "red"},
                    ]
                }
            },
            "\u662f\u5426\u89e6\u53d1\u5ba1\u6838": {
                "checkbox": {},
            },
            "reviewed_at": {
                "date": {},
            },
            "report_id": {
                "rich_text": {},
            },
            "review_id": {
                "rich_text": {},
            },
            "latest_review_version": {
                "number": {
                    "format": "number",
                }
            },
        },
    }


def create_trading_plans_database(
    *,
    token: str,
    parent_page_id: str,
    database_title: str,
    is_inline: bool = False,
) -> dict[str, Any]:
    url = f"{NOTION_API_BASE}/databases"
    payload = build_trading_plans_database_payload(
        parent_page_id=parent_page_id,
        database_title=database_title,
        is_inline=is_inline,
    )
    resp = requests.post(url, headers=notion_headers(token), json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Notion create trading plans database failed: status={resp.status_code}, body={resp.text}"
        )
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Notion trading plans database for ai_theme_app."
    )
    parser.add_argument(
        "--parent-page-id",
        default=os.getenv("NOTION_PARENT_PAGE_ID", ""),
        help="Parent Notion page id or page URL. Env: NOTION_PARENT_PAGE_ID",
    )
    parser.add_argument(
        "--title",
        default=os.getenv(
            "NOTION_TRADING_PLANS_DATABASE_TITLE",
            "\u4ea4\u6613\u603b\u7ed3\u4e0e\u8ba1\u5212",
        ),
        help="Database title. Default: trading summary and plan.",
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Create database inline under parent page.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Notion database payload without creating it.",
    )
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("[ERROR] missing NOTION_TOKEN", file=sys.stderr)
        return 2

    parent_page_id = normalize_notion_id(args.parent_page_id)
    if not parent_page_id:
        print("[ERROR] missing NOTION_PARENT_PAGE_ID or --parent-page-id", file=sys.stderr)
        return 2

    print(f"[INFO] parent_page_id={parent_page_id}")
    print(f"[INFO] database_title={args.title}")

    if args.dry_run:
        payload = build_trading_plans_database_payload(
            parent_page_id=parent_page_id,
            database_title=args.title,
            is_inline=bool(args.inline),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    db = create_trading_plans_database(
        token=token,
        parent_page_id=parent_page_id,
        database_title=args.title,
        is_inline=bool(args.inline),
    )

    database_id = db.get("id", "")
    url = db.get("url", "")

    print("\n[OK] Notion trading plans database created")
    print(f"NOTION_TRADING_PLANS_DATABASE_ID={database_id}")
    print(f"NOTION_TRADING_PLANS_DATABASE_URL={url}")

    print("\nAdd these to your SPS environment:")
    print(f"export NOTION_TRADING_PLANS_DATABASE_ID='{database_id}'")
    print("export NOTION_TRADE_PLAN_PROP_TITLE='\u6807\u9898'")
    print("export NOTION_TRADE_PLAN_PROP_TRADE_DATE='\u4ea4\u6613\u65e5\u671f'")
    print("export NOTION_TRADE_PLAN_PROP_PLAN_DATE='\u8ba1\u5212\u65e5\u671f'")
    print("export NOTION_TRADE_PLAN_PROP_PLAN_STATUS='\u8ba1\u5212\u72b6\u6001'")
    print("export NOTION_TRADE_PLAN_PROP_REVIEW_STATUS='\u5ba1\u6838\u72b6\u6001'")
    print("export NOTION_TRADE_PLAN_PROP_REVIEW_SCORE='\u5ba1\u6838\u5206'")
    print("export NOTION_TRADE_PLAN_PROP_RISK_LEVEL='\u98ce\u9669\u7b49\u7ea7'")
    print("export NOTION_TRADE_PLAN_PROP_TRIGGER_REVIEW='\u662f\u5426\u89e6\u53d1\u5ba1\u6838'")
    print("export NOTION_TRADE_PLAN_PROP_REVIEWED_AT='reviewed_at'")
    print("export NOTION_TRADE_PLAN_PROP_REPORT_ID='report_id'")
    print("export NOTION_TRADE_PLAN_PROP_REVIEW_ID='review_id'")
    print("export NOTION_TRADE_PLAN_PROP_LATEST_REVIEW_VERSION='latest_review_version'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
