from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class StockDailySnapshotContract:
    trade_date: date
    stock_id: str
    stock_name: str
    close_price: float
    pct_chg: float
    volume: float
    amount: float
    limit_up_price: float
    limit_down_price: float
    snapshot_version: str
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    pre_close: float | None = None
    source_trace_id: str | None = None


@dataclass
class SubjectStockDailySnapshotContract:
    trade_date: date
    subject_key: str
    stock_id: str
    subject_name: str
    in_pool_flag: bool
    pool_rank: int
    support_score: float
    snapshot_version: str
    stock_name: str | None = None
    pct_chg: float | None = None
    close_price: float | None = None
    evidence_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class StockAbnormalEventContract:
    trade_date: date
    stock_id: str
    event_type: str
    event_score: float
    evidence_rules: list[str]
    raw_metrics: dict[str, Any]
    snapshot_version: str
    subject_key: str | None = None
    subject_name: str | None = None
    note: str | None = None


@dataclass
class ThemeStockLeaderboardContract:
    trade_date: date
    subject_key: str
    stock_id: str
    leaderboard_rank: int
    leader_score: float
    score_breakdown: dict[str, Any]
    snapshot_version: str
    stock_name: str | None = None
    role_label: str | None = None
    evidence_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreMarketBriefSnapshotContract:
    trade_date: date
    snapshot_version: str
    batch_id: str
    trace_id: str
    brief_doc: dict[str, Any]
    summary: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    source_trace_id: str | None = None


@dataclass
class PostMarketRecapSnapshotContract:
    trade_date: date
    snapshot_version: str
    batch_id: str
    trace_id: str
    recap_doc: dict[str, Any]
    summary: str | None = None
    conclusions: list[str] = field(default_factory=list)
    source_trace_id: str | None = None
