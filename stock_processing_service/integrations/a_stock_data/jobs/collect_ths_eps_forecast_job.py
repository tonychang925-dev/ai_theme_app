"""M4d: Collect THS EPS forecasts and write to stock_expectation_snapshot."""

from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.domain.services.expectation_evidence import (
    build_expectation_evidence,
)
from stock_processing_service.integrations.a_stock_data.clients.ths_eps_client import (
    EPS_ENDPOINT,
    SOURCE_NAME,
    ThsEpsClient,
)


class CollectThsEpsForecastJob:
    """Fetch THS EPS forecasts for a list of stocks, write to snapshot."""

    def __init__(
        self,
        *,
        write_port,
        client: ThsEpsClient | None = None,
    ) -> None:
        self._write_port = write_port
        self._client = client or ThsEpsClient()

    async def execute(
        self, trade_date: date, stock_codes: list[str],
    ) -> BuildResult:
        td = trade_date.isoformat()
        snapshot_count = 0
        evidence_count = 0
        errors: list[str] = []

        for code in stock_codes:
            try:
                results = await self._client.fetch_forecast(code, trade_date)
                for r in results:
                    row = {
                        "trade_date": trade_date,
                        "stock_code": r.stock_code,
                        "stock_name": r.stock_name,
                        "year": r.year,
                        "eps_mean": r.eps_mean,
                        "eps_min": r.eps_min,
                        "eps_max": r.eps_max,
                        "analyst_count": r.analyst_count,
                        "industry_avg_eps": r.industry_avg_eps,
                        "source_name": SOURCE_NAME,
                        "endpoint_key": EPS_ENDPOINT,
                        "source_trace_id": r.source_trace_id,
                    }
                    fn = getattr(self._write_port, "upsert_stock_expectation_snapshot", None)
                    if callable(fn):
                        await fn(row)
                    snapshot_count += 1

                    ev = build_expectation_evidence(
                        stock_code=r.stock_code,
                        stock_name=r.stock_name,
                        year=r.year,
                        eps_mean=r.eps_mean,
                        analyst_count=r.analyst_count,
                        industry_avg_eps=r.industry_avg_eps,
                        eps_min=r.eps_min,
                        eps_max=r.eps_max,
                        trade_date=td,
                    )
                    evidence_count += 1
            except Exception as exc:
                errors.append(f"{code}: {exc}")

        return BuildResult(
            name="collect_ths_eps_forecast",
            trade_date=td,
            affected_rows=snapshot_count,
            warnings=errors[:10],
            metrics={
                "snapshot_rows": snapshot_count,
                "evidence_rows": evidence_count,
                "stocks_processed": len(stock_codes),
                "errors": len(errors),
            },
        )
