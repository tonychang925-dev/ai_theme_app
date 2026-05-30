"""PR-10: MainlineLifecycleFactContextBuilder.

Reads confirmed mainlines from mainline_registry and Layer B data
(theme_cycle_judgement_v2, theme_cycle_evidence_daily) by canonical_subject_key.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from stock_processing_service.domain.services.mainline_lifecycle.models import (
    MainlineLifecycleFactContext,
)

logger = logging.getLogger(__name__)


class MainlineLifecycleFactContextBuilder:
    """Build fact context for confirmed mainline lifecycle evaluation."""

    def __init__(self, read_port: Any) -> None:
        self._read = read_port

    async def build(
        self,
        *,
        trade_date: date,
        confirmed_mainlines: list[dict[str, Any]] | None = None,
    ) -> MainlineLifecycleFactContext:
        td_str = trade_date.isoformat()
        diag: dict[str, Any] = {
            "confirmed_count": 0,
            "layer_b_judgement_count": 0,
            "layer_b_evidence_count": 0,
            "missing_sources": [],
        }

        # ── 1. Get confirmed mainlines from registry ──
        if confirmed_mainlines is None:
            try:
                fn = getattr(self._read, "get_confirmed_mainlines", None)
                if callable(fn):
                    confirmed_mainlines = await fn(trade_date=trade_date)
                else:
                    confirmed_mainlines = []
            except Exception:
                confirmed_mainlines = []

        if not confirmed_mainlines:
            return MainlineLifecycleFactContext(
                trade_date=td_str,
                diagnostics=diag,
            )

        diag["confirmed_count"] = len(confirmed_mainlines)

        # ── 2. Extract canonical_subject_keys ──
        canonical_sks: list[str] = []
        related_sks: set[str] = set()
        for ml in confirmed_mainlines:
            csk = str(ml.get("canonical_subject_key") or "")
            if csk:
                canonical_sks.append(csk)
            rel = ml.get("related_subject_keys_json")
            if isinstance(rel, str):
                try:
                    rel = json.loads(rel)
                except Exception:
                    rel = []
            if isinstance(rel, list):
                for sk in rel:
                    related_sks.add(str(sk))

        all_sks = list(set(canonical_sks + list(related_sks)))

        # ── 3. Fetch Layer B judgement ──
        judgement_by_sk: dict[str, dict[str, Any]] = {}
        if all_sks:
            try:
                rows = await self._read.get_mainline_cycle_by_subject_keys(
                    subject_keys=all_sks, trade_date=td_str if isinstance(td_str, str) else trade_date,
                )
                for r in rows:
                    d = dict(r.__dict__) if hasattr(r, "__dict__") else dict(r)
                    sk = str(d.get("subject_key") or "")
                    if sk:
                        judgement_by_sk[sk] = d
            except Exception:
                diag["missing_sources"].append("cycle_judgement")

        diag["layer_b_judgement_count"] = len(judgement_by_sk)

        # ── 4. Fetch Layer B evidence ──
        evidence_by_sk: dict[str, dict[str, Any]] = {}
        if all_sks:
            try:
                rows = await self._read.get_subject_cycle_evidence_daily(
                    trade_date=td_str if isinstance(td_str, str) else trade_date,
                    subject_keys=all_sks,
                )
                for r in rows:
                    d = dict(r.__dict__) if hasattr(r, "__dict__") else dict(r)
                    sk = str(d.get("subject_key") or "")
                    if sk:
                        evidence_by_sk[sk] = d
            except Exception:
                diag["missing_sources"].append("cycle_evidence")

        diag["layer_b_evidence_count"] = len(evidence_by_sk)

        return MainlineLifecycleFactContext(
            trade_date=td_str,
            confirmed_mainlines=confirmed_mainlines,
            cycle_judgement_by_sk=judgement_by_sk,
            cycle_evidence_by_sk=evidence_by_sk,
            diagnostics=diag,
        )
