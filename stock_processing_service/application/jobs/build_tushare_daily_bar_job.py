"""Tushare 日线数据采集 Job — 直接拉取 API → Gateway 写入 DB。

替换旧链路：sync_tushare_kline_local.py → import_tushare_daily_bar_to_db.py
不再经过本地 JSONL 文件中转。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


@dataclass
class TushareDailyBarConfig:
    trade_date: date
    tushare_token: str = ""
    pause_seconds: float = 0.1
    jyhf_universe_only: bool = True


class BuildTushareDailyBarJob:
    """Tushare 日线采集 Job。

    直接调用 TushareAdapter → upsert_stock_daily_snapshot_rows（Gateway），
    不经过本地 JSONL 文件中转。
    """

    def __init__(self, write_port: Any = None) -> None:
        self._write_port = write_port

    async def execute(self, trade_date: date, token: str, pause_seconds: float = 0.1) -> BuildResult:
        from stock_service.adapters.tushare_adapter import TushareAdapter
        from stock_service.config import StockServiceConfig

        config = StockServiceConfig()
        config.tushare_token = token

        adapter = TushareAdapter(config)
        quotes = adapter.fetch_daily_quotes(str(trade_date))

        rows = []
        for q in (quotes or []):
            rows.append({
                "trade_date": str(trade_date),
                "stock_id": q.get("ts_code", ""),
                "stock_name": q.get("name", ""),
                "open_price": q.get("open", 0),
                "high_price": q.get("high", 0),
                "low_price": q.get("low", 0),
                "close_price": q.get("close", 0),
                "pre_close": q.get("pre_close", 0),
                "pct_chg": q.get("pct_chg", 0),
                "volume": q.get("vol", 0),
                "amount": q.get("amount", 0),
                "source_name": "tushare",
                "source_trace_id": f"tushare_daily_{trade_date}",
            })

        written = 0
        if rows and self._write_port:
            fn = getattr(self._write_port, "upsert_stock_daily_snapshot_rows", None)
            if callable(fn):
                written = await fn(rows)

        return BuildResult(
            name="build_tushare_daily_bar",
            trade_date=str(trade_date),
            affected_rows=written,
            status="ok" if written > 0 else "ok_no_data",
            metrics={"tushare_raw_count": len(quotes or []), "upserted": written},
        )
