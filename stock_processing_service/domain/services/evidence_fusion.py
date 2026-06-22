"""M4c: Stock Theme Evidence Fusion Engine.

Fuses THS reason, CNInfo announcement, Eastmoney blocks, and JYHF
subject_stock_map into unified stock_theme_evidence scores.

Design doc §M4c: Stock Theme Evidence Fusion
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

# ── Source weights ──────────────────────────────────────────────

SOURCE_WEIGHTS = {
    "ths": 1.00,          # THS hot reason — highest signal
    "cninfo": 0.80,       # CNInfo announcement — event-driven
    "eps": 0.70,          # THS EPS forecast — expectation-driven
    "research": 0.55,     # Research report metadata — institutional view
    "eastmoney": 0.45,    # Eastmoney concept block — structural
    "jyhf": 0.35,         # JYHF subject_stock_map — static fallback
}

# Multi-source resonance bonus
RESONANCE_BONUS: dict[int, float] = {
    2: 0.20,
    3: 0.30,
    4: 0.40,
    5: 0.50,
    6: 0.55,
}

# Daily decay rate (exponential)
DAILY_DECAY = 0.90  # evidence loses 10% relevance per day

# CNInfo: only count if within this many days
CNINFO_MAX_AGE_DAYS = 3

# Research: only count reports within this many days
RESEARCH_MAX_AGE_DAYS = 30

# Research: cap per-theme contribution to prevent over-weighting
RESEARCH_MAX_CONTRIBUTION = 0.30  # max research contribution to total score

MAX_SCORE = 2.00  # cap fused score


# ── Data types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of evidence from one source."""

    source_name: str          # ths | cninfo | eastmoney | jyhf
    theme_name: str
    stock_code: str
    stock_name: str
    evidence_date: date
    reason: str = ""          # human-readable reason text
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FusedStockTheme:
    """Fused evidence for one stock-theme pair."""

    trade_date: date
    stock_code: str
    stock_name: str
    theme_name: str
    evidence_score: float         # 0.0 — MAX_SCORE (composite)
    event_score: float = 0.0      # event-driven component (ths+cninfo+eastmoney+jyhf)
    expectation_score: float = 0.0  # expectation-driven component (eps)
    evidence_sources: list[str] = field(default_factory=list)
    source_count: int = 0
    freshness_score: float = 0.0
    confidence: float = 0.0
    primary_reason: str = ""
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    is_resonance: bool = False


# ── Fusion Engine ───────────────────────────────────────────────


class EvidenceFusionEngine:
    """Fuses evidence from multiple sources into unified scores."""

    def fuse(
        self,
        trade_date: date,
        evidence_items: list[EvidenceItem],
    ) -> list[FusedStockTheme]:
        """Fuse evidence items into per-stock-theme scores.

        Groups by (stock_code, theme_name), scores each group,
        and returns sorted by evidence_score descending.
        """
        # Group by (stock_code, theme_name)
        groups: dict[tuple[str, str], list[EvidenceItem]] = {}
        for ev in evidence_items:
            key = (ev.stock_code, ev.theme_name)
            groups.setdefault(key, []).append(ev)

        results: list[FusedStockTheme] = []
        for (stock_code, theme_name), items in groups.items():
            fused = self._fuse_group(trade_date, stock_code, theme_name, items)
            if fused.evidence_score > 0:
                results.append(fused)

        results.sort(key=lambda x: -x.evidence_score)
        return results

    def _fuse_group(
        self,
        trade_date: date,
        stock_code: str,
        theme_name: str,
        items: list[EvidenceItem],
    ) -> FusedStockTheme:
        """Score a single stock-theme group."""
        sources: set[str] = set()
        total_weight = 0.0
        event_weight = 0.0
        expectation_weight = 0.0
        total_confidence = 0.0
        best_reason = ""
        best_priority = 999

        source_priority = {"ths": 0, "eps": 0, "cninfo": 1, "eastmoney": 2, "jyhf": 3}
        event_sources = {"ths", "cninfo", "research", "eastmoney", "jyhf"}
        supporting: list[dict[str, Any]] = []

        for ev in items:
            weight = SOURCE_WEIGHTS.get(ev.source_name, 0.30)
            days_old = (trade_date - ev.evidence_date).days

            # Apply source-specific age checks
            if ev.source_name == "cninfo" and days_old > CNINFO_MAX_AGE_DAYS:
                continue
            if ev.source_name == "research" and days_old > RESEARCH_MAX_AGE_DAYS:
                continue

            # Apply decay
            if days_old > 0:
                weight *= DAILY_DECAY ** days_old

            sources.add(ev.source_name)
            total_weight += weight

            # Split: event vs expectation
            if ev.source_name in event_sources:
                event_weight += weight
            if ev.source_name == "eps":
                expectation_weight += weight

            total_confidence = max(total_confidence, ev.confidence)

            pri = source_priority.get(ev.source_name, 99)
            if ev.reason and pri < best_priority:
                best_priority = pri
                best_reason = ev.reason

            supporting.append({
                "source": ev.source_name,
                "reason": ev.reason,
                "date": ev.evidence_date.isoformat(),
                "weight": round(weight, 3),
                "tags": ev.tags,
            })

        n_sources = len(sources)
        bonus = RESONANCE_BONUS.get(n_sources, 0)
        if n_sources > max(RESONANCE_BONUS.keys()):
            bonus = RESONANCE_BONUS[max(RESONANCE_BONUS.keys())]

        # Research contribution cap: prevent institutional coverage from
        # over-weighting themes relative to event-driven evidence.
        research_contrib = sum(
            s["weight"] for s in supporting
            if s["source"] == "research"
        )
        capped_research = min(research_contrib, RESEARCH_MAX_CONTRIBUTION)
        capped_total = total_weight - research_contrib + capped_research

        score = min(capped_total + bonus, MAX_SCORE)
        freshness = 1.0 if min(
            (trade_date - ev.evidence_date).days for ev in items
        ) <= 1 else max(0.3, 1.0 - 0.1 * max(
            (trade_date - ev.evidence_date).days for ev in items
        ))

        return FusedStockTheme(
            trade_date=trade_date,
            stock_code=stock_code,
            stock_name=items[0].stock_name,
            theme_name=theme_name,
            evidence_score=round(score, 3),
            event_score=round(min(event_weight + (bonus if n_sources >= 2 else 0), MAX_SCORE), 3),
            expectation_score=round(min(expectation_weight, 1.0), 3),
            evidence_sources=sorted(sources),
            source_count=n_sources,
            freshness_score=round(freshness, 2),
            confidence=round(total_confidence, 2),
            primary_reason=best_reason or theme_name,
            supporting_evidence=supporting,
            is_resonance=n_sources >= 2,
        )
