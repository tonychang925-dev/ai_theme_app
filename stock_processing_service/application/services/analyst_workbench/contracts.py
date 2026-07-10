"""Contracts for analyst workbench application services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkbenchGenerationStep:
    step: str
    status: str
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class WorkbenchGenerateResult:
    trade_date: str
    status: str
    steps_completed: tuple[str, ...] = ()
    generation_steps: tuple[WorkbenchGenerationStep, ...] = ()
    session_status: str = ""
    draft_version: int = 0
    derived_status: str = ""
    draft_status: str = ""
    missing_tables: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    source_quality: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "status": self.status,
            "steps_completed": list(self.steps_completed),
            "generation_steps": [step.to_dict() for step in self.generation_steps],
            "session_status": self.session_status,
            "draft_version": self.draft_version,
            "derived_status": self.derived_status,
            "draft_status": self.draft_status,
            "missing_tables": list(self.missing_tables),
            "missing_fields": list(self.missing_fields),
            "source_quality": self.source_quality,
            "error": self.error,
        }
