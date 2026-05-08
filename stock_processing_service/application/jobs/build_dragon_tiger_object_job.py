"""龙虎榜对象构建 Job — 新链 Gateway 架构。

替换旧脚本 database_service/scripts/build_dragon_tiger_object.py 的 PostgresDatabaseManager 直连。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


@dataclass
class DragonTigerObjectBuildConfig:
    trade_date: date
    tushare_token: str = ""


class BuildDragonTigerObjectJob:
    """龙虎榜对象构建 Job。

    Domain 层使用现有 DragonTigerObjectService（纯数据转换），
    Infrastructure 层通过 Gateway 写入数据库。
    """

    def __init__(
        self,
        write_port: Any = None,
        config: DragonTigerObjectBuildConfig | None = None,
    ) -> None:
        self._write_port = write_port
        self._config = config

    async def execute(self, trade_date: date, tushare_token: str = "") -> BuildResult:
        """执行龙虎榜对象构建。"""
        from database_service.scripts.build_dragon_tiger_object import (
            DragonTigerObjectService,
            TushareDragonTigerSnapshotService,
        )
        from stock_service.config import StockServiceConfig

        stock_config = StockServiceConfig()
        if tushare_token:
            stock_config.tushare_token = tushare_token

        snapshot_service = TushareDragonTigerSnapshotService(stock_config)
        top_list_result = snapshot_service.fetch_or_cache_top_list(trade_date)
        top_inst_result = snapshot_service.fetch_or_cache_top_inst(trade_date)

        service = DragonTigerObjectService()
        top_list_rows = service.normalize_top_list(top_list_result.records)
        top_inst_rows = service.normalize_top_inst(top_inst_result.records)
        objects = service.build_objects(top_list_rows, top_inst_rows)

        rows = [
            {
                "trade_date": obj.trade_date,
                "stock_id": obj.stock_id,
                "stock_name": obj.stock_name,
                "reason": obj.reason,
                "close_price": obj.close_price,
                "pct_change": obj.pct_change,
                "turnover_rate": obj.turnover_rate,
                "total_amount": obj.total_amount,
                "billboard_buy_amount": obj.billboard_buy_amount,
                "billboard_sell_amount": obj.billboard_sell_amount,
                "billboard_amount": obj.billboard_amount,
                "net_amount": obj.net_amount,
                "net_rate": obj.net_rate,
                "amount_rate": obj.amount_rate,
                "float_market_value": obj.float_market_value,
                "institution_buy_amount": obj.institution_buy_amount,
                "institution_sell_amount": obj.institution_sell_amount,
                "institution_net_buy": obj.institution_net_buy,
                "institution_seat_count": obj.institution_seat_count,
                "seat_summary": obj.seat_summary,
                "source_trace_id": obj.source_trace_id,
                "source_trace": obj.source_trace,
                "source_version": obj.source_version,
                "rule_version": obj.rule_version,
            }
            for obj in objects
        ]

        written = 0
        if rows and self._write_port:
            fn = getattr(self._write_port, "upsert_dragon_tiger_object_rows", None)
            if callable(fn):
                written = await fn(rows)

        return BuildResult(
            name="build_dragon_tiger_object",
            trade_date=str(trade_date),
            affected_rows=written,
            status="ok" if written > 0 else "ok_no_rows",
        )
