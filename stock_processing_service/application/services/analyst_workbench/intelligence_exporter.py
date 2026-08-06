"""Commit B (fix): Analyst Intelligence Exporter — claims not observations.

Converts Approved ReviewSnapshot → AnalystIntelligenceEnvelope.

P0 fixes:
  1. synthetic → not_ready (in caller)
  2. ATTENTION_TO_SIGNAL removed — ai_theme_app outputs attention_level as-is
  3. observations → claims — ai_theme_app does NOT produce Julia observation format
  4. signal_level deleted from output
  5. Emotion fields use production keys: emotion_node/emotion_label/emotion_score
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Any

from .intelligence_contract import AnalystIntelligenceEnvelope, FORBIDDEN_OUTPUT_FIELDS
from .snapshot import ReviewSnapshot

CST = timezone(timedelta(hours=8))


class AnalystIntelligenceExporter:
    """Exports approved snapshots as ANALYST OPINIONS — not Julia judgments.

    This is the SINGLE entry point for Julia consumption.
    It does NOT read drafts, query databases, or run analysis.

    Output format: AnalystWorkbenchOpinionV1
    Julia's IntelligenceContractMapper converts these to ObservationEvent.
    """

    def export(
        self,
        snapshot: ReviewSnapshot,
        *,
        since_snapshot_version: int | None = None,
    ) -> AnalystIntelligenceEnvelope:
        trade_date_str = snapshot.trade_date.isoformat()

        if since_snapshot_version is not None and snapshot.snapshot_version <= since_snapshot_version:
            return _unchanged_envelope(trade_date_str, snapshot)

        return AnalystIntelligenceEnvelope(
            trade_date=trade_date_str,
            approval=self._build_approval(snapshot),
            market_view=self._build_market_view(snapshot),
            claims=self._build_claims(snapshot),
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

        # P0 fix: use production emotion field keys
        emotion = snap.emotion_review or {}
        if emotion:
            mv["emotion"] = {
                "node": _safe_str(emotion.get("emotion_node", "")),
                "label": _safe_str(emotion.get("emotion_label", "")),
                "score": _safe_int(emotion.get("emotion_score", 0)),
                "risk_level": _safe_str(emotion.get("risk_level", "UNKNOWN")),
                "confidence": _safe_float(emotion.get("confidence", 0)),
                "summary": _safe_str(emotion.get("summary", "")),
                "strategy_bias": _safe_str(emotion.get("strategy_bias", "")),
                "evidence_refs": _safe_list(emotion.get("key_evidence", [])),
                "risk_flags": _safe_list(emotion.get("risk_flags", [])),
            }

        narrative = snap.narrative or {}
        if narrative:
            mv["narrative_summary"] = _safe_str(narrative.get("summary", ""))

        playbook = snap.playbook or {}
        if playbook:
            mv["tomorrow"] = {
                "outlook": _safe_str(playbook.get("tomorrow_outlook", "")),
                "watchpoints": _safe_list(playbook.get("watchpoints", [])),
                "forbidden": _safe_list(playbook.get("forbidden_actions", [])),
            }

        return mv

    def _build_claims(self, snap: ReviewSnapshot) -> list[dict[str, Any]]:
        """Convert cognition_cards → ANALYST CLAIMS (not Julia observations).

        P0 fix: ai_theme_app outputs attention_level as-is.
        Julia's Mapper decides signal_level / experience_tier.
        No observation_id. No signal_level. No admission fields.
        """
        cards = snap.cognition_cards or []
        claims = []

        for card in cards:
            subject_name = _safe_str(card.get("subject_name", ""))
            if not subject_name:
                continue

            stage = _resolve_final(card, "stage_judgement", "")
            analyst_reviewed = bool(card.get("analyst_reviewed", False))

            claim = {
                "claim_id": f"claim_wb_{snap.trade_date.isoformat()}_{_safe_id(subject_name)}",
                "claim_type": "theme_stage",
                "subject": {
                    "type": "theme",
                    "name": subject_name,
                },
                "stage_judgement": _safe_str(stage),
                "attention_level": _safe_str(card.get("attention_level", "LOW")),
                "attention_score": _safe_int(card.get("attention_score", 0)),
                "confidence": _safe_float(card.get("confidence", 0.6)),
                "analyst_reviewed": analyst_reviewed,
                "analyst_override": bool(card.get("analyst_added", False)) or analyst_reviewed,
                "evidence_refs": _extract_evidence(card),
            }

            # P0: strip forbidden fields
            claim = {k: v for k, v in claim.items() if k not in FORBIDDEN_OUTPUT_FIELDS}
            claims.append(claim)

        # Sort by attention_level (CRITICAL first) then attention_score
        level_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        claims.sort(key=lambda c: (level_order.get(c["attention_level"], 9), -c.get("attention_score", 0)))

        return claims

    def _build_quality(self, snap: ReviewSnapshot) -> dict[str, Any]:
        source_quality = getattr(snap, 'source_quality', 0.8) or 0.8
        missing_fields = getattr(snap, 'missing_fields', []) or []
        return {
            "source_quality": float(source_quality),
            "missing_fields": [str(f) for f in missing_fields],
            "claim_count": len(snap.cognition_cards or []),
            "analyst_reviewed": True,
            "snapshot_version": snap.snapshot_version,
        }


# ── Helpers ──────────────────────────────────────────────────────────────

def _resolve_final(card: dict, field: str, default: Any = "") -> Any:
    field_data = card.get(field, {})
    if isinstance(field_data, dict):
        return field_data.get("final_value", field_data.get("ai_value", default))
    return field_data if field_data else default

def _safe_str(val: Any) -> str: return str(val) if val else ""
def _safe_int(val: Any) -> int:
    try: return int(val)
    except: return 0
def _safe_float(val: Any) -> float:
    try: return float(val)
    except: return 0.0
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

def _unchanged_envelope(trade_date: str, snap: ReviewSnapshot) -> AnalystIntelligenceEnvelope:
    return AnalystIntelligenceEnvelope(
        trade_date=trade_date,
        approval={"status": "UNCHANGED", "snapshot_version": snap.snapshot_version, "reason": "no new version"},
    )


__all__ = ["AnalystIntelligenceExporter"]
