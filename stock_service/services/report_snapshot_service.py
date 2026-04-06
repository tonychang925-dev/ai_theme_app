from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from stock_service.config import StockServiceConfig
from stock_service.models import MarketReport


@dataclass(frozen=True)
class ReportSnapshotResult:
    report_type: str
    trade_date: str
    batch_id: str
    json_path: str
    markdown_path: str


class ReportSnapshotService:
    def __init__(self, config: StockServiceConfig):
        self.config = config

    def write_report_snapshot(self, report: MarketReport, batch_id: str | None = None) -> ReportSnapshotResult:
        final_batch_id = batch_id or datetime.now().strftime("report_%Y%m%d%H%M%S")
        target_dir = self.config.report_snapshot_root / report.report_type
        target_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{report.trade_date}__{final_batch_id}"
        json_path = target_dir / f"{stem}.json"
        markdown_path = target_dir / f"{stem}.md"

        json_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(report.to_markdown(), encoding="utf-8")

        return ReportSnapshotResult(
            report_type=report.report_type,
            trade_date=report.trade_date,
            batch_id=final_batch_id,
            json_path=str(json_path),
            markdown_path=str(markdown_path),
        )
