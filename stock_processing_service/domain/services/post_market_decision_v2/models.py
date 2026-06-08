"""PR-12 PostMarketDecisionV2 data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrongStockPoolItem:
    trade_date: str = ""
    watch_start_date: str = ""
    last_trade_date: str = ""
    mainline_id: str = ""
    subject_key: str = ""
    theme_name: str = ""
    stock_id: str = ""
    stock_name: str = ""
    watch_score: float = 0.0
    watch_priority: float = 0.0
    watch_status: str = "pending_seed"
    pool_entry_type: str = "observe_only"
    strong_grade: str = "REJECT"
    relay_role: str = ""
    source_tag: str = ""
    cycle_state: str = ""
    mainline_strength_score: float = 0.0
    support_type: str | None = None
    support_level: float | None = None
    support_score: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date, "watch_start_date": self.watch_start_date,
            "last_trade_date": self.last_trade_date, "mainline_id": self.mainline_id,
            "subject_key": self.subject_key, "theme_name": self.theme_name,
            "stock_id": self.stock_id, "stock_name": self.stock_name,
            "watch_score": self.watch_score, "watch_priority": self.watch_priority,
            "watch_status": self.watch_status, "pool_entry_type": self.pool_entry_type,
            "strong_grade": self.strong_grade, "relay_role": self.relay_role,
            "source_tag": self.source_tag, "cycle_state": self.cycle_state,
            "mainline_strength_score": self.mainline_strength_score,
            "support_type": self.support_type, "support_level": self.support_level,
            "support_score": self.support_score,
            "evidence": self.evidence, "labels": self.labels,
            "diagnostics": self.diagnostics,
        }


@dataclass
class WeakToStrongD1Item:
    trade_date: str = ""
    next_trade_date: str = ""
    stock_id: str = ""
    stock_name: str = ""
    mainline_id: str = ""
    subject_key: str = ""
    theme_name: str = ""
    candidate_stage: str = "D1"
    candidate_level: str = "observe_only"
    candidate_score: float = 0.0
    support_score: float = 0.0
    momentum_score: float = 0.0
    weak_type: str = ""
    support_type: str = ""
    gap_hit: bool = False
    repair_or_takeover_score: float = 0.0
    weakness_valid_score: float = 0.0
    buy_condition: list[str] = field(default_factory=list)
    invalid_condition: list[str] = field(default_factory=list)
    d2_required: bool = True
    d2_status: str = "pending"
    evidence: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date, "next_trade_date": self.next_trade_date,
            "stock_id": self.stock_id, "stock_name": self.stock_name,
            "mainline_id": self.mainline_id, "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "candidate_stage": self.candidate_stage, "candidate_level": self.candidate_level,
            "candidate_score": self.candidate_score,
            "support_score": self.support_score, "momentum_score": self.momentum_score,
            "weak_type": self.weak_type, "support_type": self.support_type,
            "gap_hit": self.gap_hit,
            "repair_or_takeover_score": self.repair_or_takeover_score,
            "weakness_valid_score": self.weakness_valid_score,
            "buy_condition": self.buy_condition, "invalid_condition": self.invalid_condition,
            "d2_required": self.d2_required, "d2_status": self.d2_status,
            "evidence": self.evidence, "diagnostics": self.diagnostics,
        }


@dataclass
class NextDayFocusStock:
    trade_date: str = ""
    stock_id: str = ""
    stock_name: str = ""
    category: str = "重点观察"
    priority: int = 99
    mainline_id: str = ""
    subject_key: str = ""
    theme_name: str = ""
    pool_entry_type: str = ""
    candidate_level: str = ""
    watch_score: float = 0.0
    candidate_score: float = 0.0
    buy_condition: list[str] = field(default_factory=list)
    invalid_condition: list[str] = field(default_factory=list)
    d2_required: bool = True
    d2_status: str = "pending"
    suggested_position: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date, "stock_id": self.stock_id, "stock_name": self.stock_name,
            "category": self.category, "priority": self.priority,
            "mainline_id": self.mainline_id, "subject_key": self.subject_key,
            "theme_name": self.theme_name, "pool_entry_type": self.pool_entry_type,
            "candidate_level": self.candidate_level,
            "watch_score": self.watch_score, "candidate_score": self.candidate_score,
            "buy_condition": self.buy_condition, "invalid_condition": self.invalid_condition,
            "d2_required": self.d2_required, "d2_status": self.d2_status,
            "suggested_position": self.suggested_position,
        }


@dataclass
class PostMarketDecisionV2:
    trade_date: str = ""
    trading_permission: dict[str, Any] = field(default_factory=dict)
    strong_stock_pool_reviews: list[dict[str, Any]] = field(default_factory=list)
    weak_to_strong_d1_reviews: list[dict[str, Any]] = field(default_factory=list)
    next_day_focus_stocks: list[dict[str, Any]] = field(default_factory=list)
    trading_principle_v2: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "trading_permission": self.trading_permission,
            "strong_stock_pool_reviews": self.strong_stock_pool_reviews,
            "weak_to_strong_d1_reviews": self.weak_to_strong_d1_reviews,
            "next_day_focus_stocks": self.next_day_focus_stocks,
            "trading_principle_v2": self.trading_principle_v2,
            "diagnostics": self.diagnostics,
        }
