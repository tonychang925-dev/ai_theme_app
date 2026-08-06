"""Commit B: Analyst Intelligence Exporter.

Converts Approved ReviewSnapshot → AnalystIntelligenceEnvelope for Julia.

Rules:
  1. Only exports from APPROVED snapshots (validated upstream).
  2. Strips ALL forbidden fields (theme_id, gate_score, embedding, etc.).
  3. Uses final_value (analyst override) over ai_value when available.
  4. Maps attention_level → L0-L4 signal levels.
  5. Includes quality metadata (source_quality, evidence_count, missing_fields).
  6. Versioned — snapshot_version ensures idempotent export.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Any

from .intelligence_contract import (
    AnalystIntelligenceEnvelope,
    FORBIDDEN_OUTPUT_FIELDS,
    ATTENTION_TO_SIGNAL,
)
from .snapshot import ReviewSnapshot

CST = timezone(timedelta(hours=8))


class AnalystIntelligenceExporter:
    """Exports approved snapshots to Julia's intelligence contract.

    This is the SINGLE entry point for Julia consumption.
    It does NOT read drafts, query databases, or run analysis.
    """

    def export(
        self,
        snapshot: ReviewSnapshot,
        *,
        since_snapshot_version: int | None = None,
    ) -> AnalystIntelligenceEnvelope:
        """Convert an approved ReviewSnapshot → AnalystIntelligenceEnvelope.

        Args:
            snapshot: validated, approved ReviewSnapshot
            since_snapshot_version: if set, only export changes since this version
                                   (idempotency — same version → identical output)

        Returns:
            AnalystIntelligenceEnvelope ready for Julia consumption.
        """
        trade_date_str = snapshot.trade_date.isoformat()

        # Idempotency check
        if since_snapshot_version is not None and snapshot.snapshot_version <= since_snapshot_version:
            return _empty_envelope(trade_date_str, snapshot, reason="no new version")

        return AnalystIntelligenceEnvelope(
            trade_date=trade_date_str,
            approval=self._build_approval(snapshot),
            market_view=self._build_market_view(snapshot),
            observations=self._build_observations(snapshot),
            quality=self._build_quality(snapshot),
        )

    # ── Builders ────────────────────────────────────────────────────────

    def _build_approval(self, snap: ReviewSnapshot) -> dict[str, Any]:
        return {
            "status": "APPROVED",
            "snapshot_version": snap.snapshot_version,
            "snapshot_hash": snap.snapshot_hash,
            "approved_at": snap.approved_at,
            "approved_by": snap.approved_by,
            "approval_mode": snap.approval_mode,
            "based_on_draft_version": snap.based_on_draft_version,
        }

    def _build_market_view(self, snap: ReviewSnapshot) -> dict[str, Any]:
        mv: dict[str, Any] = {}

        # Emotion review
        emotion = snap.emotion_review or {}
        if emotion:
            mv["emotion"] = {
                "node": _safe_str(emotion.get("node", "")),
                "label": _safe_str(emotion.get("label", "")),
                "score": _safe_int(emotion.get("score", 0)),
                "risk_level": _safe_str(emotion.get("risk_level", "MEDIUM")),
                "confidence": _safe_float(emotion.get("confidence", 0.5)),
                "summary": _safe_str(emotion.get("summary", "")),
                "strategy_bias": _safe_str(emotion.get("strategy_bias", "")),
                "evidence_refs": _safe_list(emotion.get("evidence_refs", [])),
            }

        # Narrative (analyst-reviewed)
        narrative = snap.narrative or {}
        if narrative:
            mv["narrative_summary"] = _safe_str(narrative.get("summary", ""))

        # Playbook — only strategy bias, NOT trade instructions
        playbook = snap.playbook or {}
        if playbook:
            plan = playbook.get("plan_state", {}) or {}
            mv["tomorrow"] = {
                "outlook": _safe_str(playbook.get("tomorrow_outlook", "")),
                "watchpoints": _safe_list(playbook.get("watchpoints", [])),
                "forbidden": _safe_list(playbook.get("forbidden_actions", [])),
            }

        return mv

    def _build_observations(self, snap: ReviewSnapshot) -> list[dict[str, Any]]:
        """Convert cognition_cards → Julia observation format.

        Uses final_value (analyst override) over ai_value.
        Strips ALL forbidden fields.
        """
        cards = snap.cognition_cards or []
        observations = []

        for card in cards:
            subject_name = _safe_str(card.get("subject_name", ""))
            if not subject_name:
                continue

            attention = _safe_str(card.get("attention_level", "LOW"))
            signal_level = ATTENTION_TO_SIGNAL.get(attention, "L1")

            # Use final_value (analyst override) where available
            stage = _resolve_final(card, "stage_judgement", "")
            score = _safe_int(card.get("attention_score", 0))
            analyst_reviewed = bool(card.get("analyst_reviewed", False))
            has_override = bool(card.get("analyst_added", False))

            obs = {
                "observation_id": f"obs_wb_{snap.trade_date.isoformat()}_{_safe_id(subject_name)}",
                "subject": {
                    "type": "theme",
                    "name": subject_name,
                },
                "type": "theme.cognition",
                "signal_level": signal_level,
                "stage_judgement": _safe_str(stage),
                "attention_score": score,
                "summary": f"{subject_name}: {_safe_str(stage)}阶段, {attention}关注",
                "confidence": _safe_float(card.get("confidence", 0.6)),
                "analyst_reviewed": analyst_reviewed,
                "analyst_override": has_override or analyst_reviewed,
                "evidence_refs": _extract_evidence(card),
            }

            # Strip forbidden fields
            obs = {k: v for k, v in obs.items() if k not in FORBIDDEN_OUTPUT_FIELDS}

            observations.append(obs)

        # Sort by signal level (L4 first) then by attention score
        level_order = {"L4": 0, "L3": 1, "L2": 2, "L1": 3}
        observations.sort(key=lambda o: (level_order.get(o["signal_level"], 9), -o.get("attention_score", 0)))

        return observations

    def _build_quality(self, snap: ReviewSnapshot) -> dict[str, Any]:
        """Build quality metadata from snapshot."""
        source_quality = snap.source_quality if hasattr(snap, 'source_quality') else 0.8
        missing_fields = snap.missing_fields if hasattr(snap, 'missing_fields') else []

        return {
            "source_quality": float(source_quality),
            "missing_fields": [str(f) for f in missing_fields],
            "evidence_count": len(snap.cognition_cards or []),
            "analyst_reviewed": True,
            "snapshot_version": snap.snapshot_version,
        }


# ── Helpers ──────────────────────────────────────────────────────────────

def _resolve_final(card: dict, field: str, default: Any = "") -> Any:
    """Resolve final_value from analyst override structure.

    Card format: {
        "field_name": {
            "ai_value": "...",
            "analyst_value": "...",
            "final_value": "...",
            "override": true/false
        }
    }
    """
    field_data = card.get(field, {})
    if isinstance(field_data, dict):
        return field_data.get("final_value", field_data.get("ai_value", default))
    return field_data if field_data else default


def _safe_str(val: Any) -> str:
    return str(val) if val else ""


def _safe_int(val: Any) -> int:
    try: return int(val)
    except (TypeError, ValueError): return 0


def _safe_float(val: Any) -> float:
    try: return float(val)
    except (TypeError, ValueError): return 0.0


def _safe_list(val: Any) -> list:
    return list(val) if isinstance(val, (list, tuple)) else []


def _safe_id(name: str) -> str:
    import hashlib
    return hashlib.sha256(name.encode()).hexdigest()[:8]


def _extract_evidence(card: dict) -> list[str]:
    refs = []
    for key in ("evidence_refs", "evidence", "attention_reasons"):
        val = card.get(key, [])
        if isinstance(val, list):
            refs.extend([str(v) for v in val if v])
    return refs[:5]


def _empty_envelope(trade_date: str, snap: ReviewSnapshot, reason: str) -> AnalystIntelligenceEnvelope:
    return AnalystIntelligenceEnvelope(
        trade_date=trade_date,
        approval={
            "status": "UNCHANGED",
            "snapshot_version": snap.snapshot_version,
            "reason": reason,
        },
    )


__all__ = ["AnalystIntelligenceExporter"]
