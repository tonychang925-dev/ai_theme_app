"""Phase 4.5 T01 — Review Snapshot model + store."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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

    attention_state: dict[str, Any] = field(default_factory=dict)
    cognition_cards: list[dict[str, Any]] = field(default_factory=list)
    narrative: dict[str, Any] = field(default_factory=dict)
    playbook: dict[str, Any] = field(default_factory=dict)
    override_summary: dict[str, Any] = field(default_factory=dict)

    # ── Workbench Sections (Phase 4.5.4) ──
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
            "attention_state": self.attention_state,
            "cognition_cards": self.cognition_cards,
            "narrative": self.narrative,
            "playbook": self.playbook,
            "override_summary": self.override_summary,
            "emotion_review": self.emotion_review,
            "chart_reviews": self.chart_reviews,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewSnapshot":
        return cls(
            trade_date=date.fromisoformat(d["trade_date"]),
            snapshot_version=d.get("snapshot_version", 1),
            based_on_draft_version=d.get("based_on_draft_version", 0),
            approved=d.get("approved", False),
            approved_at=d.get("approved_at", ""),
            approved_by=d.get("approved_by", ""),
            attention_state=d.get("attention_state", {}),
            cognition_cards=d.get("cognition_cards", []),
            narrative=d.get("narrative", {}),
            playbook=d.get("playbook", {}),
            override_summary=d.get("override_summary", {}),
            emotion_review=d.get("emotion_review", {}),
            chart_reviews=d.get("chart_reviews", []),
        )

    @classmethod
    def from_draft(cls, draft: "AIDraft", overrides: dict | None = None, **kwargs) -> "ReviewSnapshot":
        from datetime import datetime, timezone
        return cls(
            trade_date=draft.trade_date,
            snapshot_version=kwargs.get("snapshot_version", 1),
            based_on_draft_version=draft.draft_version,
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            approved_by=kwargs.get("approved_by", ""),
            attention_state=draft.attention_state,
            cognition_cards=draft.cognition_cards,
            narrative=draft.narrative,
            playbook=draft.playbook,
            override_summary=overrides or {},
            emotion_review=draft.emotion_review,
            chart_reviews=draft.chart_reviews,
        )


class SnapshotStore:
    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _snapshot_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat()

    def _snapshot_path(self, trade_date: date) -> Path:
        return self._snapshot_dir(trade_date) / "snapshot.json"

    def save(self, snapshot: ReviewSnapshot) -> Path:
        d = self._snapshot_dir(snapshot.trade_date)
        d.mkdir(parents=True, exist_ok=True)
        p = self._snapshot_path(snapshot.trade_date)
        p.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
        return p

    def load(self, trade_date: date) -> ReviewSnapshot | None:
        p = self._snapshot_path(trade_date)
        if not p.exists():
            return None
        return ReviewSnapshot.from_dict(json.loads(p.read_text()))
