"""AnalystReviewQueueBuilder — Phase 1 PR-6.

Converts PR-5 machine candidates into a human-review priority queue.

Entry rules:
  Must review: fast_candidate, slow_candidate, high market_noise,
               high logic_only, grey zone
  Skip: rejected, low rotation, blocking veto without major event

Review priority = max(fast/slow/hybrid/market) + bonus - penalty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import AnalystReviewItem, AnalystReviewQueueDiagnostics, MainlineDiscoveryDecision


@dataclass
class AnalystReviewQueueBuilder:
    """Build a priority-sorted review queue from machine candidate decisions."""

    # ── thresholds ──
    grey_logic_lower: float = 60.0
    grey_logic_upper: float = 75.0
    grey_market_lower: float = 55.0
    grey_market_upper: float = 70.0
    grey_narrative_confidence_max: float = 0.75
    grey_max_items: int = 15

    def build(
        self,
        *,
        decisions: list[MainlineDiscoveryDecision],
        trade_date: str = "",
        event_evidence_by_subject: dict[str, dict[str, Any]] | None = None,
        narrative_by_subject: dict[str, dict[str, Any]] | None = None,
        market_by_subject: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[AnalystReviewItem], AnalystReviewQueueDiagnostics]:
        event_ev = event_evidence_by_subject or {}
        narr_map = narrative_by_subject or {}
        market_map = market_by_subject or {}

        diag = AnalystReviewQueueDiagnostics(total_candidates=len(decisions))
        items: list[AnalystReviewItem] = []

        for d in decisions:
            diag_cat = self._categorize(d)
            if diag_cat is None:
                diag.rejected_count += 1
                continue

            item = self._to_item(d, trade_date, event_ev.get(d.subject_key, {}),
                                 narr_map.get(d.subject_key, {}),
                                 market_map.get(d.subject_key, {}))
            items.append(item)
            self._update_counts(diag, diag_cat)

        # ── sort by priority desc ──
        items.sort(key=lambda x: x.review_priority, reverse=True)
        diag.queue_total = len(items)
        if items:
            diag.max_priority = items[0].review_priority
            diag.min_priority = items[-1].review_priority

        return items, diag

    def _categorize(self, d: MainlineDiscoveryDecision) -> str | None:
        """Return category string or None if rejected."""
        ms = d.machine_state
        market = d.market_acceptance_score or 0
        hybrid = d.hybrid_logic_score or 0
        major_score = d.major_event_score or 0
        narrative_conf = 1.0
        if self._has_blocking(d):
            return None  # rejected

        # ── must review ──
        if ms == "machine_fast_candidate":
            return "fast_line"
        if ms == "machine_slow_candidate":
            return "slow_line"

        # ── high market noise ──
        if ms == "market_noise" and market >= 75:
            return "high_market_noise"

        # ── high logic only ──
        if ms == "logic_only" and hybrid >= 80:
            return "high_logic_only"

        # ── grey zone (limited) ──
        if (self.grey_logic_lower <= hybrid <= self.grey_logic_upper
                or self.grey_market_lower <= market <= self.grey_market_upper
                or narrative_conf < self.grey_narrative_confidence_max):
            if hybrid >= 60 or market >= 60:
                return "grey_zone"

        return None

    def _to_item(
        self,
        d: MainlineDiscoveryDecision,
        trade_date: str,
        event_ev: dict[str, Any],
        narrative: dict[str, Any],
        market: dict[str, Any],
    ) -> AnalystReviewItem:
        td = trade_date or d.trade_date
        mid = f"ml_{d.subject_key}_{td.replace('-','')}" if td else f"ml_{d.subject_key}"

        # ── priority ──
        priority = max(
            d.fast_line_score or 0, d.slow_line_score or 0,
            d.hybrid_logic_score or 0, d.market_acceptance_score or 0,
        )
        if d.machine_state == "machine_fast_candidate":
            priority += 10
        elif d.machine_state == "machine_slow_candidate":
            priority += 8
        if (d.major_event_score or 0) >= 90:
            priority += 5
        if (d.market_acceptance_score or 0) >= 75:
            priority += 5
        if d.confirmation_veto_flags:
            priority -= len(d.confirmation_veto_flags) * 5

        return AnalystReviewItem(
            review_id=f"ml_review_{td}_{d.subject_key}_{d.machine_state}" if td else f"ml_review_{d.subject_key}_{d.machine_state}",
            trade_date=td,
            subject_key=d.subject_key,
            theme_name=d.theme_name,
            mainline_id=mid,
            mainline_name=d.theme_name,
            machine_state=d.machine_state,
            final_mainline_state="pending_review",
            mainline_type=d.mainline_type,
            confirmation_path=d.confirmation_path,
            trigger_mode=d.trigger_mode,
            review_reason=d.review_reason,
            review_priority=round(priority, 1),
            review_status="pending",
            suggested_human_decision=d.suggested_human_decision,
            scores={
                "rule_logic_score": d.rule_logic_score,
                "llm_narrative_score": d.llm_narrative_score,
                "hybrid_logic_score": d.hybrid_logic_score,
                "market_acceptance_score": d.market_acceptance_score,
                "major_event_score": d.major_event_score,
                "fast_line_score": d.fast_line_score,
                "slow_line_score": d.slow_line_score,
            },
            evidence={
                "event_chain": event_ev.get("event_chain", []) if isinstance(event_ev, dict) else [],
                "event_series": event_ev.get("event_series", []) if isinstance(event_ev, dict) else [],
                "major_event": {},
                "narrative_judge": narrative,
                "market_evidence": market.get("market_evidence", {}) if isinstance(market, dict) else {},
                "leader_evidence": {},
            },
            risk_flags={
                "blocking_veto_flags": d.blocking_veto_flags,
                "confirmation_veto_flags": d.confirmation_veto_flags,
            },
            human_decision=None,
            human_reviewer=None,
            human_notes=None,
            reviewed_at=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            diagnostics={
                "source": "mainline_discovery_engine.v1",
                "decision_path": d.diagnostics.get("decision_path", ""),
            },
        )

    @staticmethod
    def _has_blocking(d: MainlineDiscoveryDecision) -> bool:
        return bool(d.blocking_veto_flags) and d.machine_state not in {"machine_fast_candidate", "machine_slow_candidate"}

    @staticmethod
    def _update_counts(diag: AnalystReviewQueueDiagnostics, category: str) -> None:
        if category == "fast_line":
            diag.fast_line_count += 1
        elif category == "slow_line":
            diag.slow_line_count += 1
        elif category == "high_market_noise":
            diag.high_market_noise_count += 1
        elif category == "high_logic_only":
            diag.high_logic_only_count += 1
        elif category == "grey_zone":
            diag.grey_zone_count += 1
        # rejected already counted in build()
