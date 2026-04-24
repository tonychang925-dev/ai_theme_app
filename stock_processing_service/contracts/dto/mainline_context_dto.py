from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MainlineIdentityDTO:
    subject_key: str
    identity_status: str
    is_main_theme: bool
    first_confirmed_date: date | None = None
    last_review_date: date | None = None
    rule_version: str = ""


@dataclass(frozen=True)
class MainlineCycleDTO:
    trade_date: date
    subject_key: str
    final_cycle_state: str
    final_mainline_alive: bool
    transition_type: str = ""
    mainline_strength_score: Decimal = Decimal("0")
    repair_score: Decimal = Decimal("0")
    divergence_score: Decimal = Decimal("0")
    fade_watch_score: Decimal = Decimal("0")
    fade_confirmed_score: Decimal = Decimal("0")
