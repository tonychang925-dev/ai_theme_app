"""竞价观察池构建 Job — 新链 Gateway 架构。

替换旧脚本：database_service/scripts/build_auction_watch_universe.py
从 DB 读取龙头/主线/周期数据 → AuctionWatchUniverseService → Gateway upsert。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


class BuildAuctionWatchUniverseJob:
    def __init__(self, read_port: Any = None, write_port: Any = None) -> None:
        self._read_port = read_port
        self._write_port = write_port

    async def execute(self, trade_date: date, source_trade_date: date | None = None) -> BuildResult:
        from stock_service.services.auction_watch_universe_service import (
            AuctionWatchUniverseService,
            WatchCycleInput,
            WatchLeaderInput,
            WatchMainlineInput,
        )

        # 解析源交易日（默认取前一日）
        if source_trade_date is None:
            fn = getattr(self._read_port, "get_trade_calendar", None)
            if callable(fn):
                cal = await fn(trade_date)
                source_trade_date = cal.prev_trade_date if cal else None
        if source_trade_date is None:
            return BuildResult(name="build_auction_watch_universe", trade_date=str(trade_date),
                               affected_rows=0, status="failed", warnings=["missing source_trade_date"])

        # 读取龙头/主线/周期
        leaders = []
        mainlines = {}
        cycles = {}
        if self._read_port:
            ldr_fn = getattr(self._read_port, "get_auction_board_leaders", None)
            ml_fn = getattr(self._read_port, "get_auction_mainlines", None)
            cyc_fn = getattr(self._read_port, "get_auction_cycles", None)
            if callable(ldr_fn):
                leaders = await ldr_fn(source_trade_date)
            if callable(ml_fn):
                mainlines = {str(r["subject_key"]): r for r in await ml_fn(source_trade_date)}
            if callable(cyc_fn):
                cycles = {str(r["subject_key"]): r for r in await cyc_fn(source_trade_date)}

        # 构建 items
        service = AuctionWatchUniverseService()
        items = []
        for row in leaders:
            subject_key = str(row["subject_key"])
            mainline_row = mainlines.get(subject_key)
            cycle_row = cycles.get(subject_key)
            if not mainline_row or not cycle_row:
                continue

            mainline = WatchMainlineInput(
                subject_key=subject_key,
                theme_name=mainline_row["theme_name"],
                mainline_alive=bool(mainline_row["mainline_alive"]),
                final_cycle_state=str(mainline_row.get("final_cycle_state") or ""),
                mainline_strength_score=float(mainline_row.get("mainline_strength_score") or 0.0),
                fade_watch=bool(mainline_row.get("fade_watch") or False),
                fade_confirmed=bool(mainline_row.get("fade_confirmed") or False),
            )
            cycle = WatchCycleInput(
                subject_key=subject_key,
                primary_cycle_stage=cycle_row["primary_cycle_stage"],
                action_bias=cycle_row["action_bias"],
            )
            leader = WatchLeaderInput(
                subject_key=subject_key,
                stock_id=str(row["stock_id"]),
                stock_name=row["stock_name"],
                role_label=row["role_label"],
                candidate_rank=int(row["candidate_rank"]),
            )
            if not service.is_eligible(mainline, cycle, leader):
                continue
            item = service.build_item(
                str(source_trade_date), str(trade_date),
                mainline, cycle, leader,
            )
            if item.candidate_priority == "P3":
                continue
            items.append(item)

        # 写入
        written = 0
        if items and self._write_port:
            rows = [
                {
                    "source_trade_date": item.source_trade_date,
                    "trade_date": item.trade_date,
                    "stock_id": item.stock_id,
                    "stock_name": item.stock_name,
                    "subject_key": item.subject_key,
                    "theme_name": item.theme_name,
                    "theme_tier": item.theme_tier,
                    "mainline_alive": item.mainline_alive,
                    "primary_cycle_stage": item.primary_cycle_stage,
                    "action_bias": item.action_bias,
                    "role_label": item.role_label,
                    "candidate_rank": item.candidate_rank,
                    "candidate_priority": item.candidate_priority,
                    "is_reversal_watch": item.is_reversal_watch,
                    "source_type": item.source_type,
                    "source_trace_id": item.source_trace_id,
                    "source_trace": item.source_trace,
                    "source_version": item.source_version,
                    "rule_version": item.rule_version,
                }
                for item in items
            ]
            fn = getattr(self._write_port, "upsert_auction_watch_universe_rows", None)
            if callable(fn):
                written = await fn(rows)

        return BuildResult(
            name="build_auction_watch_universe",
            trade_date=str(trade_date),
            affected_rows=written,
            status="ok" if written > 0 else "ok_no_data",
            metrics={"p1_count": sum(1 for x in items if x.candidate_priority == "P1"),
                      "p2_count": sum(1 for x in items if x.candidate_priority == "P2")},
        )
