from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SupportTypeScore:
    support_type: str
    support_level: Decimal
    strength: Decimal
    source: str
    distance_pct: Decimal
    zone_lower: Decimal = Decimal("0")
    zone_upper: Decimal = Decimal("0")
    hit_mode: str = "miss"


@dataclass(frozen=True)
class SupportScoreResult:
    support_type: str
    support_level: Decimal
    support_score: Decimal
    support_count: int = 0
    combined_strength: Decimal = Decimal("0")
    gap_hit: bool = False
    gap_hit_mode: str = "miss"
    gap_source: str = ""
    gap_level: Decimal = Decimal("0")
    gap_distance_pct: Decimal = Decimal("999")
    support_refs: list[str] = field(default_factory=list)
    support_types: list[SupportTypeScore] = field(default_factory=list)


@dataclass(frozen=True)
class GapStructure:
    gap_id: str
    gap_from_date: date
    gap_to_date: date
    age_days: int
    gap_lower: Decimal
    gap_upper: Decimal
    gap_size_pct: Decimal
    gap_type: str
    fill_ratio: Decimal
    is_filled: bool
    current_distance_pct: Decimal
    strict_hit: bool
    soft_hit: bool
    near_ma: bool = False
    near_prev_low: bool = False
    resonance_score: Decimal = Decimal("0")
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreviousLowStructure:
    level: Decimal
    distance_pct: Decimal
    is_valid: bool
    source: str = "previous_low"


@dataclass(frozen=True)
class MAStructure:
    level: Decimal
    ma_type: str
    distance_pct: Decimal
    is_valid: bool
    source: str = "ma_support"


@dataclass(frozen=True)
class ResolvedSupport:
    support_type: str
    support_level: Decimal
    support_score: Decimal
    support_refs: list[str]
    primary_reason: str
    gap_hit: bool = False
    gap_source: str = ""
    gap_hit_mode: str = "miss"
    gap_level: Decimal = Decimal("0")
    gap_distance_pct: Decimal = Decimal("999")

