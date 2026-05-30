"""MainlineReviewService — PR-9C: Human review decisions for mainline candidates.

Supports: confirm_mainline, watch, reject, downgrade_to_theme, merge_into_existing_mainline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MainlineReviewService:
    """Service for human review decisions on machine candidates."""

    def __init__(self, write_port: Any, read_port: Any | None = None) -> None:
        self._write = write_port
        self._read = read_port

    async def submit_decision(
        self,
        *,
        review_id: str,
        human_decision: str,
        canonical_subject_key: str | None = None,
        mainline_name: str | None = None,
        human_reviewer: str | None = None,
        human_notes: str | None = None,
        related_subject_keys: list[str] | None = None,
        merge_target_mainline_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit a human decision for a review item.

        Returns dict with status and any write results.
        """
        valid_decisions = {"confirm_mainline", "watch", "reject", "downgrade_to_theme", "merge_into_existing_mainline"}
        if human_decision not in valid_decisions:
            return {"ok": False, "error": f"invalid decision: {human_decision}", "valid": list(valid_decisions)}

        # ── confirm_mainline ──
        if human_decision == "confirm_mainline":
            if not canonical_subject_key:
                return {"ok": False, "error": "confirm_mainline requires canonical_subject_key"}
            if not mainline_name:
                return {"ok": False, "error": "confirm_mainline requires mainline_name"}

            # 1. Upsert mainline_registry
            registry_row = {
                "mainline_id": f"ml_{canonical_subject_key}_{datetime.now(timezone.utc).strftime('%Y%m')}",
                "mainline_name": mainline_name,
                "canonical_subject_key": canonical_subject_key,
                "mainline_type": "fast_line",
                "identity_status": "confirmed",
                "valid_from": date.today(),
                "valid_to": None,
                "source_review_id": review_id,
                "core_subject_keys": [canonical_subject_key],
                "branch_subject_keys": [],
                "related_subject_keys": related_subject_keys or [],
                "human_reviewer": human_reviewer,
                "human_notes": human_notes,
            }
            await self._write.upsert_mainline_registry_rows([registry_row])

            # 2. Mark review_queue as reviewed
            await self._mark_reviewed(review_id, human_decision, human_reviewer, human_notes)
            return {"ok": True, "action": "confirmed", "mainline_id": registry_row["mainline_id"]}

        # ── merge_into_existing_mainline ──
        if human_decision == "merge_into_existing_mainline":
            if not merge_target_mainline_id:
                return {"ok": False, "error": "merge requires merge_target_mainline_id"}
            await self._mark_reviewed(review_id, human_decision, human_reviewer, human_notes)
            await self._write.update_mainline_registry_related_keys(
                merge_target_mainline_id, related_subject_keys or [],
            )
            return {"ok": True, "action": "merged", "target": merge_target_mainline_id}

        # ── watch / reject / downgrade_to_theme ──
        await self._mark_reviewed(review_id, human_decision, human_reviewer, human_notes)
        return {"ok": True, "action": human_decision, "registry_written": False}

    async def _mark_reviewed(self, review_id: str, decision: str, reviewer: str | None, notes: str | None) -> None:
        """Update the review queue row with human decision (direct SQL, avoids overwrite issue)."""
        try:
            pool = getattr(getattr(self._write, "_db", None), "_client", None)
            if pool is None:
                pool = getattr(self._write, "pool", None)
            if pool is None:
                return
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE mainline_review_queue
                       SET review_status = 'reviewed', human_decision = $2,
                           human_reviewer = $3, human_notes = $4, reviewed_at = NOW()
                       WHERE review_id = $1""",
                    review_id, decision, reviewer, notes,
                )
        except Exception:
            logger.exception("Failed to mark review %s as reviewed", review_id)
