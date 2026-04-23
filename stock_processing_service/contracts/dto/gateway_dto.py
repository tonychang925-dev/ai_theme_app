from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class TradeCalendarDTO:
    trade_date: date
    is_open: bool
    prev_trade_date: date | None = None
    next_trade_date: date | None = None


@dataclass
class StockDailyBarDTO:
    trade_date: date
    stock_id: str
    stock_name: str | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    pre_close: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None


@dataclass
class SubjectStockPoolRowDTO:
    trade_date: date
    subject_key: str
    subject_name: str | None
    stock_id: str
    stock_name: str | None
    in_pool_flag: bool
    pool_rank: int | None = None
    support_score: float | None = None


@dataclass
class SubjectContextDTO:
    subject_key: str
    subject_name: str | None
    trade_date: date
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotDocDTO:
    trade_date: date
    snapshot_version: str
    batch_id: str
    trace_id: str
    doc: dict[str, Any]
    created_at: datetime | None = None
