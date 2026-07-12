"""RecapCompletenessGuard — block ReviewDocument assembly when recap data is missing.

Chart types 5-7 (institution_style, hot_money_style, limitup_classification)
depend on post_market_recap_snapshot. When that snapshot is absent for a trade
date, the ReviewDocument will contain empty limit_up.categories, capital
institution/hot_money directions, etc.

This guard must run BEFORE ReviewDocument assembly. It is NOT a UI check,
NOT an Assembler fallback, and NOT a data inference path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Fields that chart_engine reads from the recap payload to build charts 5-7.
REQUIRED_RECAP_FIELDS = (
    "strong_hotspot_subjects",     # → limitup_classification + hot_money_style
    "mainline_lifecycle_reviews",  # → institution_style directions
    "theme_reviews",               # → institution_style directions (secondary)
)


@dataclass(frozen=True, slots=True)
class RecapCompletenessResult:
    complete: bool
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()


class RecapCompletenessGuard:
    """Check that required recap fields exist for a trade date."""

    def check(self, recap: dict[str, Any] | None) -> RecapCompletenessResult:
        """Verify required recap fields are non-empty.

        Args:
            recap: The recap payload dict from post_market_recap_snapshot,
                   or None/{} if no snapshot exists.

        Returns:
            RecapCompletenessResult with complete=True only if all required
            fields are present and non-empty.
        """
        if not recap:
            return RecapCompletenessResult(
                complete=False,
                missing=REQUIRED_RECAP_FIELDS,
                blocking_issues=("recap_snapshot_missing",),
            )

        present: list[str] = []
        missing: list[str] = []
        blocking: list[str] = []

        for field in REQUIRED_RECAP_FIELDS:
            value = recap.get(field)
            if _is_non_empty(value):
                present.append(field)
            else:
                missing.append(field)
                blocking.append(f"recap.{field}_empty")

        return RecapCompletenessResult(
            complete=len(missing) == 0,
            present=tuple(present),
            missing=tuple(missing),
            blocking_issues=tuple(blocking) if blocking else (),
        )


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, tuple)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return True
