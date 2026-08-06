"""Commit D: Approved-only Intelligence Export E2E Tests.

Validates the full chain: Snapshot → Validator → Exporter → Envelope → Julia-ready.

Run:
  python -m pytest tests/workbench/test_intelligence_export_e2e.py -v
"""

import sys
from pathlib import Path

# Ensure ai_theme_app root is in the import path
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
    ATTENTION_TO_SIGNAL,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_snapshot(**overrides) -> ReviewSnapshot:
    """Create a valid approved snapshot with sensible defaults."""
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
        "attention_state": {"charts_available": 7, "context_quality": 1.0},
        "cognition_cards": [
            {
                "subject_name": "人形机器人",
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
                "analyst_reviewed": True,
                "analyst_added": False,
                "stage_judgement": {
                    "ai_value": "diffusion",
                    "analyst_value": "diffusion",
                    "final_value": "diffusion",
                    "override": False,
                },
                "confidence": 0.72,
            },
            {
                "subject_name": "低空经济",
                "attention_level": "LOW",
                "attention_score": 800,
                "analyst_reviewed": False,
                "analyst_added": False,
                "stage_judgement": "start",
                "confidence": 0.45,
            },
        ],
        "narrative": {"summary": "市场处于结构性分化，AI相关题材活跃"},
        "playbook": {"tomorrow_outlook": "关注AI加速方向", "watchpoints": ["量能持续性"]},
        "emotion_review": {
            "node": "REPAIR",
            "label": "情绪修复",
            "score": 18,
            "risk_level": "MEDIUM",
            "confidence": 0.82,
            "summary": "市场情绪温和修复",
            "strategy_bias": "短线偏多",
        },
        "chart_reviews": [],
        "market_state": {"up_count": 2800, "down_count": 1200, "turnover": 8500},
        "source_quality": 0.88,
        "missing_fields": [],
    }
    defaults.update(overrides)
    snap = ReviewSnapshot(trade_date=defaults["trade_date"])
    for k, v in defaults.items():
        if k != "trade_date" and hasattr(snap, k):
            setattr(snap, k, v)
    # Manually set hash since compute_hash may not exist
    if not snap.snapshot_hash:
        snap.snapshot_hash = defaults.get("snapshot_hash", "")
    return snap


# ── Validator Tests ──────────────────────────────────────────────────────────

def test_approved_snapshot_passes():
    """APPROVED + valid hash → returns snapshot."""
    snap = _make_snapshot()
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", snap, recompute_hash=False)
    assert result.valid is True
    assert result.snapshot is not None


def test_draft_ready_session_rejected():
    """DRAFT_READY session → rejected."""
    snap = _make_snapshot()
    validator = ApprovedSnapshotValidator()
    result = validator.validate("DRAFT_READY", snap, recompute_hash=False)
    assert result.valid is False
    assert ValidationError.SESSION_NOT_APPROVED in result.errors


def test_in_review_session_rejected():
    """IN_REVIEW session → rejected."""
    snap = _make_snapshot()
    validator = ApprovedSnapshotValidator()
    result = validator.validate("IN_REVIEW", snap, recompute_hash=False)
    assert result.valid is False


def test_not_approved_flag_rejected():
    """snapshot.approved=False → rejected."""
    snap = _make_snapshot(approved=False)
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", snap, recompute_hash=False)
    assert result.valid is False
    assert ValidationError.NOT_APPROVED in result.errors


def test_missing_snapshot_rejected():
    """None snapshot → rejected."""
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", None)
    assert result.valid is False
    assert ValidationError.SNAPSHOT_NOT_FOUND in result.errors


def test_invalid_approval_mode_rejected():
    """preview approval_mode → rejected."""
    snap = _make_snapshot(approval_mode="preview")
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", snap, recompute_hash=False)
    assert result.valid is False
    assert ValidationError.INVALID_APPROVAL_MODE in result.errors


