from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.recap_service import RecapService
from stock_service.services.report_snapshot_service import ReportSnapshotService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate report snapshot from real DB data")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD format")
    parser.add_argument(
        "--report-type",
        choices=["pre_market", "post_market"],
        default="post_market",
        help="Report type to generate",
    )
    parser.add_argument(
        "--batch-id",
        default="",
        help="Optional fixed batch id for snapshot file names",
    )
    parser.add_argument(
        "--postgres-database",
        default="stock_data_test",
        help="Target database name",
    )
    return parser


async def main_async() -> int:
    args = build_parser().parse_args()
    config = StockServiceConfig(postgres_database=args.postgres_database)
    repo = ReportRepository(config)
    await repo.initialize()
    try:
        recap = RecapService(repo)
        if args.report_type == "pre_market":
            report = await recap.build_pre_market_report(args.trade_date)
        else:
            report = await recap.build_post_market_report(args.trade_date)

        result = ReportSnapshotService(config).write_report_snapshot(report, batch_id=args.batch_id or None)

        preview = {
            "title": report.title,
            "summary": report.summary,
            "highlights": report.highlights[:5],
            "sections": [(name, items[:5]) for name, items in report.sections],
        }
        print(f"[OK] report_type={report.report_type}")
        print(f"[OK] trade_date={report.trade_date}")
        print(f"[OK] json={result.json_path}")
        print(f"[OK] markdown={result.markdown_path}")
        print(f"[OK] preview={json.dumps(preview, ensure_ascii=False)}")
        return 0
    finally:
        await repo.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
