"""P2.1 — MarketAttentionState contracts.

Attention Engine domain model. Deterministic, no LLM.
Does NOT modify M8 DailyMarketState.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


# ── SubjectAttention ──


@dataclass(frozen=True, slots=True)
class SubjectAttention:
    """One subject's attention assessment for a trading day."""

    subject_id: str
    subject_name: str
    subject_type: str = "theme"

    attention_score: int = 50       # 0-100
    level: str = "MEDIUM"           # CRITICAL / HIGH / MEDIUM / LOW / IGNORE

    # ── 5 signal dimensions ──
    event_signals: int = 0          # 0-100: news/event stimulus strength
    price_signals: int = 0          # 0-100: leader limit-up/abnormal move
    capital_signals: int = 0        # 0-100: capital flow signals
    external_signals: int = 0       # 0-100: KOSPI/US/commodity mapping
    sentiment_signals: int = 0      # 0-100: market sentiment resonance

    # ── Display ──
    reasons: tuple[str, ...] = ()   # max 3 reasons for attention
    evidence_refs: tuple[str, ...] = ()  # linked evidence IDs

    # ── Analyst override ──
    ai_level: str = "MEDIUM"        # original AI-assigned level
    analyst_level: str | None = None  # analyst overridden level
    is_analyst_modified: bool = False


# ── ExternalAnchor ──


@dataclass(frozen=True, slots=True)
class ExternalAnchor:
    """External market anchor affecting attention."""
    anchor_id: str                  # KOSPI / NASDAQ / SOX / USDCNY / ...
    anchor_name: str
    direction: str                  # bullish / bearish / neutral
    strength: int                   # 0-100
    mapped_subjects: tuple[str, ...]  # which subjects this anchor maps to
    note: str = ""


# ── MarketAttentionState ──


@dataclass
class MarketAttentionState:
    """Daily attention allocation state."""

    trade_date: date
    generated_at: datetime | None = None

    # ── Attention allocation ──
    subjects: list[SubjectAttention] = field(default_factory=list)
    external_anchors: list[ExternalAnchor] = field(default_factory=list)
    ignored_subjects: list[str] = field(default_factory=list)

    # ── Analyst adjustments ──
    override_count: int = 0
    analyst_reviewed: bool = False

    # ── Budget ──
    total_budget: int = 100
    allocated_budget: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "subjects": [
                {
                    "subject_id": s.subject_id,
                    "subject_name": s.subject_name,
                    "attention_score": s.attention_score,
                    "level": s.analyst_level or s.level,
                    "ai_level": s.ai_level,
                    "event_signals": s.event_signals,
                    "price_signals": s.price_signals,
                    "capital_signals": s.capital_signals,
                    "external_signals": s.external_signals,
                    "sentiment_signals": s.sentiment_signals,
                    "reasons": list(s.reasons),
                    "evidence_refs": list(s.evidence_refs),
                    "is_analyst_modified": s.is_analyst_modified,
                }
                for s in self.subjects
            ],
            "external_anchors": [
                {
                    "anchor_id": a.anchor_id,
                    "anchor_name": a.anchor_name,
                    "direction": a.direction,
                    "strength": a.strength,
                    "mapped_subjects": list(a.mapped_subjects),
                    "note": a.note,
                }
                for a in self.external_anchors
            ],
            "ignored_subjects": self.ignored_subjects,
            "override_count": self.override_count,
            "analyst_reviewed": self.analyst_reviewed,
            "total_budget": self.total_budget,
            "allocated_budget": self.allocated_budget,
        }


# ── OverrideLog ──


@dataclass(frozen=True, slots=True)
class AttentionOverride:
    """A single analyst adjustment to attention state."""
    trade_date: date
    subject_id: str
    field_name: str                # "level" | "ignored" | "added"
    ai_value: str
    analyst_value: str
    override_reason: str = ""
    analyst_id: str = "analyst"
    created_at: datetime | None = None
