from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence


@dataclass(frozen=True)
class SubjectCycleEvidence:
    subject_key: str
    subject_name: str
    previous_cycle_state: str
    event_strength_score: Decimal
    event_continuity_score: Decimal
    strong_event_count_7d: int
    event_recency_days: int | None
    leader_alive_score: Decimal
    leader_breakdown_flag: bool
    relay_strength_score: Decimal
    front_row_survival_ratio: Decimal
    limit_up_count: int
    limit_down_count: int
    red_ratio: Decimal
    big_drop_ratio: Decimal
    front_row_strength_score: Decimal
    theme_support_score: Decimal
    break_start_pivot: bool = False


class SubjectCycleEvidenceBuilder:
    def build_many(self, stock_evidences: list[CycleEvidence]) -> list[SubjectCycleEvidence]:
        by_subject: dict[str, list[CycleEvidence]] = defaultdict(list)
        for e in stock_evidences:
            by_subject[e.subject_key].append(e)

        out: list[SubjectCycleEvidence] = []
        for subject_key, rows in by_subject.items():
            rows_sorted = sorted(rows, key=lambda x: x.leader_score, reverse=True)
            n = max(len(rows_sorted), 1)
            prev_state = rows_sorted[0].previous_state if rows_sorted else "unknown"
            event_recency_days = 1 if rows_sorted else None

            limit_up_count = sum(1 for r in rows_sorted if r.pct_chg >= Decimal("9.5"))
            limit_down_count = sum(1 for r in rows_sorted if r.pct_chg <= Decimal("-9.5"))
            red_ratio = Decimal(str(sum(1 for r in rows_sorted if r.pct_chg > 0) / n))
            big_drop_ratio = Decimal(str(sum(1 for r in rows_sorted if r.pct_chg <= Decimal("-5")) / n))

            front_rows = rows_sorted[: min(3, len(rows_sorted))]
            front_total = max(len(front_rows), 1)
            front_alive = sum(1 for r in front_rows if r.pct_chg >= 0 or r.leader_score >= Decimal("40"))
            front_row_survival_ratio = Decimal(str(front_alive / front_total))
            front_row_strength_score = sum((r.board_score for r in front_rows), start=Decimal("0")) / Decimal(
                str(front_total)
            )

            out.append(
                SubjectCycleEvidence(
                    subject_key=subject_key,
                    subject_name=rows_sorted[0].subject_name if rows_sorted else subject_key,
                    previous_cycle_state=prev_state,
                    event_strength_score=max((r.event_score for r in rows_sorted), default=Decimal("0")),
                    event_continuity_score=sum((r.continuity_score for r in rows_sorted), start=Decimal("0"))
                    / Decimal(str(n)),
                    strong_event_count_7d=sum(1 for r in rows_sorted if r.event_score >= Decimal("70")),
                    event_recency_days=event_recency_days,
                    leader_alive_score=max((r.leader_score for r in rows_sorted), default=Decimal("0")),
                    leader_breakdown_flag=any(r.pct_chg <= Decimal("-7") for r in front_rows),
                    relay_strength_score=sum((r.relay_score for r in rows_sorted), start=Decimal("0")) / Decimal(
                        str(n)
                    ),
                    front_row_survival_ratio=front_row_survival_ratio,
                    limit_up_count=limit_up_count,
                    limit_down_count=limit_down_count,
                    red_ratio=red_ratio,
                    big_drop_ratio=big_drop_ratio,
                    front_row_strength_score=front_row_strength_score,
                    theme_support_score=sum((r.support_score for r in rows_sorted), start=Decimal("0")) / Decimal(
                        str(n)
                    ),
                    break_start_pivot=False,
                )
            )
        return out