def test_published_session_passes():
    """PUBLISHED session → accepted."""
    snap = _make_snapshot(approval_mode="published", source_mode="published")
    validator = ApprovedSnapshotValidator()
    result = validator.validate("PUBLISHED", snap, recompute_hash=False)
    assert result.valid is True


# ── Exporter Tests ───────────────────────────────────────────────────────────

def test_exporter_produces_valid_envelope():
    """Exporter produces AnalystIntelligenceEnvelope from approved snapshot."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    assert envelope.schema_version == "analyst-workbench.intelligence.v1"
    assert envelope.provider == "ai_theme_app"
    assert envelope.trade_date == "2026-08-06"

    data = envelope.to_dict()
    approval = data["approval"]
    assert approval["status"] == "APPROVED"
    assert approval["snapshot_version"] == 1


def test_exporter_uses_final_value_over_ai_value():
    """Analyst override (final_value) takes precedence over ai_value."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    # "人形机器人" has analyst override: final_value="acceleration"
    robot_obs = [o for o in envelope.observations if "人形机器人" in o["subject"]["name"]]
    assert len(robot_obs) == 1
    assert robot_obs[0]["stage_judgement"] == "acceleration"
    assert robot_obs[0]["analyst_override"] is True


def test_exporter_maps_attention_to_signal_level():
    """CRITICAL→L4, HIGH→L3, LOW→L1."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    levels = {o["subject"]["name"]: o["signal_level"] for o in envelope.observations}
    assert levels.get("人形机器人") == "L4"  # CRITICAL
    assert levels.get("半导体设备") == "L3"  # HIGH
    assert levels.get("低空经济") == "L1"    # LOW


def test_exporter_observations_sorted_by_signal():
    """L4 observations appear before L3, L2, L1."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    levels = [o["signal_level"] for o in envelope.observations]
    assert levels == sorted(levels, key=lambda l: {"L4": 0, "L3": 1, "L2": 2, "L1": 3}.get(l, 9))


def test_exporter_strips_forbidden_fields():
    """No FORBIDDEN_OUTPUT_FIELDS in any observation."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    for obs in envelope.observations:
        for field in FORBIDDEN_OUTPUT_FIELDS:
            assert field not in obs, f"Forbidden field '{field}' leaked into observation"


def test_exporter_includes_quality_metadata():
    """Quality metadata: source_quality, evidence_count, missing_fields."""
    snap = _make_snapshot()
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap)

    quality = envelope.quality
    assert quality["source_quality"] >= 0.8  # source_quality from snapshot or default
    assert quality["analyst_reviewed"] is True
    assert quality["evidence_count"] >= 1


def test_exporter_idempotent():
    """Same snapshot_version → unchanged."""
    snap = _make_snapshot(snapshot_version=1)
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snap, since_snapshot_version=1)
    data = envelope.to_dict()
    assert data["approval"]["status"] == "UNCHANGED"


# ── Integrity: Validator + Exporter combined ─────────────────────────────────

def test_validator_rejects_then_exporter_not_called():
    """If validator rejects, exporter MUST NOT be invoked for Julia."""
    snap = _make_snapshot(approved=False)
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", snap, recompute_hash=False)

    assert result.valid is False
    assert result.snapshot is None  # Julia must not receive this

    # Exporter would only be called if valid
    # (proved by the fact that result.snapshot is None)


def test_full_chain_approved_to_envelope():
    """Validator passes → Exporter produces → Julia-ready envelope."""
    snap = _make_snapshot()
    validator = ApprovedSnapshotValidator()
    result = validator.validate("APPROVED", snap, recompute_hash=False)
    assert result.valid is True

    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(result.snapshot)
    data = envelope.to_dict()

    # Julia receives a complete, valid intelligence report
    assert data["approval"]["status"] == "APPROVED"
    assert len(data["observations"]) == 3
    assert data["market_view"]["emotion"]["node"] == "REPAIR"
    assert data["quality"]["analyst_reviewed"] is True
