"""Phase 4.5.2 — Report Composer Approval Gate.

Prevents the report composer from consuming raw AI drafts.
Only APPROVED / PUBLISHED snapshots produce formal reports.

Report modes:
  - preview: DRAFT_READY or no snapshot → informational preview only
  - formal:  APPROVED snapshot → full report, can be reviewed
  - published: PUBLISHED snapshot → locked report for distribution
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .approval_contract import ReviewStateStore, RuntimeIntegrityVerifier, project_root
from .session import SessionStore, WorkbenchStatus
from .snapshot import SnapshotStore, ReviewSnapshot
from .snapshot_validator import ApprovedSnapshotValidator


@dataclass(frozen=True, slots=True)
class ReportApproval:
    """Result of approval gate check before composing a report."""

    mode: str  # "preview" | "formal" | "published"
    trade_date: date
    session_status: str
    can_generate_report: bool
    snapshot: ReviewSnapshot | None
    snapshot_version: int
    approved_at: str
    approved_by: str
    reason: str  # human-readable explanation of mode choice


class ApprovalGate:
    """Check whether a report can be composed and at what level."""

    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.session_store = SessionStore(base_dir=base_dir)
        self.snapshot_store = SnapshotStore(base_dir=base_dir)
        self.review_state_store = ReviewStateStore(base_dir=base_dir)
        self.snapshot_validator = ApprovedSnapshotValidator()

    def check(self, trade_date: date) -> ReportApproval:
        """Determine report mode for a given trade date.

        Rules:
          - NOT_STARTED → preview, cannot generate formal report
          - GENERATING / FAILED → preview
          - DRAFT_READY / IN_REVIEW → preview (no approved snapshot yet)
          - APPROVED → formal (snapshot exists, can be published)
          - PUBLISHED → published (locked, immutable)
          - STALE → preview (approved snapshot may be outdated)
        """
        session = self.session_store.get(trade_date)
        snapshot = self.snapshot_store.load(trade_date)
        status = session.status

        if status in (WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED) and snapshot:
            try:
                review_state = self.review_state_store.load(trade_date)
                runtime_manifest_hash = RuntimeIntegrityVerifier.verify(project_root())
                if snapshot.runtime_manifest_hash != runtime_manifest_hash:
                    return self._blocked(
                        trade_date, status, "Approved Snapshot runtime manifest hash mismatch"
                    )
                validation = self.snapshot_validator.validate(
                    session_status=status,
                    snapshot=snapshot,
                    review_state_hash=review_state.get("state_hash") if review_state else None,
                    reviewed_by=review_state.get("reviewed_by") if review_state else None,
                )
            except (RuntimeError, ValueError) as exc:
                return self._blocked(
                    trade_date, status, f"Approved Snapshot integrity validation failed: {exc}"
                )
            if not validation.valid:
                errors = ", ".join(error.value for error in validation.errors)
                return self._blocked(trade_date, status, f"Approved Snapshot validation failed: {errors}")

        if status == WorkbenchStatus.PUBLISHED and snapshot:
            return ReportApproval(
                mode="published",
                trade_date=trade_date,
                session_status=status,
                can_generate_report=True,
                snapshot=snapshot,
                snapshot_version=snapshot.snapshot_version,
                approved_at=snapshot.approved_at,
                approved_by=snapshot.approved_by,
                reason="Published snapshot exists. Report is locked.",
            )

        if status == WorkbenchStatus.APPROVED and snapshot:
            return ReportApproval(
                mode="formal",
                trade_date=trade_date,
                session_status=status,
                can_generate_report=True,
                snapshot=snapshot,
                snapshot_version=snapshot.snapshot_version,
                approved_at=snapshot.approved_at,
                approved_by=snapshot.approved_by,
                reason="Approved snapshot exists. Formal report can be generated.",
            )

        if status in (WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED) and not snapshot:
            return self._blocked(
                trade_date,
                status,
                f"Session is {status} but snapshot.json is missing. "
                "Restore the valid snapshot or re-approve; draft fallback is disabled.",
            )

        if status in (WorkbenchStatus.DRAFT_READY, WorkbenchStatus.IN_REVIEW):
            return ReportApproval(
                mode="preview",
                trade_date=trade_date,
                session_status=status,
                can_generate_report=False,
                snapshot=None,
                snapshot_version=0,
                approved_at="",
                approved_by="",
                reason=f"Session is {status}. Only preview reports allowed. "
                       f"Approve the snapshot first to generate a formal report.",
            )

        # NOT_STARTED, GENERATING, FAILED, STALE, or any unrecognized state
        return ReportApproval(
            mode="preview",
            trade_date=trade_date,
            session_status=status,
            can_generate_report=False,
            snapshot=None,
            snapshot_version=0,
            approved_at="",
            approved_by="",
            reason=f"Session is {status}. No approved snapshot exists. "
                   f"Run generate → review → approve → publish to produce a formal report.",
        )

    @staticmethod
    def _blocked(trade_date: date, status: str, reason: str) -> ReportApproval:
        return ReportApproval(
            mode="blocked",
            trade_date=trade_date,
            session_status=status,
            can_generate_report=False,
            snapshot=None,
            snapshot_version=0,
            approved_at="",
            approved_by="",
            reason=reason,
        )

    def require_formal(self, trade_date: date) -> ReportApproval:
        """Check and raise if no approved snapshot exists."""
        approval = self.check(trade_date)
        if not approval.can_generate_report:
            raise ApprovalRequiredError(
                trade_date=trade_date,
                current_status=approval.session_status,
                reason=approval.reason,
            )
        return approval


class ApprovalRequiredError(Exception):
    """Raised when a formal report is requested but no approved snapshot exists."""

    def __init__(self, trade_date: date, current_status: str, reason: str):
        self.trade_date = trade_date
        self.current_status = current_status
        self.reason = reason
        super().__init__(
            f"No approved snapshot for {trade_date} (status={current_status}). "
            f"{reason}"
        )
