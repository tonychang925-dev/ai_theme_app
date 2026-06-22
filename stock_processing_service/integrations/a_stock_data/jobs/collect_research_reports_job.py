"""M5a: Collect Eastmoney research report metadata and write to snapshot."""

from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.integrations.a_stock_data.clients.research_report_client import (
    ENDPOINT_KEY,
    SOURCE_NAME,
    ResearchReportClient,
)


class CollectResearchReportsJob:
    def __init__(
        self,
        *,
        write_port,
        client: ResearchReportClient | None = None,
    ) -> None:
        self._write_port = write_port
        self._client = client or ResearchReportClient()

    async def execute(
        self, trade_date: date, stock_codes: list[str],
    ) -> BuildResult:
        td = trade_date.isoformat()
        snapshot_count = 0
        errors: list[str] = []

        for code in stock_codes:
            try:
                results = await self._client.fetch_reports(code, trade_date)
                for r in results:
                    row = {
                        "trade_date": trade_date,
                        "stock_code": r.stock_code,
                        "stock_name": r.stock_name,
                        "title": r.title,
                        "organization": r.organization,
                        "publish_date": r.publish_date,
                        "rating": r.rating,
                        "eps_2026": r.eps_2026,
                        "eps_2027": r.eps_2027,
                        "eps_2028": r.eps_2028,
                        "pe_2026": r.pe_2026,
                        "pe_2027": r.pe_2027,
                        "pe_2028": r.pe_2028,
                        "industry": r.industry,
                        "pdf_url": r.pdf_url,
                        "source_name": SOURCE_NAME,
                        "endpoint_key": ENDPOINT_KEY,
                        "source_trace_id": r.source_trace_id,
                    }
                    fn = getattr(self._write_port, "upsert_stock_research_report_snapshot", None)
                    if callable(fn):
                        await fn(row)
                    snapshot_count += 1
            except Exception as exc:
                errors.append(f"{code}: {exc}")

        return BuildResult(
            name="collect_research_reports",
            trade_date=td,
            affected_rows=snapshot_count,
            warnings=errors[:10],
            metrics={
                "snapshot_rows": snapshot_count,
                "stocks_processed": len(stock_codes),
                "errors": len(errors),
            },
        )
