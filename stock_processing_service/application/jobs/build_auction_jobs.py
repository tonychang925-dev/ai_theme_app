"""竞价快照 Job — 新链架构（bridge 模式，后续升级为完整 Gateway）。

替换旧脚本 database_service/scripts/build_pre_market_auction_snapshot.py 的自行 DB 管理。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


class BuildAuctionSnapshotJob:
    """竞价快照采集 Job — 通过 Gateway 注入 db_manager 给脚本，消除自建 DB 连接。"""

    def __init__(
        self,
        write_port: Any = None,
        universe_source: str = "auction_watch_universe",
        max_stocks: int = 0,
        db_gateway: Any = None,
    ) -> None:
        self._write_port = write_port
        self._universe_source = universe_source
        self._max_stocks = max_stocks
        self._db_gateway = db_gateway

    async def execute(
        self,
        trade_date: date,
        tushare_token: str = "",
        *,
        universe_source: str | None = None,
        max_stocks: int | None = None,
    ) -> BuildResult:
        import argparse

        source = universe_source or self._universe_source
        n_stocks = max_stocks if max_stocks is not None else self._max_stocks

        ns = argparse.Namespace()
        ns.trade_date = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
        ns.token = tushare_token
        ns.allow_online_fetch = bool(tushare_token)
        ns.force_refresh = True
        ns.universe_source = source
        ns.max_stocks = n_stocks
        ns.timeline_json = ""
        ns.source_trade_date = ""
        ns.top_k = 40
        ns.proxy_ratio = 0.08

        db_manager = getattr(self._db_gateway, "_client", None) if self._db_gateway else None
        from database_service.scripts.build_pre_market_auction_snapshot import main_async
        exit_code = await main_async(args=ns, db_manager=db_manager)

        ec = exit_code or 0
        if ec == 0:
            status = "ok"
        elif ec == 2:
            status = "ok_no_data"
        else:
            status = "failed"
        return BuildResult(
            name="build_auction_snapshot",
            trade_date=str(trade_date),
            affected_rows=int(status == "ok"),
            status=status,
        )


class BuildAuctionSignalJob:
    """竞价信号 Job — 通过 Gateway 注入 db_manager 给脚本，消除自建 DB 连接。"""

    def __init__(
        self,
        write_port: Any = None,
        top_k: int = 40,
        db_gateway: Any = None,
    ) -> None:
        self._write_port = write_port
        self._top_k = top_k
        self._db_gateway = db_gateway

    async def execute(
        self,
        trade_date: date,
        *,
        top_k: int | None = None,
    ) -> BuildResult:
        import argparse

        ns = argparse.Namespace()
        ns.trade_date = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
        ns.top_k = top_k if top_k is not None else self._top_k
        ns.source_trade_date = ""

        db_manager = getattr(self._db_gateway, "_client", None) if self._db_gateway else None
        from database_service.scripts.build_pre_market_auction_signal import main_async
        exit_code = await main_async(args=ns, db_manager=db_manager)

        ec = exit_code or 0
        if ec == 0:
            status = "ok"
        elif ec == 2:
            status = "ok_no_data"
        else:
            status = "failed"
        return BuildResult(
            name="build_auction_signal",
            trade_date=str(trade_date),
            affected_rows=int(status == "ok"),
            status=status,
        )
