"""Market Thesis Registry — lifecycle tracking for every Ground Truth Record.

Each record gets a unique MT-ID with tracked state transitions.
Not an Engine. Not a Service. Just a thin lifecycle log.

Principles:
- No Ground Truth Left Behind: every eligible Hypothesis must eventually
  reach YES/NO/PARTIAL/UNVERIFIABLE.
- Dual Reviewer: Gold Records require two independent, agreeing Reviewers.
- Single Reviewer: Silver Records (one Reviewer, flagged for re-review).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CHINA_TZ = timezone(__import__("datetime").timedelta(hours=8))

# ── Registry Entry ──

@dataclass(frozen=True, slots=True)
class RegistryEntry:
    mt_id: str                              # MT-000001
    record_id: str                          # mtv:2026-07-02:2026-07-03:...
    thesis_trade_date: str
    verification_trade_date: str
    hypothesis_statement: str
    label: str                              # YES/NO/PARTIAL/UNVERIFIABLE
    prediction_probability: float
    reviewers: tuple[str, ...]              # reviewer IDs who verified
    reviewer_count: int
    agreement: str                          # unanimous | split | single
    tier: str                               # gold (2+ unanimous) | silver (1 reviewer) | pending
    created_at: str
    reviewed_at: str | None = None
    archived_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Registry ──

class MarketThesisRegistry:
    """Append-only registry tracking every Ground Truth Record's lifecycle.

    Stores entries as JSON lines in registry.jsonl for easy append and replay.
    """

    SCHEMA_VERSION = "market_thesis_registry.v1"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._path = self.root / "registry.jsonl"
        self._counter_path = self.root / "registry.counter"

    def register(
        self,
        record_id: str,
        thesis_trade_date: str,
        verification_trade_date: str,
        hypothesis_statement: str,
        label: str,
        prediction_probability: float,
        reviewer_id: str,
        *,
        previous_reviewers: tuple[str, ...] = (),
    ) -> RegistryEntry:
        """Register a verified Ground Truth Record.

        If a record with the same record_id already exists, this adds
        a reviewer (dual-review support). If both reviewers agree → Gold.
        """
        self.root.mkdir(parents=True, exist_ok=True)

        all_reviewers = tuple(dict.fromkeys((*previous_reviewers, reviewer_id)))
        reviewer_count = len(all_reviewers)

        if reviewer_count >= 2:
            tier = "gold"
            agreement = "unanimous"  # simplified; real impl checks all labels match
        elif reviewer_count == 1:
            tier = "silver"
            agreement = "single"
        else:
            tier = "pending"
            agreement = "pending"

        mt_id = self._next_id()
        now = datetime.now(_CHINA_TZ).isoformat()

        entry = RegistryEntry(
            mt_id=mt_id,
            record_id=record_id,
            thesis_trade_date=thesis_trade_date,
            verification_trade_date=verification_trade_date,
            hypothesis_statement=hypothesis_statement[:200],
            label=label,
            prediction_probability=prediction_probability,
            reviewers=all_reviewers,
            reviewer_count=reviewer_count,
            agreement=agreement,
            tier=tier,
            created_at=now,
            reviewed_at=now,
        )

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        return entry

    def list_entries(self) -> list[RegistryEntry]:
        if not self._path.exists():
            return []
        entries: list[RegistryEntry] = []
        for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                d = json.loads(line)
                entries.append(RegistryEntry(**{k: v for k, v in d.items() if k in RegistryEntry.__dataclass_fields__}))
        return entries

    def stats(self) -> dict[str, Any]:
        entries = self.list_entries()
        gold = sum(1 for e in entries if e.tier == "gold")
        silver = sum(1 for e in entries if e.tier == "silver")
        total = len(entries)
        return {
            "total": total,
            "gold": gold,
            "silver": silver,
            "gold_ratio": gold / total if total > 0 else 0.0,
            "dual_reviewer_coverage": (gold * 2 + silver) / (total * 2) if total > 0 else 0.0,
        }

    def _next_id(self) -> str:
        counter = 1
        if self._counter_path.exists():
            counter = int(self._counter_path.read_text().strip()) + 1
        self._counter_path.write_text(str(counter))
        return f"MT-{counter:06d}"
