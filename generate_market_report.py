#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from stock_service.config import DEFAULT_CONFIG
from stock_service.publishers.notion_report_publisher import NotionReportPublisher
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.recap_service import RecapService


PROJECT_ROOT = Path(__file__).resolve().parent
TMP_DIR = PROJECT_ROOT / "tmp"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成盘前必读/盘后复盘，并可选发布到 Notion")
    parser.add_argument("--trade-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--report-type", choices=("pre", "post"), required=True)
    parser.add_argument("--publish-notion", action="store_true")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    repo = ReportRepository(DEFAULT_CONFIG)
    await repo.initialize()
    try:
        service = RecapService(repo)
        if args.report_type == "pre":
            report = await service.build_pre_market_report(args.trade_date)
        else:
            report = await service.build_post_market_report(args.trade_date)
    finally:
        await repo.close()

    output_path = TMP_DIR / f"{args.report_type}_market_report_{args.trade_date}.md"
    output_path.write_text(report.to_markdown(), encoding="utf-8")
    print(f"[OK] report={output_path}")

    if args.publish_notion:
        publisher = NotionReportPublisher(
            token=DEFAULT_CONFIG.__dict__.get("notion_report_page_id") and __import__("os").getenv("NOTION_TOKEN", ""),
            page_id=DEFAULT_CONFIG.notion_report_page_id,
        )
        publisher.publish_report(report)
        print(f"[OK] notion_page_id={DEFAULT_CONFIG.notion_report_page_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
