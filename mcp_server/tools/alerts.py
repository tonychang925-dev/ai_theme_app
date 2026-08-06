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

    observations = data.get("observations", [])

    # Filter by minimum signal level
    level_rank = {"L4": 0, "L3": 1, "L2": 2, "L1": 3}
    min_rank = level_rank.get(min_level, 1)

    filtered = [
        obs for obs in observations
        if level_rank.get(obs.get("signal_level", "L1"), 9) <= min_rank
    ]

    return filtered
