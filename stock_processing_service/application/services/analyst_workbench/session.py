"""Phase 4.5 T01 — Workbench Session Store.

Strict state machine for analyst workbench lifecycle:
  NOT_STARTED → GENERATING → DRAFT_READY → IN_REVIEW → APPROVED → PUBLISHED
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


# ═══ Status Enum ═══

class WorkbenchStatus:
    NOT_STARTED = "NOT_STARTED"
    GENERATING = "GENERATING"
    DRAFT_READY = "DRAFT_READY"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    STALE = "STALE"
    FAILED = "FAILED"


# ═══ Allowed Transitions ═══

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    WorkbenchStatus.NOT_STARTED: {WorkbenchStatus.GENERATING, WorkbenchStatus.FAILED},
    WorkbenchStatus.GENERATING: {WorkbenchStatus.DRAFT_READY, WorkbenchStatus.FAILED},
    WorkbenchStatus.DRAFT_READY: {WorkbenchStatus.IN_REVIEW, WorkbenchStatus.GENERATING, WorkbenchStatus.FAILED},
    WorkbenchStatus.IN_REVIEW: {WorkbenchStatus.DRAFT_READY, WorkbenchStatus.APPROVED, WorkbenchStatus.FAILED},
    WorkbenchStatus.APPROVED: {WorkbenchStatus.PUBLISHED, WorkbenchStatus.STALE},
    WorkbenchStatus.PUBLISHED: {WorkbenchStatus.STALE},
    WorkbenchStatus.STALE: {WorkbenchStatus.GENERATING},
    WorkbenchStatus.FAILED: {WorkbenchStatus.GENERATING},
}


# ═══ Session Model ═══

@dataclass
class WorkbenchSession:
    trade_date: date
    status: str = WorkbenchStatus.NOT_STARTED
    draft_version: int = 0
    snapshot_version: int = 0
    created_at: str = ""
    updated_at: str = ""
    generated_at: str = ""
    reviewed_at: str = ""
    approved_at: str = ""
    published_at: str = ""
    approved_by: str = ""
    error_message: str = ""

    # ── Calibration metadata (Phase 4.5.1) ──
    last_calibrated_at: str = ""
    calibration_status: str = ""      # pending / completed / failed
    calibration_score: float = 0.0
    calibration_grade: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "status": self.status,
            "draft_version": self.draft_version,
            "snapshot_version": self.snapshot_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "generated_at": self.generated_at,
            "reviewed_at": self.reviewed_at,
            "approved_at": self.approved_at,
            "published_at": self.published_at,
            "approved_by": self.approved_by,
            "error_message": self.error_message,
            "last_calibrated_at": self.last_calibrated_at,
            "calibration_status": self.calibration_status,
            "calibration_score": self.calibration_score,
            "calibration_grade": self.calibration_grade,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkbenchSession":
        return cls(
            trade_date=date.fromisoformat(d["trade_date"]),
            status=d.get("status", WorkbenchStatus.NOT_STARTED),
            draft_version=d.get("draft_version", 0),
            snapshot_version=d.get("snapshot_version", 0),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            generated_at=d.get("generated_at", ""),
            reviewed_at=d.get("reviewed_at", ""),
            approved_at=d.get("approved_at", ""),
            published_at=d.get("published_at", ""),
            approved_by=d.get("approved_by", ""),
            error_message=d.get("error_message", ""),
            last_calibrated_at=d.get("last_calibrated_at", ""),
            calibration_status=d.get("calibration_status", ""),
            calibration_score=d.get("calibration_score", 0.0),
            calibration_grade=d.get("calibration_grade", ""),
        )

    @property
    def can_generate(self) -> bool:
        return self.status in (WorkbenchStatus.NOT_STARTED, WorkbenchStatus.DRAFT_READY,
                                WorkbenchStatus.FAILED, WorkbenchStatus.STALE)

    @property
    def can_review(self) -> bool:
        return self.status == WorkbenchStatus.DRAFT_READY

    @property
    def can_approve(self) -> bool:
        return self.status in (WorkbenchStatus.IN_REVIEW, WorkbenchStatus.DRAFT_READY)

    @property
    def can_publish(self) -> bool:
        return self.status == WorkbenchStatus.APPROVED

    @property
    def has_draft(self) -> bool:
        return self.draft_version > 0 and self.status != WorkbenchStatus.NOT_STARTED

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot_version > 0

    @property
    def is_finalized(self) -> bool:
        return self.status in (WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED)


# ═══ Session Store ═══

class SessionStore:
    """JSON persistence for WorkbenchSession."""

    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _session_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat()

    def _session_path(self, trade_date: date) -> Path:
        return self._session_dir(trade_date) / "session.json"

    def get(self, trade_date: date) -> WorkbenchSession:
        """Load existing session or create new one."""
        path = self._session_path(trade_date)
        if path.exists():
            return WorkbenchSession.from_dict(json.loads(path.read_text()))
        return WorkbenchSession(trade_date=trade_date)

    def save(self, session: WorkbenchSession) -> None:
        """Persist session to disk."""
        d = self._session_dir(session.trade_date)
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        if not session.created_at:
            session.created_at = now
        session.updated_at = now
        self._session_path(session.trade_date).write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2))

    def transition(self, session: WorkbenchSession, new_status: str, **kwargs) -> WorkbenchSession:
        """Validate and apply a state transition."""
        allowed = ALLOWED_TRANSITIONS.get(session.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {session.status} → {new_status}. "
                f"Allowed: {allowed}"
            )
        session.status = new_status
        now = datetime.now(timezone.utc).isoformat()
        if new_status == WorkbenchStatus.DRAFT_READY:
            session.generated_at = kwargs.get("generated_at", now)
            session.draft_version = kwargs.get("draft_version", session.draft_version + 1)
        elif new_status == WorkbenchStatus.IN_REVIEW:
            session.reviewed_at = now
        elif new_status == WorkbenchStatus.APPROVED:
            session.approved_at = now
            session.approved_by = kwargs.get("approved_by", "")
            session.snapshot_version = kwargs.get("snapshot_version", session.snapshot_version + 1)
        elif new_status == WorkbenchStatus.PUBLISHED:
            session.published_at = now
        elif new_status == WorkbenchStatus.FAILED:
            session.error_message = kwargs.get("error_message", "")
        self.save(session)
        return session

    def apply_calibration(self, trade_date: date, calibration: dict) -> WorkbenchSession:
        """Persist calibration result to the latest draft and session metadata.

        The calibration dict is merged into the latest draft's calibration field
        and the session is annotated with calibration metadata.
        """
        from .draft import DraftStore

        session = self.get(trade_date)
        draft_store = DraftStore(base_dir=str(self.base_dir))
        draft = draft_store.load(trade_date)
        if draft is None:
            raise ValueError(f"No draft exists for {trade_date}. Generate first.")

        now = datetime.now(timezone.utc).isoformat()
        # Full replacement — calibration is atomic per run, no merge with stale data
        draft.calibration = {
            **calibration,
            "applied_at": now,
        }
        draft_store.save(draft)

        session.last_calibrated_at = now
        session.calibration_status = "completed"
        session.calibration_score = float(calibration.get("overall_score", 0))
        session.calibration_grade = str(calibration.get("grade", ""))
        self.save(session)

        return session

    def list_dates(self) -> list[date]:
        """List all dates with workbench sessions."""
        if not self.base_dir.exists():
            return []
        dates = []
        for d in sorted(self.base_dir.iterdir()):
            if d.is_dir() and d.name != ".":
                try:
                    dates.append(date.fromisoformat(d.name))
                except ValueError:
                    pass
        return dates
