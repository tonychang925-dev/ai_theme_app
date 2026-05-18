"""W2S backtest domain models, enums and DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class RunType(str, Enum):
    SIGNAL_VALIDATION = "signal_validation"
    DAILY_BACKTEST = "daily_backtest"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PoolEntryType(str, Enum):
    FORMAL = "formal"
    OBSERVE_ONLY = "observe_only"
    REJECT = "reject"


class ConfirmSource(str, Enum):
    REAL_AUCTION = "real_auction"
    AUCTION_SNAPSHOT = "auction_snapshot"
    DAILY_OPEN_PROXY = "daily_open_proxy"
    MISSING = "missing"


class ConfirmLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    X = "X"
    PROXY_A = "proxy_A"
    PROXY_B = "proxy_B"
    PROXY_C = "proxy_C"
    PROXY_X = "proxy_X"


class LeaderRoleProxy(str, Enum):
    LEADER = "leader"
    CARD = "card"
    ASSIST = "assist"
    SUPPLEMENT = "supplement"
    UNKNOWN = "unknown"


class BoardType(str, Enum):
    MAIN_BOARD = "main_board"
    CHINEXT = "chinext"
    STAR = "star"
    BEIJING = "beijing"


class AuctionFeatureMode(str, Enum):
    REAL_AUCTION_SERIES = "real_auction_series"
    AUCTION_PROXY = "auction_proxy"


class ExperimentID(str, Enum):
    EXP_A_BASELINE = "EXP_A_BASELINE"
    EXP_B_FORMAL_ONLY = "EXP_B_FORMAL_ONLY"
    EXP_C_MAINLINE = "EXP_C_MAINLINE"
    EXP_D_LEADER = "EXP_D_LEADER"
    EXP_E_MAINLINE_LEADER = "EXP_E_MAINLINE_LEADER"
    EXP_F_CONFIRMED_AB = "EXP_F_CONFIRMED_AB"


# ── Experiment condition definitions ──

EXPERIMENT_GROUPS: dict[str, dict[str, Any]] = {
    ExperimentID.EXP_A_BASELINE.value: {
        "label": "全量基准",
        "conditions": {"pool_entry_type": ("formal", "observe_only")},
    },
    ExperimentID.EXP_B_FORMAL_ONLY.value: {
        "label": "仅formal候选",
        "conditions": {"pool_entry_type": ("formal",)},
    },
    ExperimentID.EXP_C_MAINLINE.value: {
        "label": "主线过滤",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
        },
    },
    ExperimentID.EXP_D_LEADER.value: {
        "label": "龙头过滤",
        "conditions": {
            "pool_entry_type": ("formal",),
            "leader_role_proxy": ("leader", "card"),
        },
    },
    ExperimentID.EXP_E_MAINLINE_LEADER.value: {
        "label": "主线+龙头",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
            "leader_role_proxy": ("leader", "card"),
        },
    },
    ExperimentID.EXP_F_CONFIRMED_AB.value: {
        "label": "主线+龙头+A/B确认",
        "conditions": {
            "pool_entry_type": ("formal",),
            "mainline_strength_score_min": 60,
            "fade_confirmed": False,
            "leader_role_proxy": ("leader", "card"),
            "confirm_level": ("A", "B"),
        },
    },
}

VISIBLE_EXPERIMENTS = [
    ExperimentID.EXP_A_BASELINE.value,
    ExperimentID.EXP_C_MAINLINE.value,
    ExperimentID.EXP_E_MAINLINE_LEADER.value,
]

CONFIRM_SOURCE_LABELS: dict[str, str] = {
    "real_auction": "真实竞价分时",
    "auction_snapshot": "竞价快照(无分时序列)",
    "daily_open_proxy": "日K代理",
    "missing": "无数据",
}
