"""Phase 4.5 T01 — AI Draft model + store."""
from __future__ import annotations

import json
import re
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
        )


class DraftStore:
    def __init__(self, base_dir: str = "tmp/analyst_workbench"):
        self.base_dir = Path(base_dir)

    def _drafts_dir(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat() / "drafts"

    def _draft_path(self, trade_date: date, version: int) -> Path:
        return self._drafts_dir(trade_date) / f"draft_v{version}.json"

    def save(self, draft: AIDraft) -> Path:
        d = self._drafts_dir(draft.trade_date)
        d.mkdir(parents=True, exist_ok=True)
        draft.generated_at = datetime.now(timezone.utc).isoformat()
        p = self._draft_path(draft.trade_date, draft.draft_version)
        p.write_text(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2))
        return p

    def load(self, trade_date: date, version: int | None = None) -> AIDraft | None:
        d = self._drafts_dir(trade_date)
        if not d.exists():
            return None
        if version is not None:
            p = self._draft_path(trade_date, version)
            if p.exists():
                return AIDraft.from_dict(json.loads(p.read_text()))
            return None
        # Find latest version
        path = latest_draft_path(d)
        if path is None:
            return None
        return AIDraft.from_dict(json.loads(path.read_text()))

    def latest_version(self, trade_date: date) -> int:
        draft = self.load(trade_date)
        return draft.draft_version if draft else 0


def draft_file_version(path: Path) -> int:
    match = re.fullmatch(r"draft_v(\d+)\.json", path.name)
    return int(match.group(1)) if match else -1


def latest_draft_path(drafts_dir: Path) -> Path | None:
    files = [path for path in drafts_dir.glob("draft_v*.json") if draft_file_version(path) >= 0]
    if not files:
        return None
    return max(files, key=draft_file_version)
