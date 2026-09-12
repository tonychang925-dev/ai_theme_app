"""Immutable governed Workbench snapshot revisions and authority."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ReviewSnapshot:
    trade_date: date
    snapshot_version: int = 1
    based_on_draft_version: int = 0
    approved: bool = False
    approved_at: str = ""
    approved_by: str = ""
    approval_mode: str = "preview"
    source_mode: str = "preview"
    snapshot_hash: str = ""
    reviewed_by: str = ""
    review_state_hash: str = ""
    runtime_manifest_hash: str = ""
    runtime_integrity_status: str = "unverified"
    governance_state: str = "APPROVED"
    supersedes_snapshot_version: int = 0
    parent_snapshot_hash: str = ""
    published_at: str = ""
    published_by: str = ""
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance_refs: list[str] = field(default_factory=list)

    attention_state: dict[str, Any] = field(default_factory=dict)
    cognition_cards: list[dict[str, Any]] = field(default_factory=list)
    narrative: dict[str, Any] = field(default_factory=dict)
    playbook: dict[str, Any] = field(default_factory=dict)
    override_summary: dict[str, Any] = field(default_factory=dict)
    emotion_review: dict[str, Any] = field(default_factory=dict)
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "snapshot_version": self.snapshot_version,
            "based_on_draft_version": self.based_on_draft_version,
            "approved": self.approved,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "approval_mode": self.approval_mode,
            "source_mode": self.source_mode,
            "snapshot_hash": self.snapshot_hash,
            "reviewed_by": self.reviewed_by,
            "review_state_hash": self.review_state_hash,
            "runtime_manifest_hash": self.runtime_manifest_hash,
            "runtime_integrity_status": self.runtime_integrity_status,
            "governance_state": self.governance_state,
            "supersedes_snapshot_version": self.supersedes_snapshot_version,
            "parent_snapshot_hash": self.parent_snapshot_hash,
            "published_at": self.published_at,
            "published_by": self.published_by,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            "provenance_refs": self.provenance_refs,
            "attention_state": self.attention_state,
            "cognition_cards": self.cognition_cards,
            "narrative": self.narrative,
            "playbook": self.playbook,
            "override_summary": self.override_summary,
            "emotion_review": self.emotion_review,
            "chart_reviews": self.chart_reviews,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewSnapshot":
        return cls(
            trade_date=date.fromisoformat(data["trade_date"]),
            snapshot_version=data.get("snapshot_version", 1),
            based_on_draft_version=data.get("based_on_draft_version", 0),
            approved=data.get("approved", False),
            approved_at=data.get("approved_at", ""),
            approved_by=data.get("approved_by", ""),
            approval_mode=data.get(
                "approval_mode",
                "analyst_approved" if data.get("approved") else "preview",
            ),
            source_mode=data.get(
                "source_mode", "formal" if data.get("approved") else "preview"
            ),
            snapshot_hash=data.get("snapshot_hash", ""),
            reviewed_by=data.get("reviewed_by", ""),
            review_state_hash=data.get("review_state_hash", ""),
            runtime_manifest_hash=data.get("runtime_manifest_hash", ""),
            runtime_integrity_status=data.get("runtime_integrity_status", "unverified"),
            governance_state=data.get(
                "governance_state", "APPROVED" if data.get("approved") else "DRAFT"
            ),
            supersedes_snapshot_version=data.get("supersedes_snapshot_version", 0),
            parent_snapshot_hash=data.get("parent_snapshot_hash", ""),
            published_at=data.get("published_at", ""),
            published_by=data.get("published_by", ""),
            assumptions=list(data.get("assumptions", [])),
            limitations=list(data.get("limitations", [])),
            provenance_refs=list(data.get("provenance_refs", [])),
            attention_state=data.get("attention_state", {}),
            cognition_cards=data.get("cognition_cards", []),
            narrative=data.get("narrative", {}),
            playbook=data.get("playbook", {}),
            override_summary=data.get("override_summary", {}),
            emotion_review=data.get("emotion_review", {}),
            chart_reviews=data.get("chart_reviews", []),
        )

    @classmethod
    def from_draft(
        cls, draft: Any, overrides: dict | None = None, **kwargs: Any
    ) -> "ReviewSnapshot":
        return cls(
            trade_date=draft.trade_date,
            snapshot_version=kwargs.get("snapshot_version", 1),
            based_on_draft_version=draft.draft_version,
            supersedes_snapshot_version=kwargs.get(
                "supersedes_snapshot_version", kwargs.get("snapshot_version", 1) - 1
            ),
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            approved_by=kwargs.get("approved_by", ""),
            approval_mode=kwargs.get("approval_mode", "analyst_approved"),
            source_mode=kwargs.get("source_mode", "formal"),
            reviewed_by=kwargs.get("reviewed_by", ""),
            review_state_hash=kwargs.get("review_state_hash", ""),
            runtime_manifest_hash=kwargs.get("runtime_manifest_hash", ""),
            runtime_integrity_status=(
                "verified" if kwargs.get("runtime_manifest_hash") else "unverified"
            ),
            assumptions=list(getattr(draft, "assumptions", [])),
            limitations=list(getattr(draft, "limitations", [])),
            provenance_refs=[
                f"draft:v{draft.draft_version}",
                f"generator:{draft.generated_by}",
            ],
            attention_state=draft.attention_state,
            cognition_cards=draft.cognition_cards,
            narrative=draft.narrative,
            playbook=draft.playbook,
            override_summary=overrides or {},
            emotion_review=draft.emotion_review,
            chart_reviews=draft.chart_reviews,
        )

    @classmethod
    def from_merged(
        cls,
        *,
        trade_date: date,
        draft: Any,
        merged: dict[str, Any],
        snapshot_version: int = 1,
        supersedes_snapshot_version: int | None = None,
        approved_by: str = "",
        reviewed_by: str = "",
        review_state_hash: str = "",
        runtime_manifest_hash: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> "ReviewSnapshot":
        effective_assumptions = (
            assumptions
            if assumptions is not None
            else list(getattr(draft, "assumptions", []))
        )
        effective_limitations = (
            limitations
            if limitations is not None
            else list(getattr(draft, "limitations", []))
        )
        return cls(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            supersedes_snapshot_version=(
                snapshot_version - 1
                if supersedes_snapshot_version is None
                else supersedes_snapshot_version
            ),
            based_on_draft_version=draft.draft_version,
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            approved_by=approved_by,
            approval_mode="analyst_approved",
            source_mode="formal",
            attention_state=merged.get("attention_state", {}),
            cognition_cards=merged.get("cognition_cards", []),
            narrative=merged.get("narrative", {}),
            playbook=merged.get("playbook", {}),
            override_summary=merged.get("override_summary", {}),
            emotion_review=merged.get("emotion_review", {}),
            chart_reviews=merged.get("chart_reviews", []),
            reviewed_by=reviewed_by,
            review_state_hash=review_state_hash,
            runtime_manifest_hash=runtime_manifest_hash,
            runtime_integrity_status=(
                "verified" if runtime_manifest_hash else "unverified"
            ),
            assumptions=effective_assumptions,
            limitations=effective_limitations,
            provenance_refs=[
                f"draft:v{draft.draft_version}",
                f"review-state:{review_state_hash}",
                f"runtime-manifest:{runtime_manifest_hash}",
            ],
        )

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload["snapshot_hash"] = ""
        raw = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SnapshotStore:
    AUTHORITY_SCHEMA_VERSION = 1

    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _snapshot_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat()

    def _snapshot_path(self, trade_date: date) -> Path:
        return self._snapshot_dir(trade_date) / "snapshot.json"

    def _revision_path(self, trade_date: date, version: int) -> Path:
        return (
            self._snapshot_dir(trade_date) / "snapshots" / f"snapshot_v{version}.json"
        )

    def _authority_path(self, trade_date: date) -> Path:
        return self._snapshot_dir(trade_date) / "snapshot_authority.json"

    def _load_authority(self, trade_date: date) -> dict[str, Any] | None:
        path = self._authority_path(trade_date)
        if not path.exists():
            return None
        try:
            authority = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("snapshot authority pointer is unreadable") from exc
        if not isinstance(authority, dict):
            raise ValueError("snapshot authority pointer is invalid")
        if authority.get("schema_version") != self.AUTHORITY_SCHEMA_VERSION:
            raise ValueError("unsupported snapshot authority schema")
        if authority.get("trade_date") != trade_date.isoformat():
            raise ValueError("snapshot authority trade date mismatch")
        version = authority.get("current_version")
        digest = authority.get("current_hash")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("snapshot authority version is invalid")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("snapshot authority hash is invalid")
        return authority

    def _write_authority(self, trade_date: date, version: int, digest: str) -> None:
        authority = {
            "schema_version": self.AUTHORITY_SCHEMA_VERSION,
            "trade_date": trade_date.isoformat(),
            "current_version": version,
            "current_hash": digest,
        }
        path = self._authority_path(trade_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(authority, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    @staticmethod
    def _create_once(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)

    @staticmethod
    def _validate_version(snapshot: ReviewSnapshot) -> None:
        if isinstance(snapshot.snapshot_version, bool) or not isinstance(
            snapshot.snapshot_version, int
        ):
            raise ValueError("snapshot_version must be an integer")
        if snapshot.snapshot_version < 1:
            raise ValueError("snapshot_version must be positive")
        if snapshot.supersedes_snapshot_version != snapshot.snapshot_version - 1:
            raise ValueError("snapshot parent version is out of order")

    def _prepare(self, snapshot: ReviewSnapshot) -> ReviewSnapshot:
        self._validate_version(snapshot)
        authority = self._load_authority(snapshot.trade_date)
        if snapshot.snapshot_version == 1:
            if authority is not None:
                raise ValueError("initial snapshot revision already exists")
            if snapshot.parent_snapshot_hash:
                raise ValueError("initial snapshot cannot declare a parent")
        else:
            if authority is None:
                raise ValueError("snapshot predecessor authority is missing")
            if authority.get("current_version") != snapshot.supersedes_snapshot_version:
                raise ValueError("snapshot revision is out of order")
            parent = self.load(
                snapshot.trade_date, version=snapshot.supersedes_snapshot_version
            )
            if (
                parent is None
                or parent.snapshot_version != snapshot.supersedes_snapshot_version
            ):
                raise ValueError("snapshot predecessor is missing or invalid")
            if parent.snapshot_hash != authority.get("current_hash"):
                raise ValueError("snapshot predecessor hash does not match authority")
            if not snapshot.parent_snapshot_hash:
                snapshot.parent_snapshot_hash = parent.snapshot_hash
            if snapshot.parent_snapshot_hash != parent.snapshot_hash:
                raise ValueError("snapshot parent hash mismatch")
        snapshot.snapshot_hash = ""
        snapshot.snapshot_hash = snapshot.compute_hash()
        return snapshot

    def save(self, snapshot: ReviewSnapshot) -> Path:
        prepared = self._prepare(snapshot)
        path = self._revision_path(prepared.trade_date, prepared.snapshot_version)
        try:
            self._create_once(
                path,
                json.dumps(prepared.to_dict(), ensure_ascii=False, indent=2),
            )
        except FileExistsError as exc:
            raise ValueError("snapshot revision already exists") from exc
        self._write_authority(
            prepared.trade_date, prepared.snapshot_version, prepared.snapshot_hash
        )
        return path

    def load(
        self, trade_date: date, version: int | None = None
    ) -> ReviewSnapshot | None:
        if version is not None:
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ValueError("snapshot version must be a positive integer")
            revision = self._revision_path(trade_date, version)
            if revision.exists():
                return ReviewSnapshot.from_dict(json.loads(revision.read_text()))
            return None

        authority = self._load_authority(trade_date)
        if authority is None:
            return None
        current_version = authority.get("current_version")
        snapshot = self.load(trade_date, version=current_version)
        if (
            snapshot is None
            or snapshot.snapshot_version != current_version
            or snapshot.snapshot_hash != authority.get("current_hash")
        ):
            raise ValueError("snapshot current pointer does not match its revision")
        return snapshot

    def publish(self, snapshot: ReviewSnapshot, *, published_by: str) -> ReviewSnapshot:
        if not isinstance(published_by, str) or not published_by.startswith("user:"):
            raise ValueError("publication requires a bound authenticated principal")
        current = self.load(snapshot.trade_date)
        if current is None or current.snapshot_hash != snapshot.snapshot_hash:
            raise ValueError("publication requires the current approved revision")
        if current.governance_state != "APPROVED":
            raise ValueError("publication requires an APPROVED revision")
        now = datetime.now(timezone.utc).isoformat()
        published = replace(
            current,
            snapshot_version=current.snapshot_version + 1,
            governance_state="PUBLISHED",
            supersedes_snapshot_version=current.snapshot_version,
            parent_snapshot_hash=current.snapshot_hash,
            approval_mode="published",
            source_mode="published",
            published_at=now,
            published_by=published_by,
            snapshot_hash="",
        )
        published.provenance_refs = [
            *[
                reference
                for reference in current.provenance_refs
                if not reference.startswith("parent-snapshot:")
            ],
            f"parent-snapshot:v{current.snapshot_version}",
        ]
        self.save(published)
        return published

    def latest_version(self, trade_date: date) -> int:
        snapshot = self.load(trade_date)
        return snapshot.snapshot_version if snapshot else 0
