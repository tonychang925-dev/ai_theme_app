from __future__ import annotations

from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPruneService:
    def prune(self, rows: list[StrongWatchRecord]) -> tuple[list[StrongWatchRecord], list[StrongWatchRecord]]:
        kept: list[StrongWatchRecord] = []
        pruned: list[StrongWatchRecord] = []
        for row in rows:
            # Two-stage prune:
            # 1) immediate prune for hard reject grade or severe support break.
            # 2) delayed prune for weakening rows after weak_days threshold.
            support_break = row.support_score < 35
            if row.strong_grade == "REJECT" or support_break:
                pruned.append(
                    StrongWatchRecord(
                        **{
                            **row.__dict__,
                            "watch_status": "removed",
                            "prune_reason_code": "HARD_PRUNE_SUPPORT_BREAK" if support_break else "HARD_PRUNE_REJECT_GRADE",
                        }
                    )
                )
                continue

            if row.strong_grade == "B":
                weak_days = row.weak_days + 1
                if weak_days >= 3:
                    pruned.append(
                        StrongWatchRecord(
                            **{
                                **row.__dict__,
                                "weak_days": weak_days,
                                "watch_status": "removed",
                                "prune_reason_code": "DELAYED_PRUNE_WEAK_DAYS",
                            }
                        )
                    )
                    continue
                kept.append(
                    StrongWatchRecord(
                        **{
                            **row.__dict__,
                            "weak_days": weak_days,
                            "watch_status": "weakening",
                        }
                    )
                )
                continue

            kept.append(
                StrongWatchRecord(
                    **{
                        **row.__dict__,
                        "watch_status": "active",
                    }
                )
            )
        return kept, pruned
