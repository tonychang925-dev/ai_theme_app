"""PR4.2.31c-3 Eastmoney fund-flow collector tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.integrations.a_stock_data.clients.eastmoney_fund_flow_client import (
    RawHttpResult,
)
from stock_processing_service.integrations.a_stock_data.jobs.collect_eastmoney_fund_flow_job import (
    CollectEastmoneyFundFlowJob,
)


@dataclass
class _Diag:
    consecutive_failures: int = 0
    total_requests: int = 1
    total_failures: int = 0
    last_success_at: float | None = 1.0


class _FakeClient:
    diagnostics = _Diag()

    async def fetch_stock_daykline(self, stock_code: str, limit: int = 120) -> RawHttpResult:
        assert stock_code == "300223"
        assert limit == 20
        return RawHttpResult(
            source_name="eastmoney_fund_flow",
            endpoint_key="eastmoney_stock_fflow_daykline",
            request_url="fixture://daykline",
            request_params={"secid": "0.300223", "lmt": limit},
            status_code=200,
            response_json={
                "data": {
                    "code": "300223",
                    "name": "北京君正",
                    "klines": ["2026-07-09,100.0,20.0,-10.0,30.0,60.0,1,2,3,4,5,6,7"],
                }
            },
        )


class _FakeWritePort:
    def __init__(self) -> None:
        self.raw_rows: list[dict[str, Any]] = []
        self.fund_flow_rows: list[dict[str, Any]] = []

    async def upsert_source_raw_snapshot(self, row: dict[str, Any]) -> int:
        self.raw_rows.append(row)
        return 42

    async def upsert_stock_fund_flow_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        self.fund_flow_rows.extend(rows)
        return len(rows)


async def test_collect_eastmoney_fund_flow_writes_evidence_only() -> None:
    """TC-ID: PR4.2.31c3-collector-writes-fund-flow-evidence-only."""
    write_port = _FakeWritePort()
    job = CollectEastmoneyFundFlowJob(
        write_port=write_port,
        stock_codes=["300223"],
        client=_FakeClient(),
        limit=20,
    )

    result = await job.execute(date(2026, 7, 9))

    assert result.name == "collect_eastmoney_fund_flow"
    assert result.affected_rows == 1
    assert len(write_port.raw_rows) == 1
    assert len(write_port.fund_flow_rows) == 1
    row = write_port.fund_flow_rows[0]
    assert row["trade_date"] == date(2026, 7, 9)
    assert row["stock_code"] == "300223"
    assert row["stock_name"] == "北京君正"
    assert row["net_inflow_yuan"] == 100.0
    assert row["small_net_inflow_yuan"] == 20.0
    assert row["medium_net_inflow_yuan"] == -10.0
    assert row["large_net_inflow_yuan"] == 30.0
    assert row["super_large_net_inflow_yuan"] == 60.0
    assert row["source_name"] == "eastmoney_fund_flow"
    assert row["source_endpoint"] == "eastmoney_stock_fflow_daykline"
    assert row["source_version"] == "eastmoney_fflow_daykline_f52_v1"
    assert row["frequency"] == "DAILY"
    assert row["window"] == "1D"
    assert row["market_scope"] == "CN_A"
    assert row["quality"] == "OK"
    assert row["diagnostics"]["raw_snapshot_id"] == 42
    assert "institution" not in row
    assert "hot_money" not in row
    assert "style" not in row
