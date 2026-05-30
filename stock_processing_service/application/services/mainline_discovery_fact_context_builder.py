"""MainlineDiscoveryFactContextBuilder — Phase 1 application-level service.

Actively builds MainlineDiscoveryFactContext from real data sources
(read_port calls, not report_context). This is the authoritative fact
input for MainlineLogicChainBuilder and MainlineMarketAcceptanceBuilder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from stock_processing_service.domain.services.mainline_identity_universe_builder import (
    MainlineIdentityUniverseBuilder,
)

logger = logging.getLogger(__name__)


@dataclass
class MainlineDiscoveryFactContext:
    """Structured fact input for mainline discovery engines.

    All fields are populated actively from read_port, not passively
    from report_context.
    """
    trade_date: str = ""
    lookback_days: int = 7

    candidate_subjects: list[dict[str, Any]] = field(default_factory=list)

    event_rows_by_subject: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    event_stats_by_subject: dict[str, dict[str, Any]] = field(default_factory=dict)
    rank_history_by_subject: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    cycle_evidence_by_subject: dict[str, dict[str, Any]] = field(default_factory=dict)
    cycle_judgement_by_subject: dict[str, dict[str, Any]] = field(default_factory=dict)
    capital_by_subject: dict[str, dict[str, Any]] = field(default_factory=dict)
    stock_facts_by_subject: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "lookback_days": self.lookback_days,
            "candidate_subjects": self.candidate_subjects,
            "event_rows_by_subject": self.event_rows_by_subject,
            "event_stats_by_subject": self.event_stats_by_subject,
            "rank_history_by_subject": self.rank_history_by_subject,
            "cycle_evidence_by_subject": self.cycle_evidence_by_subject,
            "cycle_judgement_by_subject": self.cycle_judgement_by_subject,
            "capital_by_subject": self.capital_by_subject,
            "stock_facts_by_subject": self.stock_facts_by_subject,
            "diagnostics": self.diagnostics,
        }


class MainlineDiscoveryFactContextBuilder:
    """Build mainline discovery fact context from read_port sources.

    Sources (in priority order):
    1. MainlineIdentityUniverseBuilder → candidate_subjects
    2. get_subject_event_chain_rows → event detail rows
    3. get_subject_event_stats → aggregate stats
    4. get_subject_cycle_evidence_daily → cycle evidence
    5. get_mainline_cycle_by_subject_keys → cycle judgement
    6. theme_context_map / money_flow → capital data
    """

    def __init__(self, read_port: Any) -> None:
        self._read = read_port

    async def build(
        self,
        *,
        trade_date: date,
        subject_keys_override: list[str] | None = None,
        theme_context_map: dict[str, dict[str, Any]] | None = None,
        lookback_days: int = 7,
    ) -> MainlineDiscoveryFactContext:
        """Build fact context for the given trading date."""
        td_str = trade_date.isoformat()
        diag: dict[str, Any] = {
            "trade_date": td_str,
            "lookback_days": lookback_days,
            "missing_sources": [],
            "fallback_used": [],
            "error_sources": {},
        }

        # ── 1. candidate subjects ──
        candidate_subjects = await self._build_candidates(
            trade_date, subject_keys_override, diag
        )
        subject_keys = [
            str(c["subject_key"]) for c in candidate_subjects
            if str(c.get("subject_key", ""))
        ]

        # ── 2. event detail rows ──
        event_rows_by_subject = await self._fetch_event_rows(
            trade_date, subject_keys, lookback_days, diag
        )

        # ── 3. event stats ──
        event_stats_by_subject = await self._fetch_event_stats(
            trade_date, subject_keys, lookback_days, diag
        )

        # ── 4. cycle evidence ──
        cycle_evidence = await self._fetch_cycle_evidence(
            trade_date, subject_keys, diag
        )

        # ── 5. cycle judgement ──
        cycle_judgement = await self._fetch_cycle_judgement(
            trade_date, subject_keys, diag
        )

        # ── 6. capital & stock_facts from theme_context_map ──
        capital_by_subject: dict[str, dict[str, Any]] = {}
        stock_facts_by_subject: dict[str, list[dict[str, Any]]] = {}
        if theme_context_map:
            for sk, ctx in theme_context_map.items():
                cap = ctx.get("capital")
                if isinstance(cap, dict):
                    capital_by_subject[str(sk)] = cap
                sf = ctx.get("stock_facts")
                if isinstance(sf, list):
                    stock_facts_by_subject[str(sk)] = sf

        diag["candidate_subject_count"] = len(candidate_subjects)
        diag["event_row_subject_count"] = len(event_rows_by_subject)
        diag["event_stats_subject_count"] = len(event_stats_by_subject)
        diag["cycle_evidence_subject_count"] = len(cycle_evidence)
        diag["cycle_judgement_subject_count"] = len(cycle_judgement)
        diag["capital_subject_count"] = len(capital_by_subject)

        return MainlineDiscoveryFactContext(
            trade_date=td_str,
            lookback_days=lookback_days,
            candidate_subjects=candidate_subjects,
            event_rows_by_subject=event_rows_by_subject,
            event_stats_by_subject=event_stats_by_subject,
            rank_history_by_subject={},  # P2: add top-history
            cycle_evidence_by_subject=cycle_evidence,
            cycle_judgement_by_subject=cycle_judgement,
            capital_by_subject=capital_by_subject,
            stock_facts_by_subject=stock_facts_by_subject,
            diagnostics=diag,
        )

    # ── private fetch helpers ──

    async def _build_candidates(
        self,
        td: date,
        override: list[str] | None,
        diag: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if override:
            return [{"subject_key": sk, "theme_name": "", "candidate_source": "override",
                     "priority_score": 0} for sk in override]

        try:
            builder = MainlineIdentityUniverseBuilder(self._read)
            rows = await builder.build(td)
            return [
                {
                    "subject_key": r.subject_key,
                    "theme_name": r.theme_name,
                    "candidate_source": r.universe_source,
                    "priority_score": r.priority_score,
                }
                for r in rows
            ]
        except Exception as exc:
            diag["error_sources"]["candidate_subjects"] = str(exc)[:200]
            diag["missing_sources"].append("candidate_subjects")
            return []

    async def _fetch_event_rows(
        self,
        td: date,
        sks: list[str],
        days: int,
        diag: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        if not sks:
            return {}
        try:
            rows = await self._read.get_subject_event_chain_rows(
                trade_date=td, subject_keys=sks, lookback_days=days,
            )
        except Exception as exc:
            diag["error_sources"]["event_rows"] = str(exc)[:200]
            diag["missing_sources"].append("event_rows")
            return {}

        if not rows:
            diag["missing_sources"].append("event_rows")
            return {}

        by_sk: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            sk = str(r.get("subject_key") or "").strip()
            if sk:
                by_sk.setdefault(sk, []).append(dict(r))
        return by_sk

    async def _fetch_event_stats(
        self,
        td: date,
        sks: list[str],
        days: int,
        diag: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        if not sks:
            return {}
        try:
            rows = await self._read.get_subject_event_stats(
                trade_date=td, subject_keys=sks, lookback_days=days,
            )
        except Exception as exc:
            diag["error_sources"]["event_stats"] = str(exc)[:200]
            diag["missing_sources"].append("event_stats")
            return {}

        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = dict(r.__dict__) if hasattr(r, "__dict__") else dict(r)
            sk = str(d.get("subject_key") or "").strip()
            if sk:
                result[sk] = d
        return result

    async def _fetch_cycle_evidence(
        self,
        td: date,
        sks: list[str],
        diag: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        if not sks:
            return {}
        try:
            rows = await self._read.get_subject_cycle_evidence_daily(
                trade_date=td, subject_keys=sks,
            )
        except Exception as exc:
            diag["error_sources"]["cycle_evidence"] = str(exc)[:200]
            diag["missing_sources"].append("cycle_evidence")
            return {}

        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = dict(r.__dict__) if hasattr(r, "__dict__") else dict(r)
            sk = str(d.get("subject_key") or "").strip()
            if sk:
                result[sk] = d
        return result

    async def _fetch_cycle_judgement(
        self,
        td: date,
        sks: list[str],
        diag: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        if not sks:
            return {}
        try:
            rows = await self._read.get_mainline_cycle_by_subject_keys(
                subject_keys=sks, trade_date=td,
            )
        except Exception as exc:
            diag["error_sources"]["cycle_judgement"] = str(exc)[:200]
            diag["missing_sources"].append("cycle_judgement")
            return {}

        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = dict(r.__dict__) if hasattr(r, "__dict__") else dict(r)
            sk = str(d.get("subject_key") or "").strip()
            if sk:
                result[sk] = d
        return result
