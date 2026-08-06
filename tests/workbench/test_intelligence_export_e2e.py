"""Fix: Analyst Opinion Export E2E — claims not observations, attention not signal.

P0 fixes verified:
  P0-1: not_ready replaces synthetic
  P0-2: ATTENTION_TO_SIGNAL deleted → ai_theme_app outputs attention_level as-is
  P0-3: claims replace observations (ai_theme_app does NOT output Julia format)
  P0-4: emotion fields use production keys (emotion_node/emotion_label/emotion_score)

Run:
  python -m pytest tests/workbench/test_intelligence_export_e2e.py -v
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import json
from datetime import date

import pytest

from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
from stock_processing_service.application.services.analyst_workbench.snapshot_validator import (
    ApprovedSnapshotValidator,
    ValidationError,
)
from stock_processing_service.application.services.analyst_workbench.intelligence_exporter import (
    AnalystIntelligenceExporter,
)
from stock_processing_service.application.services.analyst_workbench.intelligence_contract import (
    AnalystIntelligenceEnvelope,
    FORBIDDEN_OUTPUT_FIELDS,
    # ATTENTION_TO_SIGNAL removed — P0 fix
)


def _make_snapshot(**overrides) -> ReviewSnapshot:
    defaults = {
        "trade_date": date(2026, 8, 6),
        "snapshot_version": 1,
        "based_on_draft_version": 1,
        "approved": True,
        "approved_at": "2026-08-06T15:30:00+08:00",
        "approved_by": "analyst",
        "approval_mode": "analyst_approved",
        "source_mode": "formal",
        "snapshot_hash": "abc123",
        "source_quality": 0.88,
        "missing_fields": [],
        "attention_state": {"charts_available": 7, "context_quality": 1.0},
        "cognition_cards": [
            {
                "subject_name": "创新药",
                "attention_level": "CRITICAL",
                "attention_score": 5740,
                "analyst_reviewed": True,
                "analyst_added": False,
                "stage_judgement": {
                    "ai_value": "diffusion",
                    "analyst_value": "acceleration",
                    "final_value": "acceleration",
                    "override": True,
                },
                "confidence": 0.84,
            },
            {
                "subject_name": "半导体设备",
                "attention_level": "HIGH",
                "attention_score": 3200,
                "analyst_reviewed": False,
                "stage_judgement": "diffusion",
                "confidence": 0.62,
            },
        ],
        "narrative": {"summary": "结构性分化"},
        "playbook": {"tomorrow_outlook": "关注AI方向"},
        # P0 fix: use production field keys
        "emotion_review": {
            "emotion_node": "REPAIR",
            "emotion_label": "情绪修复",
            "emotion_score": 18,
            "risk_level": "MEDIUM",
            "confidence": 0.82,
            "summary": "市场情绪温和修复",
            "strategy_bias": "短线偏多",
            "key_evidence": ["breadth_improving", "capital_recovering"],
        },
        "chart_reviews": [],
        "market_state": {},
    }
    defaults.update(overrides)
    snap = ReviewSnapshot(trade_date=defaults["trade_date"])
    for k, v in defaults.items():
        if k != "trade_date" and hasattr(snap, k):
            setattr(snap, k, v)
    if not snap.snapshot_hash:
        snap.snapshot_hash = defaults.get("snapshot_hash", "")
    return snap


# ── Validator (unchanged, P0-1 in snapshot.py) ─────────────────────────────

def test_approved_snapshot_passes():
    snap = _make_snapshot()
    result = ApprovedSnapshotValidator().validate("APPROVED", snap, recompute_hash=False)
    assert result.valid

def test_draft_rejected():
    result = ApprovedSnapshotValidator().validate("DRAFT_READY", _make_snapshot(), recompute_hash=False)
    assert not result.valid
    assert ValidationError.SESSION_NOT_APPROVED in result.errors

def test_not_approved_rejected():
    result = ApprovedSnapshotValidator().validate("APPROVED", _make_snapshot(approved=False), recompute_hash=False)
    assert not result.valid

def test_missing_snapshot():
    result = ApprovedSnapshotValidator().validate("APPROVED", None)
    assert not result.valid

def test_invalid_approval_mode():
    result = ApprovedSnapshotValidator().validate("APPROVED", _make_snapshot(approval_mode="preview"), recompute_hash=False)
    assert not result.valid


# ── P0-3: Exporter outputs claims (not observations) ────────────────────

def test_exporter_outputs_claims_not_observations():
    """P0-3 fix: ai_theme_app outputs 'claims', not 'observations'."""
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)
    data = envelope.to_dict()

    assert "claims" in data, f"Expected 'claims', got keys: {list(data.keys())}"
    assert "observations" not in data, "ai_theme_app must NOT output 'observations'"


# ── P0-2: attention_level preserved as-is, no signal_level ──────────────

def test_exporter_preserves_attention_level_no_signal():
    """P0-2 fix: attention_level is output as-is. No signal_level mapping."""
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)

    for claim in envelope.claims:
        # attention_level is the workbench's own label — not Julia's signal
        assert "attention_level" in claim
        assert claim["attention_level"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        # P0 fix: signal_level must NOT appear
        assert "signal_level" not in claim, (
            f"ai_theme_app must NOT output signal_level. Julia decides this."
        )


def test_exporter_preserves_analyst_override():
    """final_value takes precedence over ai_value."""
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)

    innovation = [c for c in envelope.claims if "创新药" in c["subject"]["name"]][0]
    assert innovation["stage_judgement"] == "acceleration"  # from final_value
    assert innovation["analyst_override"] is True


# ── P0-4: Emotion uses production field keys ────────────────────────────

def test_emotion_uses_production_keys():
    """P0-4 fix: emotion reads emotion_node/emotion_label/emotion_score."""
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)
    data = envelope.to_dict()

    emotion = data["market_view"]["emotion"]
    assert emotion["node"] == "REPAIR"
    assert emotion["label"] == "情绪修复"
    assert emotion["score"] == 18
    assert emotion["risk_level"] == "MEDIUM"
    # key_evidence from production is mapped to evidence_refs
    assert len(emotion["evidence_refs"]) >= 1


# ── P0-1: not_ready snapshot tool ───────────────────────────────────────

def test_not_ready_when_no_approved_snapshot():
    """P0-1 fix: no synthetic fallback — returns not_ready."""
    from mcp_server.tools.snapshot import _not_ready_envelope
    result = _not_ready_envelope("2026-08-06")

    assert result["status"] == "not_ready"
    assert result["reason"] == "approved_snapshot_not_found"
    assert result["claims"] == []
    # Must NOT contain synthetic market conclusions
    assert "market_sentiment" not in str(result)
    assert "synthetic" not in str(result.get("status", ""))


# ── Forbidden fields ────────────────────────────────────────────────────

def test_no_forbidden_fields_in_claims():
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)
    for claim in envelope.claims:
        for field in FORBIDDEN_OUTPUT_FIELDS:
            assert field not in claim, f"'{field}' leaked into claim"


# ── Quality metadata ────────────────────────────────────────────────────

def test_quality_has_claim_count():
    snap = _make_snapshot()
    envelope = AnalystIntelligenceExporter().export(snap)
    assert envelope.quality["claim_count"] >= 1
    assert envelope.quality["analyst_reviewed"] is True


# ── Idempotency ─────────────────────────────────────────────────────────

def test_same_version_returns_unchanged():
    snap = _make_snapshot(snapshot_version=1)
    envelope = AnalystIntelligenceExporter().export(snap, since_snapshot_version=1)
    assert envelope.to_dict()["approval"]["status"] == "UNCHANGED"
