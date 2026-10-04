"""Source-aware acceptance policy for canonical event resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable

from ..contracts import MarketAcceptanceStatus


class EventRowAcceptance(str, Enum):
    ACCEPTED = MarketAcceptanceStatus.ACCEPTED.value
    PRESENT_UNVERIFIED = MarketAcceptanceStatus.PRESENT_UNVERIFIED.value
    INVALID = MarketAcceptanceStatus.INVALID.value


@dataclass(frozen=True)
class OperationalWindow:
    start: date | None = None
    end: date | None = None

    def contains(self, value: date) -> bool:
        return (self.start is None or value >= self.start) and (
            self.end is None or value <= self.end
        )


class EventAcceptancePolicy:
    """Evaluate rows without treating persistence as proof of fact.

    With no configured windows, dates are considered eligible.  Callers that
    have an authoritative operational timeline should inject explicit windows;
    the reader must not infer an outage from an empty result.
    """

    def __init__(self, active_windows: Iterable[OperationalWindow] | None = None):
        self._active_windows = tuple(active_windows or ())

    def is_operational(self, trade_date: date) -> bool:
        if not self._active_windows:
            return True
        return any(window.contains(trade_date) for window in self._active_windows)

    @staticmethod
    def classify_row(row: dict) -> EventRowAcceptance:
        if not row.get("event_id") or not str(row.get("subject_key") or "").strip():
            return EventRowAcceptance.INVALID
        source = str(row.get("source_category") or row.get("source") or "").strip()
        if source == "news":
            if not row.get("news_raw_id") or not row.get("source_trace_id"):
                return EventRowAcceptance.PRESENT_UNVERIFIED
            return EventRowAcceptance.ACCEPTED
        if source in {"jyhf_dom", "jyhf_cdp"}:
            if not row.get("jyhf_provenance") or not row.get("jyhf_ingest_at"):
                return EventRowAcceptance.PRESENT_UNVERIFIED
            return EventRowAcceptance.ACCEPTED
        return EventRowAcceptance.PRESENT_UNVERIFIED

    def classify(self, trade_date: date, rows: list[dict]) -> MarketAcceptanceStatus:
        if not self.is_operational(trade_date):
            return MarketAcceptanceStatus.CASE_INELIGIBLE
        if not rows:
            return MarketAcceptanceStatus.EMPTY
        states = {self.classify_row(row) for row in rows}
        if EventRowAcceptance.INVALID in states:
            return MarketAcceptanceStatus.INVALID
        if EventRowAcceptance.PRESENT_UNVERIFIED in states:
            return MarketAcceptanceStatus.PRESENT_UNVERIFIED
        return MarketAcceptanceStatus.ACCEPTED
