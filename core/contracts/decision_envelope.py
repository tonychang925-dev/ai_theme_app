"""DecisionEnvelope v1.1 — Frozen Contract.

The shared language between ai_theme_app (Market Brain) and Julia Core (Cognitive Companion).

ai_theme_app owns: facts, evidence, signals, causal_chain, quantitative models.
Julia Core owns: interpretation, reasoning, companionship.

This contract is the neural interface. Never the other way around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

CST = timezone(timedelta(hours=8))


# ── Alert Levels ──

class AlertLevel:
    NOISE = "noise"
    OBSERVATION = "observation"
    WATCH = "watch"
    ALERT = "alert"
    DECISION = "decision"

    RANK: dict[str, int] = {
        NOISE: 0,
        OBSERVATION: 1,
        WATCH: 2,
        ALERT: 3,
        DECISION: 4,
    }


# ── Lifecycle States ──

class Lifecycle:
    START = "START"
    DIFFUSION = "DIFFUSION"
    CONSOLIDATION = "CONSOLIDATION"
    DECLINE = "DECLINE"


# ── v1.1 Contracts ──

@dataclass(frozen=True, slots=True)
class Evidence:
    """Source-traceable evidence item."""
    type: str        # "news" | "market_data" | "capital_flow" | "auction"
    text: str        # Human-readable evidence description
    source: str = ""  # data origin identifier
    ref_id: str = ""  # traceable reference (news ID, ticker, etc.)
    authority: float = 0.5  # 0.0-1.0, source reliability


@dataclass(frozen=True, slots=True)
class CausalLink:
    """One link in the causal chain: cause → effect → market response."""
    cause: str
    effect: str
    market_response: str
    confidence: float = 0.5  # 0.0-1.0


@dataclass(frozen=True, slots=True)
class ThemeContext:
    """Where this theme currently sits in its lifecycle."""
    theme_id: str
    lifecycle: str                    # Lifecycle.START / DIFFUSION / CONSOLIDATION / DECLINE
    previous_state: str = ""          # last observed state
    change: str = ""                  # "heat increasing" | "heat decreasing" | "stable"
    first_signal_date: str = ""       # YYYY-MM-DD
    days_active: int = 0


@dataclass(frozen=True, slots=True)
class DecisionEnvelope:
    """The frozen market cognition output — the neural interface between Market Brain and Julia.

    ai_theme_app writes these. Julia reads them. Never the other way around.
    """
    id: str = field(default_factory=lambda: f"dec_{uuid4().hex}")
    timestamp: str = field(default_factory=lambda: datetime.now(CST).isoformat())
    source: str = ""                  # "news" | "market" | "signal" | "alert"
    type: str = ""                    # "event_news" | "theme_match" | "support_alert" | ...
    level: str = AlertLevel.OBSERVATION

    evidence: tuple[Evidence, ...] = ()
    causal_chain: tuple[CausalLink, ...] = ()
    theme_context: ThemeContext | None = None
    prediction_id: str | None = None

    confidence: float = 0.0           # 0.0-1.0
    impact: str = "unknown"           # "positive" | "negative" | "neutral" | "unknown"
    expiry: str | None = None         # ISO 8601, when this signal becomes stale
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.level not in AlertLevel.RANK:
            raise ValueError(f"Unknown alert level: {self.level}")

    @property
    def is_active(self) -> bool:
        """Has this signal expired?"""
        if self.expiry is None:
            return True
        now = datetime.now(CST)
        try:
            expire_dt = datetime.fromisoformat(self.expiry)
            return now < expire_dt
        except (ValueError, TypeError):
            return True

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.75


@dataclass(frozen=True, slots=True)
class ThemeStatusSnapshot:
    """Returned by query_theme_status()."""
    theme: str
    lifecycle: str
    heat_score: int
    leaders: tuple[str, ...]
    money_flow: str
    causal_chain: tuple[CausalLink, ...] = ()
    risk: str = "unknown"
    last_updated: str = field(default_factory=lambda: datetime.now(CST).isoformat())


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Returned by review_market_snapshot()."""
    market_sentiment: str             # "偏强" | "偏弱" | "中性"
    active_themes: tuple[str, ...]
    top_signals: tuple[DecisionEnvelope, ...]
    risk_alerts: tuple[str, ...]
    date: str = field(default_factory=lambda: datetime.now(CST).strftime("%Y-%m-%d"))


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    """Returned by explain_decision()."""
    decision_id: str
    summary: str
    causal_chain: tuple[CausalLink, ...]
    supporting_evidence: int          # count of supporting items
    opposing_evidence: int            # count of opposing items
    confidence: float
    risk_factors: tuple[str, ...]
    alternatives: tuple[str, ...]     # alternative interpretations


@dataclass(frozen=True, slots=True)
class ChannelState:
    """Returned by subscribe_agent_channel()."""
    subscribed: tuple[str, ...]
    active: bool
    updated_at: str = field(default_factory=lambda: datetime.now(CST).isoformat())
