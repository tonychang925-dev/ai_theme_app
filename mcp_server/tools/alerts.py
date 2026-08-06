"""Tool 2: list_active_alerts — Julia's high-importance observation feed.

Commit C: Now reads from APPROVED Analyst Workbench Snapshot via
ApprovedSnapshotValidator + AnalystIntelligenceExporter.

Returns: filtered observations with L3/L4 signal levels only.
Only approved, hash-verified snapshots. No draft fallback.
"""

from __future__ import annotations


def list_active_alerts(level: str = "L3") -> list[dict]:
    """Return high-importance observations from the approved workbench snapshot.

    Filters observations by signal_level >= requested level.
    Default: L3 and above (CRITICAL + HIGH).

    Sources:
      - Approved ReviewSnapshot from analyst workbench
      - Falls back to empty list if no approved snapshot exists
    """
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    trade_date = datetime.now(CST).strftime("%Y-%m-%d")

    try:
        observations = _alerts_from_workbench(trade_date, level)
        if observations:
            return observations
    except Exception:
        pass

    return []


def _alerts_from_workbench(trade_date: str, min_level: str) -> list[dict]:
    """Extract high-level observations from approved workbench snapshot."""
    import os as _os
    import json as _json
    from pathlib import Path as _Path

    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    wb_base = _Path(project_root) / "tmp" / "analyst_workbench" / trade_date

    session_path = wb_base / "session.json"
    snapshot_path = wb_base / "snapshot.json"

    if not session_path.exists() or not snapshot_path.exists():
        return []

    session_data = _json.loads(session_path.read_text(encoding="utf-8"))
    session_status = session_data.get("status", "NOT_STARTED")

    from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
    snap_data = _json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot = ReviewSnapshot.from_dict(snap_data) if hasattr(ReviewSnapshot, 'from_dict') else None

    if snapshot is None:
        return []

    from stock_processing_service.application.services.analyst_workbench.snapshot_validator import (
        ApprovedSnapshotValidator,
    )
    validator = ApprovedSnapshotValidator()
    result = validator.validate(session_status, snapshot)

    if not result.valid:
        return []

    from stock_processing_service.application.services.analyst_workbench.intelligence_exporter import (
        AnalystIntelligenceExporter,
    )
    exporter = AnalystIntelligenceExporter()
    envelope = exporter.export(snapshot)
    data = envelope.to_dict()

    claims = data.get("claims", [])

    # Filter by attention_level (P0 fix: ai_theme_app outputs attention, not signal)
    attention_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    if min_level == "L4": min_rank = 0
    elif min_level == "L3": min_rank = 1
    else: min_rank = 2

    filtered = [
        claim for claim in claims
        if attention_rank.get(claim.get("attention_level", "LOW"), 9) <= min_rank
    ]

    return filtered
