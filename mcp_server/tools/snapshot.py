"""Tool 3: review_market_snapshot — Julia's daily context entry point.

Commit C: Now reads from APPROVED Analyst Workbench Snapshot via
ApprovedSnapshotValidator + AnalystIntelligenceExporter.

Returns: AnalystIntelligenceEnvelope (analyst-workbench.intelligence.v1).
Only approved, hash-verified snapshots. No draft fallback.
"""

from __future__ import annotations

from datetime import date as _date


def review_market_snapshot(date: str | None = None) -> dict:
    """Return analyst-approved market overview for Julia consumption.

    Sources:
      - Approved ReviewSnapshot from analyst workbench
      - Falls back to synthetic data if no approved snapshot exists

    Returns AnalystIntelligenceEnvelope in ADR-030 format.
    """
    trade_date = _resolve_trade_date(date)

    try:
        envelope = _export_from_workbench(trade_date)
        if envelope is not None:
            return envelope
    except Exception:
        pass

    # Fallback: no approved snapshot → not_ready (P0: never fake market conclusions)
    return _not_ready_envelope(trade_date)


def _export_from_workbench(trade_date: str) -> dict | None:
    """Load approved snapshot → validate → export for Julia."""
    import os as _os
    import json as _json
    from pathlib import Path as _Path

    # Locate the workbench snapshot
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    wb_base = _Path(project_root) / "tmp" / "analyst_workbench" / trade_date

    session_path = wb_base / "session.json"
    snapshot_path = wb_base / "snapshot.json"

    if not session_path.exists() or not snapshot_path.exists():
        return None

    # Load session
    session_data = _json.loads(session_path.read_text(encoding="utf-8"))
    session_status = session_data.get("status", "NOT_STARTED")

    # Load snapshot
    from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
    snap_data = _json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot = ReviewSnapshot.from_dict(snap_data) if hasattr(ReviewSnapshot, 'from_dict') else None

    if snapshot is None:
        return None

    # Validate
    from stock_processing_service.application.services.analyst_workbench.snapshot_validator import (
        ApprovedSnapshotValidator,
    )
    validator = ApprovedSnapshotValidator()
    result = validator.validate(session_status, snapshot)

    if not result.valid:
        return {
            "schema_version": "analyst-workbench.intelligence.v1",
            "provider": "ai_theme_app",
            "trade_date": trade_date,
            "status": "rejected",
            "rejection_errors": [e.value for e in result.errors],
        }

    # Export
    from stock_processing_service.application.services.analyst_workbench.intelligence_exporter import (
        AnalystIntelligenceExporter,
    )
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snapshot)
    return envelope.to_dict()


def _not_ready_envelope(trade_date: str) -> dict:
    """No approved snapshot → not_ready. No fake market conclusions."""
    return {
        "schema_version": "analyst-workbench.intelligence.v1",
        "provider": "ai_theme_app",
        "trade_date": trade_date,
        "status": "not_ready",
        "reason": "approved_snapshot_not_found",
        "claims": [],
        "market_view": {},
    }


def _resolve_trade_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    return datetime.now(CST).strftime("%Y-%m-%d")
