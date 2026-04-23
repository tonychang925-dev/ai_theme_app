from __future__ import annotations

from dataclasses import replace

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
                prune_reason_code = "HARD_PRUNE_SUPPORT_BREAK" if support_break else "HARD_PRUNE_REJECT_GRADE"
                pruned.append(
                    replace(
                        row,
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code=prune_reason_code,
                        removed_reason=prune_reason_code.lower(),
                    )
                )
                continue

            if row.strong_grade == "B":
                weak_days = row.weak_days + 1
                if weak_days >= 3:
                    pruned.append(
                        replace(
                            row,
                            weak_days=weak_days,
                            watch_status="removed",
                            prune_mode="delayed",
                            prune_reason_code="DELAYED_PRUNE_WEAK_DAYS",
                            removed_reason="delayed_prune_weak_days",
                        )
                    )
                    continue
                kept.append(
                    replace(
                        row,
                        weak_days=weak_days,
                        watch_status="weakening",
                        prune_mode=None,
                        prune_reason_code=None,
                        removed_reason=None,
                    )
                )
                continue

            kept.append(replace(row, watch_status="active", prune_mode=None, prune_reason_code=None, removed_reason=None))
        return kept, pruned
