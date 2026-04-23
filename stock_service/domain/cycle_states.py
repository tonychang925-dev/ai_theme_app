from __future__ import annotations

from typing import Final, Set

CYCLE_STATE_START: Final[str] = "start"
CYCLE_STATE_FERMENTATION: Final[str] = "fermentation"
CYCLE_STATE_ACCELERATION: Final[str] = "acceleration"
CYCLE_STATE_DIVERGENCE: Final[str] = "divergence"
CYCLE_STATE_REPAIR: Final[str] = "repair"
CYCLE_STATE_FADE_WATCH: Final[str] = "fade_watch"
CYCLE_STATE_FADE_CONFIRMED: Final[str] = "fade_confirmed"

CYCLE_STATES: Final[Set[str]] = {
    CYCLE_STATE_START,
    CYCLE_STATE_FERMENTATION,
    CYCLE_STATE_ACCELERATION,
    CYCLE_STATE_DIVERGENCE,
    CYCLE_STATE_REPAIR,
    CYCLE_STATE_FADE_WATCH,
    CYCLE_STATE_FADE_CONFIRMED,
}
