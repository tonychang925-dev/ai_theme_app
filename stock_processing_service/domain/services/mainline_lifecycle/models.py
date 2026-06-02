"""PR-10: Mainline Lifecycle data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MainlineLifecycleReview:
    """Lifecycle state for a confirmed mainline, derived from Layer B."""

    trade_date: str = ""
    mainline_id: str = ""
    mainline_name: str = ""
    canonical_subject_key: str = ""
    related_subject_keys: list[str] = field(default_factory=list)

    lifecycle_state: str = "unknown"
    mainline_alive: bool = False
    mainline_trade_alive: bool = False
    risk_state: str = "unknown"

    mainline_strength_score: float | None = None
    fade_risk_score: float | None = None
    fade_watch_score: float | None = None
    fade_confirmed_score: float | None = None
    support_break: bool = False
    fade_reason_codes: list[str] = field(default_factory=list)

    lifecycle_source: str = "theme_cycle_judgement_v2"
    source_subject_key: str = ""

    related_subject_states: list[dict[str, Any]] = field(default_factory=list)

    playability: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mainline_id": self.mainline_id,
            "mainline_name": self.mainline_name,
            "canonical_subject_key": self.canonical_subject_key,
            "related_subject_keys": self.related_subject_keys,
            "lifecycle_state": self.lifecycle_state,
            "mainline_alive": self.mainline_alive,
            "mainline_trade_alive": self.mainline_trade_alive,
            "risk_state": self.risk_state,
            "mainline_strength_score": self.mainline_strength_score,
            "fade_risk_score": self.fade_risk_score,
            "fade_watch_score": self.fade_watch_score,
            "fade_confirmed_score": self.fade_confirmed_score,
            "support_break": self.support_break,
            "fade_reason_codes": self.fade_reason_codes,
            "lifecycle_source": self.lifecycle_source,
            "source_subject_key": self.source_subject_key,
            "related_subject_states": self.related_subject_states,
            "playability": self.playability,
            "diagnostics": self.diagnostics,
        }


@dataclass
class MainlineLifecycleFactContext:
    """Context built from mainline_registry + Layer B data."""

    trade_date: str = ""
    confirmed_mainlines: list[dict[str, Any]] = field(default_factory=list)
    cycle_judgement_by_sk: dict[str, dict[str, Any]] = field(default_factory=dict)
    cycle_evidence_by_sk: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "confirmed_mainlines": self.confirmed_mainlines,
            "cycle_judgement_by_sk": self.cycle_judgement_by_sk,
            "cycle_evidence_by_sk": self.cycle_evidence_by_sk,
            "diagnostics": self.diagnostics,
        }
