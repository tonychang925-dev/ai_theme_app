"""Commit B: Analyst Intelligence Contract — frozen schema for Julia consumption.

ADR-030 Integration Contract: Julia receives ONLY approved, analyst-validated
conclusions. No raw data. No internal fields. No draft fallback.

This is the stable interface between ai_theme_app Analyst Workbench and
Julia OS Awareness Runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

CST = timezone(timedelta(hours=8))


# ── Envelope ────────────────────────────────────────────────────────────────

@dataclass
class AnalystIntelligenceEnvelope:
    """The frozen contract for Julia's market intelligence consumption.

    Schema version: analyst-workbench.intelligence.v1
    Provider: ai_theme_app
    Only produced from APPROVED ReviewSnapshots.
    """
    schema_version: str = "analyst-workbench.intelligence.v1"
    provider: str = "ai_theme_app"
    trade_date: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(CST).isoformat())

    # Approval metadata (proves this is analyst-validated)
    approval: dict[str, Any] = field(default_factory=dict)

    # Market view — analyst-approved conclusions
    market_view: dict[str, Any] = field(default_factory=dict)

    # Theme observations — cognition cards mapped to Julia observation format
    observations: list[dict[str, Any]] = field(default_factory=list)

    # Quality metadata
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "trade_date": self.trade_date,
            "generated_at": self.generated_at,
            "approval": self.approval,
            "market_view": self.market_view,
            "observations": self.observations,
            "quality": self.quality,
        }


# ── Forbidden Output Fields (MUST NOT appear in envelope) ──────────────────

FORBIDDEN_OUTPUT_FIELDS = frozenset({
    "theme_id",          # internal database PK
    "subject_id",        # internal database PK
    "gate_score",        # algorithm internal
    "embedding",         # model internal
    "algorithm_version", # implementation detail
    "source_table",      # DB schema leak
    "internal_rank",     # ranking implementation
    "pool_metadata",     # DB connection detail
})


# ── Attention level → Julia signal level mapping ────────────────────────────

ATTENTION_TO_SIGNAL = {
    "CRITICAL": "L4",
    "HIGH":     "L3",
    "MEDIUM":   "L2",
    "LOW":      "L1",
}


__all__ = [
    "AnalystIntelligenceEnvelope",
    "FORBIDDEN_OUTPUT_FIELDS",
    "ATTENTION_TO_SIGNAL",
]
