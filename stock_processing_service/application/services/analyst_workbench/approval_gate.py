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
from typing import Any, Protocol

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
    snapshot_hash: str = ""


@dataclass(frozen=True, slots=True)
class GovernedWorkbenchProduct:
    product_id: str
    revision_id: str
    governance_state: str
    produced_at: str
    data_cutoff: str
    supersedes_revision_id: str
    judgment_content: dict[str, Any]
    provenance_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "revision_id": self.revision_id,
            "governance_state": self.governance_state,
            "produced_at": self.produced_at,
            "data_cutoff": self.data_cutoff,
            "supersedes_revision_id": self.supersedes_revision_id,
            "judgment_content": self.judgment_content,
            "provenance_refs": list(self.provenance_refs),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
        }


class WorkbenchGovernedProductPort(Protocol):
    def read(self, trade_date: date) -> GovernedWorkbenchProduct | None: ...


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
        status = session.status
        try:
            snapshot = self.snapshot_store.load(trade_date)
        except (OSError, RuntimeError, ValueError) as exc:
            return self._blocked(
                trade_date,
                status,
                f"Approved Snapshot authority is unreadable: {exc}",
            )

        if status in (WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED):
            try:
                if snapshot is None:
                    return self._blocked(
                        trade_date,
                        status,
                        "governed snapshot authority is missing",
                )
                review_state = self.review_state_store.load(trade_date)
                if review_state is None:
                    return self._blocked(
                        trade_date,
                        status,
                        "governed review state is missing",
                    )
                runtime_manifest_hash = RuntimeIntegrityVerifier.verify(project_root())
                if snapshot.runtime_manifest_hash != runtime_manifest_hash:
                    return self._blocked(
                        trade_date,
                        status,
                        "Approved Snapshot runtime manifest hash mismatch",
                    )
                if session.snapshot_version != snapshot.snapshot_version:
                    return self._blocked(
                        trade_date,
                        status,
                        "session snapshot authority version mismatch",
                    )
                expected_session_hash = (
                    session.published_snapshot_hash
                    if status == WorkbenchStatus.PUBLISHED
                    else session.snapshot_hash
                )
                if expected_session_hash != snapshot.snapshot_hash:
                    return self._blocked(
                        trade_date,
                        status,
                        "session snapshot authority hash mismatch",
                    )
                if session.approved_by != snapshot.approved_by:
                    return self._blocked(
                        trade_date,
                        status,
                        "session snapshot approver binding mismatch",
                    )
                if status == WorkbenchStatus.PUBLISHED and (
                    not session.published_by.startswith("user:")
                    or session.published_by != snapshot.published_by
                ):
                    return self._blocked(
                        trade_date,
                        status,
                        "session snapshot publisher binding mismatch",
                    )
                validation = self.snapshot_validator.validate(
                    session_status=status,
                    snapshot=snapshot,
                    review_state_hash=(
                        review_state.get("state_hash") if review_state else None
                    ),
                    reviewed_by=(
                        review_state.get("reviewed_by") if review_state else None
                    ),
                )
                if (
                    status == WorkbenchStatus.APPROVED
                    and snapshot.governance_state != WorkbenchStatus.APPROVED
                ) or (
                    status == WorkbenchStatus.PUBLISHED
                    and snapshot.governance_state != WorkbenchStatus.PUBLISHED
                ):
                    return self._blocked(
                        trade_date,
                        status,
                        "session and snapshot governance states do not match",
                    )
                if status == WorkbenchStatus.PUBLISHED and (
                    snapshot.approval_mode != "published"
                    or snapshot.source_mode != "published"
                    or not snapshot.published_by.startswith("user:")
                    or snapshot.supersedes_snapshot_version < 1
                    or not snapshot.parent_snapshot_hash
                ):
                    return self._blocked(
                        trade_date,
                        status,
                        "published revision lineage is invalid",
                    )
            except (RuntimeError, ValueError) as exc:
                return self._blocked(
                    trade_date,
                    status,
                    f"Approved Snapshot integrity validation failed: {exc}",
                )
            if not validation.valid:
                errors = ", ".join(error.value for error in validation.errors)
                return self._blocked(
                    trade_date, status, f"Approved Snapshot validation failed: {errors}"
                )

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
                snapshot_hash=snapshot.snapshot_hash,
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
                snapshot_hash=snapshot.snapshot_hash,
            )

        if (
            status in (WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED)
            and not snapshot
        ):
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


class WorkbenchGovernedProductReadModel:
    def __init__(self, approval_gate: ApprovalGate):
        self.approval_gate = approval_gate

    def read(self, trade_date: date) -> GovernedWorkbenchProduct | None:
        approval = self.approval_gate.check(trade_date)
        if not approval.can_generate_report or approval.snapshot is None:
            return None
        snapshot = approval.snapshot
        digest = snapshot.snapshot_hash
        return GovernedWorkbenchProduct(
            product_id=f"wgp:{trade_date.isoformat()}:{digest[:24]}",
            revision_id=f"rev:v{snapshot.snapshot_version}:{digest[:16]}",
            governance_state=snapshot.governance_state,
            produced_at=snapshot.approved_at,
            data_cutoff=snapshot.published_at or snapshot.approved_at,
            supersedes_revision_id=(
                f"rev:v{snapshot.supersedes_snapshot_version}:"
                f"{snapshot.parent_snapshot_hash[:16]}"
                if snapshot.supersedes_snapshot_version
                else ""
            ),
            judgment_content={
                "attention_state": snapshot.attention_state,
                "cognition_cards": snapshot.cognition_cards,
                "narrative": snapshot.narrative,
                "playbook": snapshot.playbook,
                "emotion_review": snapshot.emotion_review,
                "chart_reviews": snapshot.chart_reviews,
            },
            provenance_refs=tuple(snapshot.provenance_refs),
            assumptions=tuple(snapshot.assumptions),
            limitations=tuple(snapshot.limitations),
        )
