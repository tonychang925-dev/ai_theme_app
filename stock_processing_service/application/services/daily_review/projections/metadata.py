"""Metadata projection for FormalReviewProjectionCompiler.

Projects metadata from engine_report + approval info.
"""

from __future__ import annotations

from typing import Any


def project_metadata(
    *,
    trade_date: str,
    engine_report: dict[str, Any],
    snapshot_meta: dict[str, Any] | None = None,
    source_info: dict[str, Any] | None = None,
    theme_name_map: dict[str, str] | None = None,
    generated_at: str = "",
    snapshot_version: str = "",
) -> dict[str, Any]:
    """Build the metadata block.

    Args:
        trade_date: ISO date string.
        engine_report: Full engine report dict (for source references).
        snapshot_meta: Approval metadata from WorkbenchReportComposer.
        source_info: Source info from DailyReviewV2Builder.
        theme_name_map: Subject key → display name mapping.
        generated_at: ISO timestamp of generation.
        snapshot_version: Version string.

    Returns:
        metadata dict.
    """
    approval: dict[str, Any] = {}
    if snapshot_meta:
        approval = {
            "mode": snapshot_meta.get("mode", "preview"),
            "session_status": snapshot_meta.get("session_status", ""),
            "can_generate_formal_report": snapshot_meta.get("can_generate_formal_report", False),
            "snapshot_version": snapshot_meta.get("snapshot_version"),
            "approved_by": snapshot_meta.get("approved_by", ""),
            "approved_at": snapshot_meta.get("approved_at", ""),
            "snapshot_hash": snapshot_meta.get("snapshot_hash", ""),
            "approval_mode": snapshot_meta.get("approval_mode", ""),
            "source_mode": snapshot_meta.get("source_mode", ""),
            "composition_mode": snapshot_meta.get("composition_mode", ""),
        }

    source: dict[str, Any] = {}
    if source_info:
        source = {
            "snapshot_id": source_info.get("snapshot_id"),
            "recap_snapshot_version": source_info.get("recap_snapshot_version", ""),
            "derived_data_status": source_info.get("derived_data_status", ""),
            "recap_generate_status": source_info.get("recap_generate_status", ""),
        }

    return {
        "schema_version": "daily_review_v3",
        "projection_version": "formal_review_v1",
        "trade_date": trade_date,
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "report_type": "post_market",
        "approval": approval,
        "source": source,
        "theme_name_map": theme_name_map or {},
    }
