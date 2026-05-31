"""PR-12.5: ActiveMainlineUniverseBuilder.

Reads active confirmed mainlines from registry that remain valid today.
Distinguishes between "new discovery" and "old mainline maintenance".

Key semantics: old mainlines persist until explicitly expired or archived.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ActiveMainlineUniverse:
    trade_date: str = ""
    active_mainlines: list[dict[str, Any]] = field(default_factory=list)
    active_subject_keys: set[str] = field(default_factory=set)
    active_mainline_ids: set[str] = field(default_factory=set)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "active_mainline_count": len(self.active_mainlines),
            "active_subject_keys": sorted(self.active_subject_keys),
            "active_mainline_ids": sorted(self.active_mainline_ids),
            "diagnostics": self.diagnostics,
        }


class ActiveMainlineUniverseBuilder:
    """Build the universe of active confirmed mainlines for today's trading.

    Reads ALL mainlines with identity_status='confirmed' and valid date range,
    regardless of when they were confirmed. This is the stable input for
    lifecycle, market_regime, and post_market_decision_v2.
    """

    def __init__(self, read_port: Any) -> None:
        self._read = read_port

    async def build(self, *, trade_date: date) -> ActiveMainlineUniverse:
        td_str = trade_date.isoformat()
        mainlines: list[dict[str, Any]] = []

        try:
            fn = getattr(self._read, "get_active_confirmed_mainlines", None)
            if not callable(fn):
                fn = getattr(self._read, "get_confirmed_mainlines", None)
            if callable(fn):
                mainlines = await fn(trade_date=trade_date, limit=100)
        except Exception as exc:
            logger.error("Failed to read active mainlines: %s", exc)

        active_sks: set[str] = set()
        active_ids: set[str] = set()
        seen_canonical: set[str] = set()
        deduped: list[dict[str, Any]] = []

        # Dedup by canonical_subject_key: keep latest valid_from entry
        for ml in sorted(mainlines, key=lambda m: str(m.get("valid_from") or ""), reverse=True):
            csk = str(ml.get("canonical_subject_key") or "")
            if csk in seen_canonical:
                continue
            seen_canonical.add(csk)
            deduped.append(ml)

        for ml in deduped:
            mid = str(ml.get("mainline_id") or "")
            csk = str(ml.get("canonical_subject_key") or "")
            active_ids.add(mid)
            active_sks.add(csk)
            # Add related
            rel = ml.get("related_subject_keys_json")
            if isinstance(rel, str):
                try: rel = json.loads(rel)
                except: rel = []
            if isinstance(rel, list):
                for rsk in rel:
                    active_sks.add(str(rsk))
            # Add branch
            br = ml.get("branch_subject_keys_json")
            if isinstance(br, str):
                try: br = json.loads(br)
                except: br = []
            if isinstance(br, list):
                for bsk in br:
                    active_sks.add(str(bsk))

        diag = {
            "source": "registry",
            "raw_count": len(mainlines),
            "deduped_count": len(deduped),
            "active_count": len(active_sks),
            "active_subject_count": len(active_sks),
            "validity": f"identity_status=confirmed, valid_from<={td_str}, valid_to NULL or >={td_str}",
        }

        return ActiveMainlineUniverse(
            trade_date=td_str,
            active_mainlines=mainlines,
            active_subject_keys=active_sks,
            active_mainline_ids=active_ids,
            diagnostics=diag,
        )

    @staticmethod
    def is_duplicate_of_active(
        candidate_subject_key: str,
        active_keys: set[str],
    ) -> str | None:
        """Check if a candidate subject_key belongs to an existing active mainline.

        Returns: None if new, or a category string:
          - 'existing_mainline_branch_event' if matches related/branch
          - 'existing_mainline_strengthening' if matches canonical
        """
        if not candidate_subject_key:
            return None
        if candidate_subject_key in active_keys:
            return "existing_mainline_strengthening"
        return None
