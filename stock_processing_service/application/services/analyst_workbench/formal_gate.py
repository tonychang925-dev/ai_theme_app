"""Strict formal compose guard for analyst-approved workbench snapshots."""
from __future__ import annotations

from dataclasses import dataclass

from .approval_gate import ReportApproval
from .snapshot import ReviewSnapshot


@dataclass(frozen=True)
class FormalComposeGuard:
    """Validate that formal reports can only consume approved snapshots."""

    def validate(self, approval: ReportApproval) -> ReviewSnapshot:
        snapshot = approval.snapshot
        if snapshot is None:
            raise FormalComposeGuardError("formal compose requires snapshot.json")
        if not approval.can_generate_report:
            raise FormalComposeGuardError(
                f"formal compose requires approved session, got {approval.session_status}"
            )
        self.validate_snapshot(snapshot)
        return snapshot

    def validate_snapshot(self, snapshot: ReviewSnapshot) -> None:
        if snapshot.approved is not True:
            raise FormalComposeGuardError("formal compose requires approved=true")
        if not snapshot.approved_at:
            raise FormalComposeGuardError("formal compose requires approved_at")
        if snapshot.approval_mode not in ("analyst_approved", "published"):
            raise FormalComposeGuardError(
                f"invalid approval_mode for formal compose: {snapshot.approval_mode}"
            )
        if snapshot.composition_mode != "formal":
            raise FormalComposeGuardError(
                f"invalid composition_mode for formal compose: {snapshot.composition_mode}"
            )
        if snapshot.source_mode != "analyst_workbench":
            raise FormalComposeGuardError(
                f"invalid source_mode for formal compose: {snapshot.source_mode}"
            )
        if not snapshot.snapshot_hash:
            raise FormalComposeGuardError("formal compose requires snapshot_hash")
        if snapshot.snapshot_hash != snapshot.compute_hash():
            raise FormalComposeGuardError("snapshot_hash mismatch")


class FormalComposeGuardError(Exception):
    """Raised when a snapshot is not valid for formal report composition."""
