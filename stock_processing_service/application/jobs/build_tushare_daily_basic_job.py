"""BuildTushareDailyBasicJob — 采集 Tushare daily_basic 换手率/量比等基础数据.

入 stock_daily_basic_snapshot 轻量缓存表，供 abnormal_signal / OneToTwo 读取.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto.output_dto import BuildResult


class BuildTushareDailyBasicJob:
    """采集 Tushare daily_basic: turnover_rate, volume_ratio, float_share, etc."""

    def __init__(self, write_port: Any = None, db_gateway: Any = None) -> None:
        self._write_port = write_port
        self._db_gateway = db_gateway

    async def execute(self, trade_date: date) -> BuildResult:
        td_str = trade_date.isoformat()
        token = os.getenv("TUSHARE_TOKEN", "").strip().strip("\"'")
        if not token:
            return BuildResult(name="build_tushare_daily_basic", trade_date=td_str,
                               affected_rows=0, status="failed", warnings=["TUSHARE_TOKEN not set"])

        from stock_service.adapters.tushare_adapter import TushareAdapter

        adapter = TushareAdapter(token, timeout=60, retry_count=1)
        frame = adapter.fetch_daily_basic(td_str)
        if frame is None or not hasattr(frame, "iterrows"):
            return BuildResult(name="build_tushare_daily_basic", trade_date=td_str,
                               affected_rows=0, status="failed", warnings=["daily_basic returned no data"])

        rows: list[dict[str, Any]] = []
        turnover_non_null = 0
        volume_ratio_non_null = 0
        for _, row in frame.iterrows():
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if not ts_code:
                continue
            tr = row.get("turnover_rate")
            tr_f = row.get("turnover_rate_f")
            vr = row.get("volume_ratio")
            if tr is not None:
                try:
                    if float(tr) > 0:
                        turnover_non_null += 1
                except (ValueError, TypeError):
                    pass
            if vr is not None:
                try:
                    if float(vr) > 0:
                        volume_ratio_non_null += 1
                except (ValueError, TypeError):
                    pass

            raw_json = {}
            for col in frame.columns:
                val = row.get(col)
                if val is not None and not (isinstance(val, float) and (val != val)):
                    raw_json[str(col)] = val

            rows.append({
                "trade_date": td_str,
                "stock_id": ts_code,
                "turnover_rate": float(tr) if tr is not None and str(tr) != "nan" else None,
                "turnover_rate_f": float(tr_f) if tr_f is not None and str(tr_f) != "nan" else None,
                "volume_ratio": float(vr) if vr is not None and str(vr) != "nan" else None,
                "float_share": float(row.get("float_share")) if row.get("float_share") is not None else None,
                "circ_mv": float(row.get("circ_mv")) if row.get("circ_mv") is not None else None,
                "total_mv": float(row.get("total_mv")) if row.get("total_mv") is not None else None,
                "raw_json": json.dumps(raw_json, ensure_ascii=False, default=str),
                "source_name": "tushare.daily_basic",
            })

        if not rows:
            return BuildResult(name="build_tushare_daily_basic", trade_date=td_str,
                               affected_rows=0, status="ok_no_data", warnings=["no valid rows after parsing"])

        gw = self._db_gateway
        if gw is not None and hasattr(gw, "upsert_stock_daily_basic_snapshot_rows"):
            written = await gw.upsert_stock_daily_basic_snapshot_rows(rows)
        elif self._write_port is not None and hasattr(self._write_port, "upsert_stock_daily_basic_snapshot_rows"):
            written = await self._write_port.upsert_stock_daily_basic_snapshot_rows(rows)
        else:
            return BuildResult(name="build_tushare_daily_basic", trade_date=td_str,
                               affected_rows=0, status="failed", warnings=["no write port available"])

        return BuildResult(
            name="build_tushare_daily_basic",
            trade_date=td_str,
            affected_rows=written,
            status="ok" if written > 0 else "ok_no_data",
            metrics={
                "rows_fetched": len(rows),
                "rows_upserted": written,
                "turnover_rate_non_null": turnover_non_null,
                "volume_ratio_non_null": volume_ratio_non_null,
            },
        )
