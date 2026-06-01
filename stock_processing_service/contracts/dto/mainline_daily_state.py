"""MainlineDailyState DTO — 每日主线状态快照，一条 active mainline 一行。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any


@dataclass
class MainlineDailyStateDTO:
    trade_date: _date
    mainline_id: str
    canonical_subject_key: str
    mainline_name: str = ""
    run_id: str = ""
    active_subject_keys_json: list[str] = field(default_factory=list)
    active_subject_count: int = 0
    event_count_1d: int = 0
    event_count_3d: int = 0
    event_count_7d: int = 0
    lifecycle_state: str = "unknown"
    mainline_alive: bool = False
    mainline_trade_alive: bool = False
    fade_risk_score: float | None = None
    broad_market_regime: str = ""
    short_term_sentiment: str = ""
    mainline_environment: str = ""
    market_structure: str = ""
    trade_mode: str = "no_trade"
    allow_trade: bool = False
    position_limit: float = 0.0
    strong_pool_count: int = 0
    d1_count: int = 0
    focus_count: int = 0
    layer_c_subject_keys_json: list[str] = field(default_factory=list)
    mainline_filtered_subject_keys_json: list[str] = field(default_factory=list)
    missing_registry_subject_keys_json: list[str] = field(default_factory=list)
    no_trade_blocking_rule: str = ""
    diagnostics_json: dict[str, Any] = field(default_factory=dict)
    source_version: str = "v1"

    def to_upsert_dict(self) -> dict[str, Any]:
        import json
        return {
            "run_id": self.run_id,
            "trade_date": self.trade_date,
            "mainline_id": self.mainline_id,
            "canonical_subject_key": self.canonical_subject_key,
            "mainline_name": self.mainline_name,
            "active_subject_keys_json": json.dumps(self.active_subject_keys_json),
            "active_subject_count": self.active_subject_count,
            "event_count_1d": self.event_count_1d,
            "event_count_3d": self.event_count_3d,
            "event_count_7d": self.event_count_7d,
            "lifecycle_state": self.lifecycle_state,
            "mainline_alive": self.mainline_alive,
            "mainline_trade_alive": self.mainline_trade_alive,
            "fade_risk_score": self.fade_risk_score,
            "broad_market_regime": self.broad_market_regime,
            "short_term_sentiment": self.short_term_sentiment,
            "mainline_environment": self.mainline_environment,
            "market_structure": self.market_structure,
            "trade_mode": self.trade_mode,
            "allow_trade": self.allow_trade,
            "position_limit": self.position_limit,
            "strong_pool_count": self.strong_pool_count,
            "d1_count": self.d1_count,
            "focus_count": self.focus_count,
            "layer_c_subject_keys_json": json.dumps(self.layer_c_subject_keys_json),
            "mainline_filtered_subject_keys_json": json.dumps(self.mainline_filtered_subject_keys_json),
            "missing_registry_subject_keys_json": json.dumps(self.missing_registry_subject_keys_json),
            "no_trade_blocking_rule": self.no_trade_blocking_rule,
            "diagnostics_json": json.dumps(self.diagnostics_json),
            "source_version": self.source_version,
        }
