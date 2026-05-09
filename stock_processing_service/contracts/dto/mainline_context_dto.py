from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MainlineIdentityDTO:
    subject_key: str
    identity_status: str
    is_main_theme: bool
    theme_name: str = ""
    first_confirmed_date: date | None = None
    last_review_date: date | None = None
    rule_version: str = ""
    composite_score: float = 0.0


@dataclass(frozen=True)
class MainlineCycleDTO:
    trade_date: date
    subject_key: str
    final_cycle_state: str
    final_mainline_alive: bool
    theme_name: str = ""
    transition_type: str = ""
    transition_confidence: Decimal = Decimal("0")
    trigger_flags: list[str] = field(default_factory=list)
    mainline_strength_score: Decimal = Decimal("0")
    repair_score: Decimal = Decimal("0")
    divergence_score: Decimal = Decimal("0")
    fade_watch_score: Decimal = Decimal("0")
    fade_confirmed_score: Decimal = Decimal("0")
    fade_watch: bool = False
    fade_confirmed: bool = False
