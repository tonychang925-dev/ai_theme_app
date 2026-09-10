"""Fail-closed validator for public Approved Snapshot consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .snapshot import ReviewSnapshot


class ValidationError(str, Enum):
    SESSION_NOT_APPROVED = "session_not_approved"
    SNAPSHOT_NOT_FOUND = "snapshot_not_found"
    NOT_APPROVED = "not_approved"
    HASH_MISMATCH = "hash_mismatch"
    MISSING_HASH = "missing_hash"
    MISSING_APPROVAL_METADATA = "missing_approval_metadata"
    UNBOUND_APPROVER = "unbound_approver"
    REVIEW_STATE_MISMATCH = "review_state_mismatch"
    RUNTIME_INTEGRITY_UNVERIFIED = "runtime_integrity_unverified"
    INVALID_APPROVAL_MODE = "invalid_approval_mode"
    INVALID_SOURCE_MODE = "invalid_source_mode"


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    snapshot: ReviewSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": [error.value for error in self.errors]}


class ApprovedSnapshotValidator:
    ALLOWED_APPROVAL_MODES = frozenset({"analyst_approved", "published"})
    ALLOWED_SOURCE_MODES = frozenset({"formal", "published"})
    ALLOWED_SESSION_STATES = frozenset({"APPROVED", "PUBLISHED"})

    def validate(
        self,
        *,
        session_status: str,
        snapshot: ReviewSnapshot | None,
        review_state_hash: str | None = None,
        reviewed_by: str | None = None,
        recompute_hash: bool = True,
    ) -> ValidationResult:
        errors: list[ValidationError] = []
        if session_status not in self.ALLOWED_SESSION_STATES:
            errors.append(ValidationError.SESSION_NOT_APPROVED)
        if snapshot is None:
            errors.append(ValidationError.SNAPSHOT_NOT_FOUND)
            return ValidationResult(False, errors)
        if not snapshot.approved:
            errors.append(ValidationError.NOT_APPROVED)
        if snapshot.approval_mode not in self.ALLOWED_APPROVAL_MODES:
            errors.append(ValidationError.INVALID_APPROVAL_MODE)
        if snapshot.source_mode not in self.ALLOWED_SOURCE_MODES:
            errors.append(ValidationError.INVALID_SOURCE_MODE)
        if not snapshot.approved_at or not snapshot.approved_by:
            errors.append(ValidationError.MISSING_APPROVAL_METADATA)
        elif snapshot.approved_by == "analyst" or not snapshot.approved_by.startswith(
            "user:"
        ):
            errors.append(ValidationError.UNBOUND_APPROVER)
        if recompute_hash:
            if not snapshot.snapshot_hash:
                errors.append(ValidationError.MISSING_HASH)
            elif snapshot.snapshot_hash != snapshot.compute_hash():
                errors.append(ValidationError.HASH_MISMATCH)
        if not snapshot.review_state_hash:
            errors.append(ValidationError.REVIEW_STATE_MISMATCH)
        elif (
            review_state_hash is not None
            and snapshot.review_state_hash != review_state_hash
        ):
            errors.append(ValidationError.REVIEW_STATE_MISMATCH)
        if reviewed_by is not None and snapshot.reviewed_by != reviewed_by:
            errors.append(ValidationError.REVIEW_STATE_MISMATCH)
        if (
            snapshot.runtime_integrity_status != "verified"
            or len(snapshot.runtime_manifest_hash) != 64
        ):
            errors.append(ValidationError.RUNTIME_INTEGRITY_UNVERIFIED)
        return ValidationResult(not errors, errors, snapshot if not errors else None)


__all__ = ["ApprovedSnapshotValidator", "ValidationError", "ValidationResult"]
