from __future__ import annotations

from dataclasses import replace

from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPruneService:
    OBSERVE_KEEP_MIN_SCORE = 42

    def prune(self, rows: list[StrongWatchRecord]) -> tuple[list[StrongWatchRecord], list[StrongWatchRecord]]:
        kept: list[StrongWatchRecord] = []
        pruned: list[StrongWatchRecord] = []
        for row in rows:
            role_tags = row.role_tags if isinstance(row.role_tags, dict) else {}
            final_cycle_state = str(role_tags.get("final_cycle_state") or "").lower()
            fade_confirmed = bool(role_tags.get("fade_confirmed") or final_cycle_state == "fade_confirmed")
            if fade_confirmed:
                pruned.append(
                    replace(
                        row,
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code="HARD_PRUNE_FADE_CONFIRMED",
                        removed_reason="hard_prune_fade_confirmed",
                        kept_because=None,
                    )
                )
                continue
            if str(getattr(row, "admission_status", "formal") or "formal") == "reject":
                pruned.append(
                    replace(
                        row,
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code="ADMISSION_REJECT",
                        removed_reason="admission_reject",
                        kept_because=None,
                    )
                )
                continue
            if str(getattr(row, "admission_status", "formal") or "formal") == "observe_only":
                if row.watch_score < self.OBSERVE_KEEP_MIN_SCORE:
                    pruned.append(
                        replace(
                            row,
                            watch_status="removed",
                            prune_mode="immediate",
                            prune_reason_code="HARD_PRUNE_OBSERVE_LOW_SCORE",
                            removed_reason="hard_prune_observe_low_score",
                            kept_because=None,
                        )
                    )
                    continue
                weak_days = row.weak_days + 1
                if weak_days >= 5:
                    pruned.append(
                        replace(
                            row,
                            weak_days=weak_days,
                            watch_status="removed",
                            prune_mode="delayed",
                            prune_reason_code="DELAYED_PRUNE_OBSERVE_ONLY_EXPIRE",
                            removed_reason="delayed_prune_observe_only_expire",
                            kept_because=None,
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
                        kept_because=row.kept_because or "admission_observe_only",
                    )
                )
                continue
            has_prior7_gene = row.prior7_limitup_days >= 1 or row.prior7_strong_days >= 2
            support_ok = row.support_score >= 55
            immediate_prune = (
                row.strong_gene_score < 25
                or row.support_score < 35
                or row.weakness_tolerance_score < 20
                or (row.strong_grade == "REJECT" and not (has_prior7_gene and support_ok))
            )
            if immediate_prune:
                if row.strong_gene_score < 25:
                    prune_reason_code = "HARD_PRUNE_WEAK_GENE"
                elif row.support_score < 35:
                    prune_reason_code = "HARD_PRUNE_SUPPORT_BREAK"
                elif row.weakness_tolerance_score < 20:
                    prune_reason_code = "HARD_PRUNE_INVALID_WEAK"
                else:
                    prune_reason_code = "HARD_PRUNE_REJECT_GRADE"
                pruned.append(
                    replace(
                        row,
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code=prune_reason_code,
                        removed_reason=prune_reason_code.lower(),
                        kept_because=None,
                    )
                )
                continue

            keep_observe_bucket = row.strong_grade in {"B_KEEP", "B"} and has_prior7_gene and support_ok
            if keep_observe_bucket:
                weak_days = row.weak_days + 1
                if weak_days >= 5:
                    pruned.append(
                        replace(
                            row,
                            weak_days=weak_days,
                            watch_status="removed",
                            prune_mode="delayed",
                            prune_reason_code="DELAYED_PRUNE_WEAKENING_KEEP_EXPIRE",
                            removed_reason="delayed_prune_weakening_keep_expire",
                            kept_because=None,
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
                        kept_because="weakening_keep_gene_and_support",
                    )
                )
                continue

            kept.append(
                replace(
                    row,
                    watch_status="active",
                    prune_mode=None,
                    prune_reason_code=None,
                    removed_reason=None,
                    kept_because=None,
                )
            )
        return kept, pruned
