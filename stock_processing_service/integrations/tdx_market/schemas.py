"""TDX 标准化数据模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TdxStockQuote:
    trade_date: str
    ts: str
    stock_id: str
    system_stock_id: str = ""
    stock_name: str | None = None
    price: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    last_close: float | None = None
    amount: float | None = None
    vol: float | None = None
    servertime: str | None = None
    bid1: float | None = None
    ask1: float | None = None
    bid_vol1: int | None = None
    ask_vol1: int | None = None
    bid2: float | None = None
    ask2: float | None = None
    bid_vol2: int | None = None
    ask_vol2: int | None = None
    bid3: float | None = None
    ask3: float | None = None
    bid_vol3: int | None = None
    ask_vol3: int | None = None
    bid4: float | None = None
    ask4: float | None = None
    bid_vol4: int | None = None
    ask_vol4: int | None = None
    bid5: float | None = None
    ask5: float | None = None
    bid_vol5: int | None = None
    ask_vol5: int | None = None
    source: str = "tdx_mootdx"
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TdxMinuteBar:
    trade_date: str
    ts: str
    stock_id: str
    system_stock_id: str = ""
    minute_index: int = 0
    price: float | None = None
    vol: float | None = None
    volume: float | None = None
    source: str = "tdx_mootdx"
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TdxDailyBar:
    trade_date: str
    ts: str
    stock_id: str
    system_stock_id: str = ""
    bar_time: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    vol: float | None = None
    amount: float | None = None
    frequency: int = 9
    source: str = "tdx_mootdx"
    raw_json: dict[str, Any] = field(default_factory=dict)
