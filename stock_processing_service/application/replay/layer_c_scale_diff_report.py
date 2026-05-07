from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob
from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_admission_policy import StrongWatchAdmissionPolicy
from stock_processing_service.domain.services.strong_watch_history_service import StrongWatchHistoryRecord
from stock_processing_service.domain.services.strong_watch_history_service import StrongWatchHistoryService
from stock_processing_service.domain.services.strong_watch_preseed_gene_enricher import StrongWatchPreSeedGeneEnricher
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord, StrongWatchRefreshService
from stock_processing_service.domain.services.strong_watch_roll_forward_service import StrongWatchRollForwardService
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService
from stock_processing_service.domain.services.strong_watch_service import StrongWatchService
from stock_processing_service.domain.services.strong_watch_universe import StrongWatchUniverseBuilder
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService


@dataclass(frozen=True)
class LayerCScaleDiffReport:
    trade_date: str
    target_stock_id: str
    pipeline_counts: dict[str, Any]
    seven_day_history_counts: list[dict[str, Any]]
    admission_counts: dict[str, int]
    prune_counts: dict[str, int]
    promote_counts: dict[str, int]
    d_layer_counts: dict[str, int]
    target: dict[str, Any]
    top_observe_candidates: list[dict[str, Any]]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LayerCScaleDiffReportBuilder:
    """Read-only Layer C/D scale diagnostic.

    The builder mirrors the StrongWatch pipeline stage by stage so replay
    diagnostics can show where the pool expands before D ranking.
    """

    def __init__(
        self,
        *,
        preseed_gene_enricher: StrongWatchPreSeedGeneEnricher | None = None,
        universe_builder: StrongWatchUniverseBuilder | None = None,
        seed_service: StrongWatchSeedService | None = None,
        roll_forward_service: StrongWatchRollForwardService | None = None,
        refresh_service: StrongWatchRefreshService | None = None,
        admission_policy: StrongWatchAdmissionPolicy | None = None,
        prune_service: StrongWatchPruneService | None = None,
        promote_service: StrongWatchPromoteService | None = None,
        history_service: StrongWatchHistoryService | None = None,
        candidate_service: W2SCandidateService | None = None,
    ) -> None:
        self._preseed_gene_enricher = preseed_gene_enricher or StrongWatchPreSeedGeneEnricher()
        self._universe_builder = universe_builder or StrongWatchUniverseBuilder()
        self._seed_service = seed_service or StrongWatchSeedService()
        self._roll_forward_service = roll_forward_service or StrongWatchRollForwardService()
        self._refresh_service = refresh_service or StrongWatchRefreshService()
        self._admission_policy = admission_policy or StrongWatchAdmissionPolicy()
        self._prune_service = prune_service or StrongWatchPruneService()
        self._promote_service = promote_service or StrongWatchPromoteService()
        self._history_service = history_service or StrongWatchHistoryService()
        self._candidate_service = candidate_service or W2SCandidateService()

    def build(
        self,
        *,
        trade_date: date,
        target_stock_id: str,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO],
        prior_watch_rows: list[SubjectStockPoolDTO],
        identities_by_subject: dict[str, Any],
        cycles_by_subject: dict[str, Any],
    ) -> LayerCScaleDiffReport:
        notes: list[str] = []
        stock_id = str(target_stock_id).strip().upper()
        preseed_rows = self._preseed_gene_enricher.enrich(
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )
        universe = self._universe_builder.build_universe(
            pool_rows=preseed_rows,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        universe_kept = [*universe.formal_rows, *universe.observe_rows]
        enriched_kept = StrongWatchService._enrich_rows_with_universe_diag(
            universe_rows=universe_kept,
            diagnostics=universe.diagnostics,
        )
        seeded = self._seed_service.seed(enriched_kept)
        prior_active_rows = BuildPostMarketRecapJob._build_prior_active_strong_watch_records(prior_watch_rows)
        rolled = self._roll_forward_service.roll_forward(
            trade_date=trade_date,
            seeded_rows=seeded,
            prior_active_rows=prior_active_rows,
        )
        seeded_ids = {row.stock_id for row in seeded}
        carried_rows = [
            StrongWatchService._pool_row_from_rolled_record(
                trade_date=trade_date,
                row=row,
                identities_by_subject=identities_by_subject,
                cycles_by_subject=cycles_by_subject,
            )
            for row in rolled
            if row.stock_id not in seeded_ids
        ]
        refresh_rows = [*seeded, *carried_rows]
        refreshed = self._refresh_service.refresh(
            refresh_rows,
            bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )
        refreshed = self._merge_roll_forward_baseline(refreshed=refreshed, rolled=rolled)
        admission_kept, admission_pruned, admission_counts = self._apply_admission(
            preseed_rows=preseed_rows,
            refreshed=refreshed,
            bars=bars,
        )
        kept, pruned_by_rule = self._prune_service.prune(admission_kept)
        pruned = [*admission_pruned, *pruned_by_rule]
        promoted = self._promote_service.promote(trade_date, kept)
        history_rows = self._history_service.build_history_snapshot(
            trade_date=trade_date,
            kept_rows=kept,
            pruned_rows=pruned,
        )
        candidate_input_rows = BuildPostMarketRecapJob._build_candidate_input_rows(
            trade_date=trade_date,
            strong_watch_rows=kept,
            promoted_pool_rows=promoted,
            prior_watch_rows=prior_watch_rows,
        )
        candidates = self._candidate_service.build_candidates(
            bars=bars,
            pool_rows=candidate_input_rows,
            prior_rows=prior_rows,
        )
        all_candidates = list(getattr(self._candidate_service, "all_candidates", candidates))
        formal_candidates = [
            c for c in all_candidates if str(getattr(c, "candidate_level", "")).lower() in {"formal", "s", "a", "b"}
        ]
        observe_candidates = [
            c for c in all_candidates if str(getattr(c, "candidate_level", "")).lower() == "observe_only"
        ]

        if len(universe.diagnostics) < len(preseed_rows):
            notes.append("universe_diagnostics_keyed_by_stock_id_may_collapse_duplicate_subject_rows")
        if len({r.stock_id for r in preseed_rows}) < len(preseed_rows):
            notes.append("subject_pool_contains_duplicate_stock_across_subjects")

        return LayerCScaleDiffReport(
            trade_date=trade_date.isoformat(),
            target_stock_id=stock_id,
            pipeline_counts={
                "subject_pool_rows": len(pool_rows),
                "subject_pool_unique_stocks": len({r.stock_id for r in pool_rows if r.stock_id}),
                "subject_pool_subject_keys": len({r.subject_key for r in pool_rows if r.subject_key}),
                "universe_formal": len(universe.formal_rows),
                "universe_observe": len(universe.observe_rows),
                "universe_blocked": len(universe.blocked_rows),
                "seeded": len(seeded),
                "prior_active_rows": len(prior_active_rows),
                "rolled": len(rolled),
                "carried_from_prior": len(carried_rows),
                "refresh_rows": len(refresh_rows),
                "refreshed": len(refreshed),
                "admission_kept": len(admission_kept),
                "admission_pruned": len(admission_pruned),
                "prune_kept": len(kept),
                "prune_removed": len(pruned),
                "promoted": len(promoted),
                "strong_watch_history_rows": len(history_rows),
                "strong_watch_input_7d_count": len(candidate_input_rows),
            },
            seven_day_history_counts=self._seven_day_history_counts(
                prior_watch_rows=prior_watch_rows,
                current_history_rows=history_rows,
            ),
            admission_counts=admission_counts,
            prune_counts=self._prune_counts(pruned),
            promote_counts=self._promote_counts(promoted),
            d_layer_counts={
                "all_candidates": len(all_candidates),
                "formal_candidates": len(formal_candidates),
                "observe_candidates": len(observe_candidates),
                "returned_candidates": len(candidates),
                "observe_top_n": len(self._candidate_service.observe_candidates),
            },
            target=self._target_summary(
                stock_id=stock_id,
                pool_rows=pool_rows,
                preseed_rows=preseed_rows,
                universe_rows=universe_kept,
                universe_diagnostics=universe.diagnostics,
                seeded=seeded,
                rolled=rolled,
                refreshed=refreshed,
                kept=kept,
                promoted=promoted,
                candidate_input_rows=candidate_input_rows,
                all_candidates=all_candidates,
                observe_candidates=observe_candidates,
            ),
            top_observe_candidates=[
                self._candidate_summary(c, idx)
                for idx, c in enumerate(observe_candidates[:20], start=1)
            ],
            notes=notes,
        )

    @staticmethod
    def _merge_roll_forward_baseline(
        *,
        refreshed: list[StrongWatchRecord],
        rolled: list[StrongWatchRecord],
    ) -> list[StrongWatchRecord]:
        from dataclasses import replace

        baseline_by_stock = {r.stock_id: r for r in rolled}
        out: list[StrongWatchRecord] = []
        for row in refreshed:
            baseline = baseline_by_stock.get(row.stock_id)
            if baseline is None:
                out.append(replace(row, watch_age_days=int(row.watch_age_days or 1), weak_days=int(row.weak_days or 0)))
                continue
            role_tags = row.role_tags if isinstance(row.role_tags, dict) else {}
            renewal_signal = bool(role_tags.get("renewal_signal") or role_tags.get("watch_age_reset") or False)
            if renewal_signal and row.watch_status in {"active", "weakening"}:
                out.append(replace(row, watch_age_days=int(row.watch_age_days or 1), weak_days=int(row.weak_days or 0)))
            else:
                out.append(
                    replace(
                        row,
                        watch_age_days=int(baseline.watch_age_days or 1),
                        weak_days=int(baseline.weak_days or 0),
                    )
                )
        return out

    def _apply_admission(
        self,
        *,
        preseed_rows: list[SubjectStockPoolDTO],
        refreshed: list[StrongWatchRecord],
        bars: list[StockBarDTO],
    ) -> tuple[list[StrongWatchRecord], list[StrongWatchRecord], dict[str, int]]:
        from dataclasses import replace

        subject_stats = StrongWatchService._subject_day_stats(preseed_rows)
        bars_by_stock = {b.stock_id: b for b in bars}
        kept: list[StrongWatchRecord] = []
        pruned: list[StrongWatchRecord] = []
        counts = {
            "formal": 0,
            "observe_only": 0,
            "reject": 0,
            "pass_4of3_fail": 0,
            "hard_reject": 0,
            "removed_before_admission": 0,
        }
        for row in refreshed:
            if row.watch_status == "removed":
                counts["reject"] += 1
                counts["removed_before_admission"] += 1
                pruned.append(
                    replace(
                        row,
                        admission_status="reject",
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code="WATCH_SCORE_REJECT",
                        removed_reason="watch_score_reject",
                        kept_because=None,
                    )
                )
                continue
            role_tags = row.role_tags if isinstance(row.role_tags, dict) else {}
            bar = bars_by_stock.get(row.stock_id)
            pct_chg = bar.pct_chg if bar else Decimal("0")
            stats = subject_stats.get(row.subject_key, {})
            decision = self._admission_policy.assess(
                prior7_limitup_days=row.prior7_limitup_days,
                recent_limit_up_count=int(role_tags.get("recent_limit_up_count") or 0),
                subject_limit_up_count=stats.get("subject_limit_up_count", 0),
                subject_strong_count=stats.get("subject_strong_count", 0),
                final_mainline_alive=bool(role_tags.get("final_mainline_alive") or False),
                board_effect_confirmed=bool(role_tags.get("board_effect_confirmed") or False),
                two_board_entry=bool(role_tags.get("two_board_entry") or False),
                pct_chg=pct_chg,
                support_type=str(row.support_type or ""),
                support_score=row.support_score,
                is_leader=bool(role_tags.get("is_leader") or False),
                rank_order=row.pool_rank if row.pool_rank is not None else 999,
            )
            counts[decision.admission_status] += 1
            if decision.pass_count_4of3 < 3:
                counts["pass_4of3_fail"] += 1
            if decision.reject_no_limitup_gene or decision.reject_isolated_theme or decision.reject_break_support_with_heavy_drop:
                counts["hard_reject"] += 1
            if decision.admission_status == "formal":
                kept.append(replace(row, admission_status="formal"))
            elif decision.admission_status == "observe_only":
                kept.append(
                    replace(
                        row,
                        watch_status="weakening",
                        kept_because="admission_observe_only",
                        admission_status="observe_only",
                    )
                )
            else:
                pruned.append(
                    replace(
                        row,
                        admission_status="reject",
                        watch_status="removed",
                        prune_mode="immediate",
                        prune_reason_code="ADMISSION_REJECT",
                        removed_reason="admission_reject",
                        kept_because=None,
                    )
                )
        return kept, pruned, counts

    @staticmethod
    def _seven_day_history_counts(
        *,
        prior_watch_rows: list[SubjectStockPoolDTO],
        current_history_rows: list[StrongWatchHistoryRecord],
    ) -> list[dict[str, Any]]:
        by_date: dict[str, dict[str, Any]] = {}

        def ensure(day: Any) -> dict[str, Any]:
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            return by_date.setdefault(
                key,
                {
                    "trade_date": key,
                    "active": 0,
                    "weakening": 0,
                    "formal": 0,
                    "observe_only": 0,
                    "removed": 0,
                    "total_kept": 0,
                    "total_rows": 0,
                },
            )

        for row in prior_watch_rows:
            md = getattr(row, "metadata", {}) or {}
            item = ensure(getattr(row, "trade_date", ""))
            status = str(md.get("watch_status") or "").lower()
            entry = str(md.get("pool_entry_type") or "").lower()
            LayerCScaleDiffReportBuilder._inc_history(item, status=status, entry=entry)
        for row in current_history_rows:
            item = ensure(row.trade_date)
            LayerCScaleDiffReportBuilder._inc_history(
                item,
                status=str(row.watch_status or "").lower(),
                entry=str(row.pool_entry_type or "").lower(),
            )
        return [by_date[key] for key in sorted(by_date)]

    @staticmethod
    def _inc_history(item: dict[str, Any], *, status: str, entry: str) -> None:
        item["total_rows"] += 1
        if status == "active":
            item["active"] += 1
            item["total_kept"] += 1
        elif status == "weakening":
            item["weakening"] += 1
            item["total_kept"] += 1
        elif status == "removed":
            item["removed"] += 1
        if entry == "formal":
            item["formal"] += 1
        elif entry == "observe_only":
            item["observe_only"] += 1

    @staticmethod
    def _prune_counts(pruned: list[StrongWatchRecord]) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in pruned:
            key = str(row.prune_reason_code or row.removed_reason or "unknown")
            out[key] = out.get(key, 0) + 1
        return out

    @staticmethod
    def _promote_counts(promoted: list[SubjectStockPoolDTO]) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in promoted:
            md = getattr(row, "metadata", {}) or {}
            key = str(md.get("promote_bucket") or "unknown")
            out[key] = out.get(key, 0) + 1
        return out

    @staticmethod
    def _rank(stock_id: str, rows: list[Any]) -> int | None:
        target = stock_id.strip().upper()
        for idx, row in enumerate(rows, start=1):
            if str(getattr(row, "stock_id", "") or "").strip().upper() == target:
                return idx
        return None

    @classmethod
    def _target_rows(cls, stock_id: str, rows: list[Any]) -> list[Any]:
        target = stock_id.strip().upper()
        return [row for row in rows if str(getattr(row, "stock_id", "") or "").strip().upper() == target]

    @classmethod
    def _target_summary(
        cls,
        *,
        stock_id: str,
        pool_rows: list[SubjectStockPoolDTO],
        preseed_rows: list[SubjectStockPoolDTO],
        universe_rows: list[SubjectStockPoolDTO],
        universe_diagnostics: dict[str, dict[str, Any]],
        seeded: list[SubjectStockPoolDTO],
        rolled: list[StrongWatchRecord],
        refreshed: list[StrongWatchRecord],
        kept: list[StrongWatchRecord],
        promoted: list[SubjectStockPoolDTO],
        candidate_input_rows: list[SubjectStockPoolDTO],
        all_candidates: list[Any],
        observe_candidates: list[Any],
    ) -> dict[str, Any]:
        target_preseed = cls._target_rows(stock_id, preseed_rows)
        target_seeded = cls._target_rows(stock_id, seeded)
        target_promoted = cls._target_rows(stock_id, promoted)
        candidate_rows = cls._target_rows(stock_id, all_candidates)
        best_candidate = candidate_rows[0] if candidate_rows else None
        promoted_row = target_promoted[0] if target_promoted else None
        promoted_md = getattr(promoted_row, "metadata", {}) or {} if promoted_row is not None else {}
        return {
            "pool_presence_count": len(cls._target_rows(stock_id, pool_rows)),
            "pool_rows": [cls._pool_row_summary(r) for r in cls._target_rows(stock_id, pool_rows)],
            "preseed_rows": [cls._pool_row_summary(r) for r in target_preseed],
            "universe_rows": [cls._pool_row_summary(r) for r in cls._target_rows(stock_id, universe_rows)],
            "universe_diagnostic": universe_diagnostics.get(stock_id) or {},
            "seeded_rows": [cls._pool_row_summary(r) for r in target_seeded],
            "rolled_rank": cls._rank(stock_id, rolled),
            "refreshed_rank": cls._rank(stock_id, refreshed),
            "kept_rank": cls._rank(stock_id, kept),
            "promoted_rank": cls._rank(stock_id, promoted),
            "candidate_input_rank": cls._rank(stock_id, candidate_input_rows),
            "candidate_rank": cls._rank(stock_id, all_candidates),
            "observe_rank": cls._rank(stock_id, observe_candidates),
            "candidate_level": getattr(best_candidate, "candidate_level", None) if best_candidate else None,
            "candidate_score": str(getattr(best_candidate, "candidate_score", "")) if best_candidate else None,
            "support_type": (
                str(getattr(best_candidate, "support_type", ""))
                if best_candidate
                else str(promoted_md.get("support_type") or "")
            ),
            "support_score": (
                str(getattr(best_candidate, "support_score", ""))
                if best_candidate
                else str(promoted_md.get("support_score") or "")
            ),
            "promote_bucket": str(promoted_md.get("promote_bucket") or ""),
            "promote_reason": str(promoted_md.get("promote_reason") or ""),
        }

    @staticmethod
    def _pool_row_summary(row: SubjectStockPoolDTO) -> dict[str, Any]:
        md = getattr(row, "metadata", {}) or {}
        role_tags = md.get("role_tags") if isinstance(md.get("role_tags"), dict) else {}
        return {
            "subject_key": row.subject_key,
            "subject_name": row.subject_name,
            "pool_rank": row.pool_rank,
            "pct_chg": str(md.get("pct_chg") or ""),
            "limit_up": bool(md.get("limit_up") or False),
            "is_leader": bool(md.get("is_leader") or role_tags.get("is_leader") or False),
            "entry_path": str(md.get("entry_path") or ""),
            "seed_gate_pass": md.get("seed_gate_pass"),
            "seed_gate_reason": md.get("seed_gate_reason"),
            "strong_gene_seed": bool(md.get("strong_gene_seed") or False),
            "strong_gene_seed_reason": str(md.get("strong_gene_seed_reason") or ""),
            "two_board_entry": bool(md.get("two_board_entry") or role_tags.get("two_board_entry") or False),
            "admission_status": str(md.get("admission_status") or ""),
            "promote_bucket": str(md.get("promote_bucket") or ""),
        }

    @staticmethod
    def _candidate_summary(candidate: Any, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "stock_id": candidate.stock_id,
            "stock_name": candidate.stock_name,
            "subject_key": candidate.subject_key,
            "subject_name": candidate.subject_name,
            "candidate_level": candidate.candidate_level,
            "candidate_score": str(candidate.candidate_score),
            "support_type": candidate.support_type,
            "support_score": str(candidate.support_score),
            "weakness_valid_score": str(candidate.weakness_valid_score),
            "strong_gene_score": str(getattr(candidate, "strong_gene_score", "")),
            "repair_or_takeover_score": str(candidate.repair_or_takeover_score),
        }
