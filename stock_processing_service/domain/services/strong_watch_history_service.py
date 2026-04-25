from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


@dataclass(frozen=True)
class StrongWatchHistoryRecord:
    trade_date: date
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    watch_status: str
    pool_entry_type: str
    relay_role: str
    strong_grade: str
    watch_score: Decimal
    watch_priority: Decimal
    cycle_state: str
    mainline_strength_score: Decimal
    fade_watch: bool
    fade_confirmed: bool
    promoted_to_candidate: bool
    support_score: Decimal
    support_type: str
    support_level: Decimal = Decimal("0")
    prune_mode: str | None = None
    prune_reason_code: str | None = None
    removed_reason: str | None = None
    kept_because: str | None = None
    labels_json: dict | None = None
    evidence_json: dict | None = None


class StrongWatchHistoryService:
    def build_history_snapshot(
        self,
        trade_date: date,
        kept_rows: list[StrongWatchRecord],
        pruned_rows: list[StrongWatchRecord],
    ) -> list[StrongWatchHistoryRecord]:
        rows: list[StrongWatchHistoryRecord] = []
        for row in [*kept_rows, *pruned_rows]:
            rows.append(
                StrongWatchHistoryRecord(
                    trade_date=trade_date,
                    stock_id=row.stock_id,
                    stock_name=row.stock_name,
                    subject_key=row.subject_key,
                    theme_name=row.subject_name,
                    watch_status=row.watch_status,
                    pool_entry_type=row.admission_status if row.admission_status in {"formal", "observe_only"} else "observe_only",
                    relay_role="unknown",
                    strong_grade=row.strong_grade,
                    watch_score=row.watch_score,
                    watch_priority=row.watch_score,
                    cycle_state=str((row.role_tags or {}).get("final_cycle_state", "")),
                    mainline_strength_score=Decimal("0"),
                    fade_watch=bool((row.role_tags or {}).get("final_cycle_state", "") == "fade_watch"),
                    fade_confirmed=bool((row.role_tags or {}).get("final_cycle_state", "") == "fade_confirmed"),
                    promoted_to_candidate=bool(row.admission_status == "formal"),
                    support_score=row.support_score,
                    support_type=row.support_type,
                    support_level=row.support_level,
                    prune_mode=row.prune_mode,
                    prune_reason_code=row.prune_reason_code,
                    removed_reason=row.removed_reason,
                    kept_because=row.kept_because,
                    labels_json={
                        "strong_grade": row.strong_grade,
                        "support_refs": list(row.support_refs or []),
                        "gap_hit": bool(row.gap_hit),
                        "gap_hit_mode": str(row.gap_hit_mode or "miss"),
                        "gap_source": str(row.gap_source or ""),
                        "gap_level": str(row.gap_level),
                        "gap_distance_pct": str(row.gap_distance_pct),
                        "state_transition_type": str((row.role_tags or {}).get("transition_type", "")),
                        "state_transition_confidence": str((row.role_tags or {}).get("transition_confidence", "0")),
                        "trigger_flags": list((row.role_tags or {}).get("trigger_flags", []) or []),
                    },
                    evidence_json={
                        "kept_because": row.kept_because,
                        "prune_mode": row.prune_mode,
                        "prune_reason_code": row.prune_reason_code,
                        "removed_reason": row.removed_reason,
                    },
                )
            )
        return rows
