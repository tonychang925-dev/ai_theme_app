#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TRADING_PLANS_DATABASE_ID = "36f7bab0-ee1d-815f-9af6-da82dae8051c"


def normalize_notion_id(value: str) -> str:
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


def next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def rich_text(content: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": content}}]


def paragraph(content: str = "") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text(content) if content else []},
    }


def heading_2(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": rich_text(content)},
    }


def bullet(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(content)},
    }


def build_page_children() -> list[dict[str, Any]]:
    return [
        heading_2("一、今日交易总结"),
        bullet("今天是否按计划执行："),
        bullet("是否有冲动交易、追高、恐慌割肉："),
        bullet("是否违反仓位纪律："),
        bullet("今日最大问题："),
        paragraph(),
        heading_2("二、今日市场理解"),
        bullet("今日主线："),
        bullet("加强题材："),
        bullet("退潮题材："),
        bullet("市场状态：进攻 / 防守 / 混沌 / 退潮"),
        paragraph(),
        heading_2("三、持仓复盘"),
        bullet("当前持仓："),
        bullet("买入逻辑是否仍成立："),
        bullet("明日处理计划："),
        bullet("止损 / 止盈条件："),
        paragraph(),
        heading_2("四、明日交易计划"),
        bullet("重点观察题材："),
        bullet("重点观察个股："),
        bullet("买入条件："),
        bullet("不买条件："),
        bullet("仓位上限："),
        paragraph(),
        heading_2("五、风险预案"),
        bullet("竞价不及预期："),
        bullet("主线退潮："),
        bullet("目标股高开过多："),
        bullet("市场无主线："),
        paragraph(),
        heading_2("六、AI审核区"),
        paragraph("写完计划后，将「计划状态」改为「待审核」，并勾选「是否触发审核」。系统审核结果后续会写入这里。"),
    ]


def build_create_page_payload(
    *,
    database_id: str,
    trade_date: str,
    plan_date: str,
    title: str,
) -> dict[str, Any]:
    report_id = f"trade_plan:{trade_date}:{plan_date}"
    review_id = f"trade_plan_review:{trade_date}:{plan_date}"
    return {
        "parent": {
            "type": "database_id",
            "database_id": database_id,
        },
        "icon": {
            "type": "emoji",
            "emoji": "\U0001f4dd",
        },
        "properties": {
            "\u6807\u9898": {
                "title": rich_text(title),
            },
            "\u4ea4\u6613\u65e5\u671f": {
                "date": {"start": trade_date},
            },
            "\u8ba1\u5212\u65e5\u671f": {
                "date": {"start": plan_date},
            },
            "\u8ba1\u5212\u72b6\u6001": {
                "select": {"name": "\u8349\u7a3f"},
            },
            "\u5ba1\u6838\u72b6\u6001": {
                "select": {"name": "\u672a\u5ba1\u6838"},
            },
            "\u662f\u5426\u89e6\u53d1\u5ba1\u6838": {
                "checkbox": False,
            },
            "report_id": {
                "rich_text": rich_text(report_id),
            },
            "review_id": {
                "rich_text": rich_text(review_id),
            },
            "latest_review_version": {
                "number": 0,
            },
        },
        "children": build_page_children(),
    }


def create_trade_plan_page(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=notion_headers(token),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Notion create trade plan page failed: status={resp.status_code}, body={resp.text}"
        )
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a dated Notion trade summary and plan page."
    )
    parser.add_argument(
        "--database-id",
        default=os.getenv("NOTION_TRADING_PLANS_DATABASE_ID", DEFAULT_TRADING_PLANS_DATABASE_ID),
        help="Trading plans database id or URL. Env: NOTION_TRADING_PLANS_DATABASE_ID",
    )
    parser.add_argument(
        "--trade-date",
        default=date.today().isoformat(),
        help="Review date, YYYY-MM-DD. Default: today.",
    )
    parser.add_argument(
        "--plan-date",
        default="",
        help="Plan date, YYYY-MM-DD. Default: next weekday after trade-date.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional page title.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the create-page payload without writing Notion.",
    )
    args = parser.parse_args()

    database_id = normalize_notion_id(args.database_id)
    if not database_id:
        print("[ERROR] missing NOTION_TRADING_PLANS_DATABASE_ID or --database-id", file=sys.stderr)
        return 2

    try:
        trade_dt = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"[ERROR] invalid --trade-date: {args.trade_date}", file=sys.stderr)
        return 2

    if args.plan_date:
        try:
            plan_dt = date.fromisoformat(args.plan_date)
        except ValueError:
            print(f"[ERROR] invalid --plan-date: {args.plan_date}", file=sys.stderr)
            return 2
    else:
        plan_dt = next_weekday(trade_dt)

    title = args.title.strip() or f"{trade_dt.isoformat()} 交易总结与 {plan_dt.isoformat()} 交易计划"
    payload = build_create_page_payload(
        database_id=database_id,
        trade_date=trade_dt.isoformat(),
        plan_date=plan_dt.isoformat(),
        title=title,
    )

    print(f"[INFO] database_id={database_id}")
    print(f"[INFO] title={title}")

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token:
        print("[ERROR] missing NOTION_TOKEN", file=sys.stderr)
        return 2

    page = create_trade_plan_page(token, payload)
    print("\n[OK] Notion trade plan page created")
    print(f"PAGE_ID={page.get('id', '')}")
    print(f"PAGE_URL={page.get('url', '')}")
    print(f"TRADE_DATE={trade_dt.isoformat()}")
    print(f"PLAN_DATE={plan_dt.isoformat()}")
    print(f"CREATED_AT={datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
