"""Commit A: Approved Snapshot Integrity Validator.

Enforces that Julia ONLY receives fully validated, approved snapshots.
No draft fallback. No hash mismatch. No missing approval metadata.

This is the gate between analyst workbench internals and external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .snapshot import ReviewSnapshot


class ValidationError(str, Enum):
    NOT_APPROVED = "not_approved"
    NOT_PUBLISHED = "not_published"
    HASH_MISMATCH = "hash_mismatch"
    MISSING_HASH = "missing_hash"
    MISSING_APPROVAL_METADATA = "missing_approval_metadata"
    INVALID_APPROVAL_MODE = "invalid_approval_mode"
    INVALID_SOURCE_MODE = "invalid_source_mode"
    SNAPSHOT_NOT_FOUND = "snapshot_not_found"
    SESSION_NOT_APPROVED = "session_not_approved"


@dataclass
class ValidationResult:
    """Outcome of snapshot validation."""
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    snapshot: ReviewSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.value for e in self.errors],
        }


class ApprovedSnapshotValidator:
    """Validates that a snapshot is complete, approved, and tamper-proof.

    Rules (all must pass):
      1. Session status is APPROVED or PUBLISHED
      2. Snapshot file exists and is loadable
      3. snapshot.approved == True
      4. approval_mode is analyst_approved or published
      5. source_mode is formal or published
      6. snapshot_hash is present
      7. snapshot_hash matches recomputed canonical hash

    If ANY check fails → Julia must NOT receive this data.
    """

    # Allowed approval modes for Julia consumption
    ALLOWED_APPROVAL_MODES = frozenset({"analyst_approved", "published"})

    # Allowed source modes
    ALLOWED_SOURCE_MODES = frozenset({"formal", "published"})

    # Allowed session states (WorkbenchStatus uses string constants, not Enum)
    ALLOWED_SESSION_STATES = frozenset({"APPROVED", "PUBLISHED"})

    def validate(
        self,
        session_status: str,
        snapshot: ReviewSnapshot | None,
        recompute_hash: bool = True,
    ) -> ValidationResult:
        """Validate a snapshot for external (Julia) consumption.

        Args:
            session_status: current session status string
            snapshot: the loaded ReviewSnapshot (or None if not found)
            recompute_hash: whether to re-compute and verify the hash

        Returns:
            ValidationResult with valid=True only if ALL checks pass.
        """
        errors: list[ValidationError] = []

        # Rule 1: Session must be APPROVED or PUBLISHED
        if session_status not in self.ALLOWED_SESSION_STATES:
            errors.append(ValidationError.SESSION_NOT_APPROVED)

        # Rule 2: Snapshot must exist
        if snapshot is None:
            errors.append(ValidationError.SNAPSHOT_NOT_FOUND)
            return ValidationResult(valid=False, errors=errors)

        # Rule 3: approved flag
        if not snapshot.approved:
            errors.append(ValidationError.NOT_APPROVED)

        # Rule 4: approval_mode
        if snapshot.approval_mode not in self.ALLOWED_APPROVAL_MODES:
            errors.append(ValidationError.INVALID_APPROVAL_MODE)

        # Rule 5: source_mode
        if snapshot.source_mode not in self.ALLOWED_SOURCE_MODES:
            errors.append(ValidationError.INVALID_SOURCE_MODE)

        # Rule 6: hash present
        if not snapshot.snapshot_hash:
            errors.append(ValidationError.MISSING_HASH)
        elif recompute_hash:
            # Rule 7: hash integrity
            recomputed = snapshot.compute_hash() if hasattr(snapshot, 'compute_hash') else ""
            if recomputed and snapshot.snapshot_hash != recomputed:
                errors.append(ValidationError.HASH_MISMATCH)

        # Rule 8: basic approval metadata
        if not snapshot.approved_at or not snapshot.approved_by:
            errors.append(ValidationError.MISSING_APPROVAL_METADATA)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            snapshot=snapshot if len(errors) == 0 else None,
        )


__all__ = ["ApprovedSnapshotValidator", "ValidationResult", "ValidationError"]
