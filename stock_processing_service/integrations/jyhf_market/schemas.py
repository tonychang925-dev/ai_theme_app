"""P1-A 标准化数据模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JyhfStockQuote:
    trade_date: str
    ts: str
    stock_id: str
    stock_name: str | None = None
    current: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    vol: float | None = None
    pe: float | None = None
    market_value: float | None = None
    limit_up: float | None = None
    limit_down: float | None = None
    source_endpoint: str = "stock/realtime"
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class JyhfIndexQuote:
    trade_date: str
    ts: str
    index_code: str
    index_name: str = ""
    current: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    vol: float | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class JyhfSubjectStockQuote:
    trade_date: str
    ts: str
    subject_id: str
    stock_id: str
    stock_name: str | None = None
    subject_name: str | None = None
    current: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    vol: float | None = None
    rank_no: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
