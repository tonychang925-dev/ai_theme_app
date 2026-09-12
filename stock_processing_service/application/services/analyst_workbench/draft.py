"""Phase 4.5 T01 — AI Draft model + store."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AIDraft:
    trade_date: date
    draft_version: int = 1
    supersedes_version: int = 0

    attention_state: dict[str, Any] = field(default_factory=dict)
    cognition_cards: list[dict[str, Any]] = field(default_factory=list)
    narrative: dict[str, Any] = field(default_factory=dict)
    playbook: dict[str, Any] = field(default_factory=dict)

    # ── Calibration (Phase 4.5.1) ──
    calibration: dict[str, Any] = field(default_factory=dict)

    # ── Workbench Sections (Phase 4.5.4) ──
    emotion_review: dict[str, Any] = field(default_factory=dict)
    chart_reviews: list[dict[str, Any]] = field(default_factory=list)

    generated_by: str = "ai_workbench_v1"
    generated_at: str = ""
    source_quality: float = 1.0
    missing_fields: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "draft_version": self.draft_version,
            "supersedes_version": self.supersedes_version,
            "attention_state": self.attention_state,
            "cognition_cards": self.cognition_cards,
            "narrative": self.narrative,
            "playbook": self.playbook,
            "calibration": self.calibration,
            "emotion_review": self.emotion_review,
            "chart_reviews": self.chart_reviews,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at or datetime.now(timezone.utc).isoformat(),
            "source_quality": self.source_quality,
            "missing_fields": self.missing_fields,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AIDraft":
        return cls(
            trade_date=date.fromisoformat(d["trade_date"]),
            draft_version=d.get("draft_version", 1),
            supersedes_version=d.get("supersedes_version", 0),
            attention_state=d.get("attention_state", {}),
            cognition_cards=d.get("cognition_cards", []),
            narrative=d.get("narrative", {}),
            playbook=d.get("playbook", {}),
            calibration=d.get("calibration", {}),
            emotion_review=d.get("emotion_review", {}),
            chart_reviews=d.get("chart_reviews", []),
            generated_by=d.get("generated_by", "ai_workbench_v1"),
            generated_at=d.get("generated_at", ""),
            source_quality=d.get("source_quality", 1.0),
            missing_fields=d.get("missing_fields", []),
            assumptions=list(d.get("assumptions", [])),
            limitations=list(d.get("limitations", [])),
        )


class DraftStore:
    AUTHORITY_SCHEMA_VERSION = 1

    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _drafts_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat() / "drafts"

    def _draft_path(self, trade_date: date, version: int) -> Path:
        return self._drafts_dir(trade_date) / f"draft_v{version}.json"

    def _authority_path(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat() / "draft_authority.json"

    def _load_authority(self, trade_date: date) -> dict[str, Any] | None:
        path = self._authority_path(trade_date)
        if not path.exists():
            return None
        try:
            authority = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("draft authority pointer is unreadable") from exc
        if not isinstance(authority, dict):
            raise ValueError("draft authority pointer is invalid")
        if authority.get("schema_version") != self.AUTHORITY_SCHEMA_VERSION:
            raise ValueError("unsupported draft authority schema")
        if authority.get("trade_date") != trade_date.isoformat():
            raise ValueError("draft authority trade date mismatch")
        version = authority.get("current_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("draft authority version is invalid")
        return authority

    def _write_authority(self, trade_date: date, version: int) -> None:
        authority = {
            "schema_version": self.AUTHORITY_SCHEMA_VERSION,
            "trade_date": trade_date.isoformat(),
            "current_version": version,
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
    def _validate_version(draft: AIDraft) -> None:
        if isinstance(draft.draft_version, bool) or not isinstance(
            draft.draft_version, int
        ):
            raise ValueError("draft_version must be an integer")
        if draft.draft_version < 1:
            raise ValueError("draft_version must be positive")
        expected_parent = draft.draft_version - 1
        if draft.supersedes_version != expected_parent:
            raise ValueError("draft supersedes_version must equal draft_version - 1")

    def save(self, draft: AIDraft) -> Path:
        if not isinstance(draft, AIDraft):
            raise ValueError("draft must be an AIDraft")
        self._validate_version(draft)
        authority = self._load_authority(draft.trade_date)
        if draft.draft_version == 1:
            if authority is not None:
                raise ValueError("initial draft revision already exists")
        else:
            if authority is None:
                raise ValueError("draft predecessor authority is missing")
            if authority.get("current_version") != draft.supersedes_version:
                raise ValueError("draft revision is out of order")
            predecessor = self.load(draft.trade_date, version=draft.supersedes_version)
            if (
                predecessor is None
                or predecessor.draft_version != draft.supersedes_version
            ):
                raise ValueError("draft predecessor is missing or invalid")

        draft.generated_at = datetime.now(timezone.utc).isoformat()
        path = self._draft_path(draft.trade_date, draft.draft_version)
        try:
            self._create_once(
                path,
                json.dumps(draft.to_dict(), ensure_ascii=False, indent=2),
            )
        except FileExistsError as exc:
            raise ValueError("draft revision already exists") from exc
        self._write_authority(draft.trade_date, draft.draft_version)
        return path

    def load(self, trade_date: date, version: int | None = None) -> AIDraft | None:
        if version is not None:
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ValueError("draft version must be a positive integer")
            p = self._draft_path(trade_date, version)
            if p.exists():
                return AIDraft.from_dict(json.loads(p.read_text()))
            return None

        authority = self._load_authority(trade_date)
        if authority is None:
            return None
        current_version = authority.get("current_version")
        draft = self.load(trade_date, version=current_version)
        if draft is None or draft.draft_version != current_version:
            raise ValueError("draft current pointer does not match its revision")
        return draft

    def latest_version(self, trade_date: date) -> int:
        draft = self.load(trade_date)
        return draft.draft_version if draft else 0

    def create_calibrated_revision(
        self, draft: AIDraft, calibration: dict[str, Any]
    ) -> AIDraft:
        current = self.load(draft.trade_date)
        if current is None:
            raise ValueError("No draft exists for calibration. Generate first.")
        revised = AIDraft.from_dict(current.to_dict())
        revised.draft_version = current.draft_version + 1
        revised.supersedes_version = current.draft_version
        revised.calibration = {
            **calibration,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save(revised)
        return revised
