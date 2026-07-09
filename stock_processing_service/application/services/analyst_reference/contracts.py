"""Phase 4.1 — Analyst Reference Contracts.

Defines the structured format for analyst ground truth data,
enabling AI↔Analyst comparison, calibration, and replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class MarketFacts:
    """L0: Analyst-reported market facts."""
    limit_up_count: int | None = None
    chain_board_count: int | None = None
    max_board_height: int | None = None
    active_capital_yi: float | None = None      # 活跃资金（亿元）
    market_up_ratio: float | None = None         # 上涨比 (0-1)
    loss_effect_ratio: float | None = None       # 亏钱效应比
    composite_score: int | None = None           # 综合评分 (-10 to +10)
    down_below_minus5: int | None = None         # -5%以下个股数

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmotionLabel:
    """L1: Analyst emotion/phase assessment."""
    market_phase: str = ""                       # PANIC / FREEZE / REPAIR_WATCH / etc.
    risk_level: str = ""                         # LOW / MEDIUM / HIGH / CRITICAL
    emotion_momentum: float | None = None        # -18 ~ +10
    cycle_score: int | None = None               # running cycle score
    strategy: str = ""                           # analyst's strategy description

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelayLabel:
    """L1: Analyst relay ecology data."""
    max_board_height: int | None = None
    max_board_stock: str = ""
    first_board_success_rate: float | None = None  # 首板封板率
    promotion_1_to_2: float | None = None
    promotion_2_to_3: float | None = None
    promotion_3_to_4: float | None = None
    promotion_4_to_5: float | None = None
    promotion_5_to_6: float | None = None
    promotion_6_to_7: float | None = None

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThemeLifecycleEntry:
    """One theme's lifecycle state on a given date."""
    theme_name: str
    state: str                                   # 启动/调整/修复/观察/关注
    day_count: int = 0                           # 当前状态持续天数
    notes: str = ""


@dataclass
class LimitUpAttribution:
    """Limit-up stock classification by theme."""
    theme_name: str
    board_heights: list[int] = field(default_factory=list)
    stock_count: int = 0
    key_stocks: list[dict] = field(default_factory=list)  # [{code, name, board, reason}]

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaderState:
    """Leader/high-board stock state."""
    stock_code: str
    stock_name: str
    board_height: int
    role: str = ""                               # 龙头 / 中军 / 补涨 / 穿越
    theme: str = ""


@dataclass
class StrategyLabel:
    """L3: Analyst strategy recommendations."""
    allowed: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    watch_points: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ExternalEnvironment:
    """L6: External market context (future)."""
    korea_index: dict[str, Any] = field(default_factory=dict)
    us_market: dict[str, Any] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)


@dataclass
class AnalystReferenceRecord:
    """Complete analyst ground truth for one trading day.

    This is the canonical format for analyst data ingestion.
    All fields that cannot be automatically extracted are marked.
    """
    trade_date: date
    source_type: str                             # pdf / markdown / manual / notion
    source_path: str = ""

    # Structured layers
    market_facts: MarketFacts = field(default_factory=MarketFacts)
    emotion_label: EmotionLabel = field(default_factory=EmotionLabel)
    relay_label: RelayLabel = field(default_factory=RelayLabel)
    theme_lifecycle: list[ThemeLifecycleEntry] = field(default_factory=list)
    limitup_attribution: list[LimitUpAttribution] = field(default_factory=list)
    leader_state: list[LeaderState] = field(default_factory=list)
    strategy_label: StrategyLabel = field(default_factory=StrategyLabel)
    external_env: ExternalEnvironment = field(default_factory=ExternalEnvironment)

    # Meta
    confidence: float = 1.0                      # extraction confidence
    extraction_status: str = ""                  # complete / partial / needs_review
    needs_review_fields: list[str] = field(default_factory=list)
    raw_text: str = ""                           # original analyst text for reference
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_db_dict(self) -> dict[str, Any]:
        import json
        return {
            "trade_date": self.trade_date,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "market_facts": json.dumps(self.market_facts.__dict__, default=str),
            "emotion_label": json.dumps(self.emotion_label.__dict__, default=str),
            "relay_label": json.dumps(self.relay_label.__dict__, default=str),
            "theme_lifecycle": json.dumps([t.__dict__ for t in self.theme_lifecycle], default=str),
            "limitup_attribution": json.dumps([a.__dict__ for a in self.limitup_attribution], default=str),
            "leader_state": json.dumps([l.__dict__ for l in self.leader_state], default=str),
            "strategy_label": json.dumps(self.strategy_label.__dict__, default=str),
            "extraction_status": self.extraction_status,
            "needs_review_fields": self.needs_review_fields,
            "confidence": self.confidence,
            "raw_text": self.raw_text[:5000] if self.raw_text else "",
        }
