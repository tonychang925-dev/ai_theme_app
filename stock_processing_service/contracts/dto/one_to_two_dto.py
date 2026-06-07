from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


Decision = Literal["focus", "observe_only", "pending_review_only", "reject"]
FIRST_BOARD_ALLOWED_TYPES = {
    "strict_first_board",
    "relaunch_first_board",
    "trend_first_board",
    "oversold_first_board",
}


@dataclass(frozen=True)
class OneToTwoFeatures:
    trade_date: str
    watch_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    subject_name: str

    is_confirmed_mainline: bool
    is_strong_hotspot: bool
    mainline_or_hotspot_state: str
    lifecycle_state: str
    market_trade_mode: str
    allow_trade: bool

    is_first_limit_up: bool
    is_one_word_board: bool
    is_late_seal: bool
    first_limit_time: str | None
    open_board_count: int | None

    turnover_rate: Decimal | None
    amount: Decimal | None
    close_seal_amount: Decimal | None
    seal_ratio: Decimal | None

    float_mcap: Decimal | None
    position_120: Decimal | None
    is_downtrend: bool | None
    near_pressure: bool | None

    same_subject_limit_count: int | None
    same_subject_strong_count: int | None
    subject_authenticity: dict[str, Any] = field(default_factory=dict)
    kline_pattern_quality: dict[str, Any] = field(default_factory=dict)

    data_quality: dict[str, Any] = field(default_factory=dict)
    source_trace: dict[str, Any] = field(default_factory=dict)
    first_board_type: str = "strict_first_board"
    first_board_trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_first_limit_up", str(self.first_board_type or "") in FIRST_BOARD_ALLOWED_TYPES)


@dataclass(frozen=True)
class RuleResult:
    decision: Decision
    veto_reasons: list[str]
    risk_flags: list[str]


@dataclass(frozen=True)
class ScoreResult:
    final_score: Decimal | None
    watch_level: str | None
    score_detail: dict[str, Any]


@dataclass(frozen=True)
class SetupPlanCandidate:
    features: OneToTwoFeatures
    rule_result: RuleResult
    score_result: ScoreResult
    trigger_plan: dict[str, Any]
    invalidation_plan: list[str]
    exit_plan: list[str]


@dataclass(frozen=True)
class OneToTwoSetupPlanDTO:
    summary: dict[str, Any]
    items: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    candidate_features: list[dict[str, Any]] = field(default_factory=list)
    setup_type: str = "one_to_two"

    def to_dict(self) -> dict[str, Any]:
        return {
            "watchlists": {
                "one_to_two": {
                    "summary": dict(self.summary),
                    "items": list(self.items),
                    "diagnostics": dict(self.diagnostics),
                }
            }
        }
