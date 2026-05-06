from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_admission_policy import StrongWatchAdmissionPolicy
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_refresh_service import (
    StrongWatchRecord,
    StrongWatchRefreshService,
)
from stock_processing_service.domain.services.strong_watch_history_service import (
    StrongWatchHistoryRecord,
    StrongWatchHistoryService,
)
from stock_processing_service.domain.services.strong_watch_roll_forward_service import (
    StrongWatchRollForwardService,
)
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService
from stock_processing_service.domain.services.strong_watch_universe import StrongWatchUniverseBuilder


@dataclass(frozen=True)
class StrongWatchShadowSummary:
    universe_formal_count: int
    universe_observe_count: int
    universe_blocked_count: int
    admission_formal_count: int
    admission_observe_count: int
    admission_reject_count: int
    admission_pass_4of3_fail_count: int
    admission_hard_reject_count: int
    source: str = "shadow_layer_c"


class StrongWatchService:
    def __init__(
        self,
        seed_service: StrongWatchSeedService | None = None,
        refresh_service: StrongWatchRefreshService | None = None,
        prune_service: StrongWatchPruneService | None = None,
        promote_service: StrongWatchPromoteService | None = None,
        roll_forward_service: StrongWatchRollForwardService | None = None,
        history_service: StrongWatchHistoryService | None = None,
        universe_builder: StrongWatchUniverseBuilder | None = None,
        admission_policy: StrongWatchAdmissionPolicy | None = None,
    ) -> None:
        self._seed_service = seed_service or StrongWatchSeedService()
        self._refresh_service = refresh_service or StrongWatchRefreshService()
        self._prune_service = prune_service or StrongWatchPruneService()
        self._promote_service = promote_service or StrongWatchPromoteService()
        self._roll_forward_service = roll_forward_service or StrongWatchRollForwardService()
        self._history_service = history_service or StrongWatchHistoryService()
        self._universe_builder = universe_builder or StrongWatchUniverseBuilder()
        self._admission_policy = admission_policy or StrongWatchAdmissionPolicy()

    def build_promoted_pool(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        prior_active_rows: list[StrongWatchRecord] | None = None,
        identities_by_subject: dict[str, Any] | None = None,
        cycles_by_subject: dict[str, Any] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord]]:
        promoted, kept, _history = self.build_promoted_pool_with_history(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
            prior_active_rows=prior_active_rows,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        return promoted, kept

    def build_promoted_pool_with_history(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        prior_active_rows: list[StrongWatchRecord] | None = None,
        identities_by_subject: dict[str, Any] | None = None,
        cycles_by_subject: dict[str, Any] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord], list[StrongWatchHistoryRecord]]:
        extracted_identities, extracted_cycles = self._require_layer_ab_inputs(
            pool_rows=pool_rows,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        universe = self._universe_builder.build_universe(
            pool_rows=pool_rows,
            identities_by_subject=extracted_identities,
            cycles_by_subject=extracted_cycles,
        )
        universe_kept_rows = [*universe.formal_rows, *universe.observe_rows]
        enriched_kept_rows = self._enrich_rows_with_universe_diag(
            universe_rows=universe_kept_rows,
            diagnostics=universe.diagnostics,
        )
        seeded = self._seed_service.seed(enriched_kept_rows)
        rolled = self._roll_forward_service.roll_forward(
            trade_date=trade_date,
            seeded_rows=seeded,
            prior_active_rows=prior_active_rows or [],
        )
        seeded_ids = {row.stock_id for row in seeded}
        carried_rows = [
            self._pool_row_from_rolled_record(
                trade_date=trade_date,
                row=row,
                identities_by_subject=extracted_identities,
                cycles_by_subject=extracted_cycles,
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
        # Merge lifecycle baselines so the pool is a rolling 7-trading-day watch list,
        # not only today's newly seeded strong stocks.
        baseline_by_stock = {r.stock_id: r for r in rolled}
        refreshed = [
            replace(
                r,
                weak_days=r.weak_days if r.stock_id in baseline_by_stock else 0,
                watch_age_days=r.watch_age_days if r.stock_id in baseline_by_stock else 1,
            )
            for r in refreshed
        ]
        subject_stats = self._subject_day_stats(pool_rows)
        bars_by_stock = {b.stock_id: b for b in bars}
        ranks = {r.stock_id: (r.pool_rank if r.pool_rank is not None else 999) for r in refresh_rows}

        admission_kept: list[StrongWatchRecord] = []
        admission_pruned: list[StrongWatchRecord] = []
        _admission_v2 = os.environ.get("LAYER_C_ADMISSION_V2", "1") == "1"
        for row in refreshed:
            if row.watch_status == "removed":
                admission_pruned.append(
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
            two_board_entry = bool(role_tags.get("two_board_entry") or False)

            if _admission_v2:
                # LAYER_C_ADMISSION_V2 is a migration gate only.
                # After 5 consecutive trading days of stable replay,
                # the old strong_grade admission path MUST be downgraded
                # to reference-only (no longer drives admission decisions).
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
                    two_board_entry=two_board_entry,
                    pct_chg=pct_chg,
                    support_type=str(row.support_type or ""),
                    support_score=row.support_score,
                    is_leader=bool(role_tags.get("is_leader") or False),
                    rank_order=row.pool_rank if row.pool_rank is not None else 999,
                )
                if decision.admission_status == "formal":
                    admission_kept.append(
                        replace(row, admission_status="formal")
                    )
                elif decision.admission_status == "observe_only":
                    admission_kept.append(
                        replace(
                            row,
                            watch_status="weakening",
                            kept_because="admission_v2_observe_only",
                            admission_status="observe_only",
                        )
                    )
                else:
                    admission_pruned.append(
                        replace(
                            row,
                            admission_status="reject",
                            watch_status="removed",
                            prune_mode="immediate",
                            prune_reason_code="ADMISSION_V2_REJECT",
                            removed_reason="admission_v2_reject",
                            kept_because=None,
                        )
                    )
            else:
                # Legacy path (LAYER_C_ADMISSION_V2=0): strong_grade + watch_score thresholds
                if row.strong_grade in {"S", "A"} and row.watch_score >= Decimal("78"):
                    admission_kept.append(
                        replace(row, admission_status="formal")
                    )
                elif two_board_entry and row.watch_status in {"active", "weakening"}:
                    admission_kept.append(
                        replace(
                            row,
                            watch_status="weakening",
                            kept_because="two_board_formal_bypass",
                            admission_status="observe_only",
                        )
                    )
                elif row.watch_status in {"active", "weakening"} and row.strong_grade in {"S", "A", "B"} and row.watch_score >= Decimal("62"):
                    admission_kept.append(
                        replace(
                            row,
                            watch_status="weakening",
                            kept_because="admission_observe_only",
                            admission_status="observe_only",
                        )
                    )
                else:
                    admission_pruned.append(
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

        kept, pruned_by_rule = self._prune_service.prune(admission_kept)
        pruned = admission_pruned + pruned_by_rule
        promoted = self._promote_service.promote(trade_date, kept)
        history_rows = self._history_service.build_history_snapshot(
            trade_date=trade_date,
            kept_rows=kept,
            pruned_rows=pruned,
        )
        return promoted, kept, history_rows

    @staticmethod
    def _enrich_rows_with_universe_diag(
        *,
        universe_rows: list[SubjectStockPoolDTO],
        diagnostics: dict[str, dict[str, Any]],
    ) -> list[SubjectStockPoolDTO]:
        out: list[SubjectStockPoolDTO] = []
        for row in universe_rows:
            md = dict(row.metadata or {})
            diag = diagnostics.get(row.stock_id) or {}
            md.setdefault("identity_status", str(diag.get("identity_status") or ""))
            md.setdefault("is_main_theme", bool(diag.get("is_main_theme") or False))
            md.setdefault("final_cycle_state", str(diag.get("final_cycle_state") or ""))
            md.setdefault("final_mainline_alive", bool(diag.get("final_mainline_alive") or False))
            md.setdefault("transition_type", str(diag.get("transition_type") or ""))
            md.setdefault("transition_confidence", str(diag.get("transition_confidence") or "0"))
            md.setdefault("trigger_flags", list(diag.get("trigger_flags") or []))
            md.setdefault("entry_path", str(diag.get("entry_path") or ""))
            out.append(replace(row, metadata=md))
        return out

    @staticmethod
    def _pool_row_from_rolled_record(
        *,
        trade_date: date,
        row: StrongWatchRecord,
        identities_by_subject: dict[str, Any],
        cycles_by_subject: dict[str, Any],
    ) -> SubjectStockPoolDTO:
        md = dict(row.role_tags or {})
        md.update(
            {
                "prior7_limitup_days": row.prior7_limitup_days,
                "prior7_strong_days": row.prior7_strong_days,
                "prior7_best_watch_score": str(row.prior7_best_watch_score),
                "prior7_peak_rank": row.prior7_peak_rank,
                "watch_age_days": row.watch_age_days,
                "support_type": row.support_type,
                "support_level": str(row.support_level),
                "support_score": str(row.support_score),
                "support_refs": list(row.support_refs or []),
                "support_count": row.support_count,
                "support_combined_strength": str(row.support_combined_strength),
                "gap_hit": row.gap_hit,
                "gap_hit_mode": row.gap_hit_mode,
                "gap_source": row.gap_source,
                "gap_level": str(row.gap_level),
                "gap_distance_pct": str(row.gap_distance_pct),
                "entry_path": str(md.get("entry_path") or "roll_forward"),
            }
        )
        cycle = cycles_by_subject.get(row.subject_key)
        if cycle is not None:
            if isinstance(cycle, dict):
                md["final_cycle_state"] = str(cycle.get("final_cycle_state") or md.get("final_cycle_state") or "")
                md["final_mainline_alive"] = bool(cycle.get("final_mainline_alive") or False)
                md["transition_type"] = str(cycle.get("transition_type") or md.get("transition_type") or "")
                md["transition_confidence"] = str(cycle.get("transition_confidence") or cycle.get("confidence") or md.get("transition_confidence") or "0")
                md["trigger_flags"] = list(cycle.get("trigger_flags") or md.get("trigger_flags") or [])
                md["fade_confirmed"] = bool(cycle.get("fade_confirmed") or False)
            else:
                md["final_cycle_state"] = str(getattr(cycle, "final_cycle_state", "") or md.get("final_cycle_state") or "")
                md["final_mainline_alive"] = bool(getattr(cycle, "final_mainline_alive", False))
                md["transition_type"] = str(getattr(cycle, "transition_type", "") or md.get("transition_type") or "")
                md["transition_confidence"] = str(getattr(cycle, "transition_confidence", md.get("transition_confidence", "0")) or "0")
                md["trigger_flags"] = list(getattr(cycle, "trigger_flags", []) or md.get("trigger_flags") or [])
                md["fade_confirmed"] = bool(getattr(cycle, "fade_confirmed", False))
        identity = identities_by_subject.get(row.subject_key)
        if identity is not None:
            if isinstance(identity, dict):
                md["identity_status"] = str(identity.get("identity_status") or md.get("identity_status") or "")
                md["is_main_theme"] = bool(identity.get("is_main_theme") or False)
            else:
                md["identity_status"] = str(getattr(identity, "identity_status", "") or md.get("identity_status") or "")
                md["is_main_theme"] = bool(getattr(identity, "is_main_theme", False))
        return SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key=row.subject_key,
            subject_name=row.subject_name,
            stock_id=row.stock_id,
            stock_name=row.stock_name,
            pool_rank=row.pool_rank,
            metadata=md,
        )

    @staticmethod
    def _require_layer_ab_inputs(
        *,
        pool_rows: list[SubjectStockPoolDTO],
        identities_by_subject: dict[str, Any] | None,
        cycles_by_subject: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if identities_by_subject is None or cycles_by_subject is None:
            raise ValueError("Layer A/B inputs are required: identities_by_subject and cycles_by_subject must be provided")
        subject_keys = {str(r.subject_key or "") for r in pool_rows if str(r.subject_key or "")}
        # Production semantics:
        # - Layer A/B must be present as authoritative inputs.
        # - Non-mainline subject_keys can be absent and should be explicitly blocked by UniverseBuilder.
        # - Only fail-fast when A/B are effectively unavailable for a non-empty universe.
        if subject_keys and (len(identities_by_subject) == 0 or len(cycles_by_subject) == 0):
            raise ValueError(
                "Layer A/B inputs incomplete: "
                f"identity_rows={len(identities_by_subject)}, "
                f"cycle_rows={len(cycles_by_subject)}, "
                f"pool_subject_keys={len(subject_keys)}"
            )
        return identities_by_subject, cycles_by_subject

    @staticmethod
    def _extract_identities_from_pool(pool_rows: list[SubjectStockPoolDTO]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in pool_rows:
            md = row.metadata if isinstance(row.metadata, dict) else {}
            sk = str(row.subject_key or "")
            if not sk:
                continue
            if sk in out:
                continue
            out[sk] = {
                "identity_status": str(md.get("identity_status") or ""),
                "is_main_theme": bool(md.get("is_main_theme") or False),
                "rule_version": str(md.get("identity_rule_version") or ""),
            }
        return out

    @staticmethod
    def _extract_cycles_from_pool(pool_rows: list[SubjectStockPoolDTO]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in pool_rows:
            md = row.metadata if isinstance(row.metadata, dict) else {}
            sk = str(row.subject_key or "")
            if not sk:
                continue
            if sk in out:
                continue
            out[sk] = {
                "final_cycle_state": str(md.get("final_cycle_state") or ""),
                "final_mainline_alive": bool(md.get("final_mainline_alive") or False),
                "fade_watch": bool(md.get("fade_watch") or False),
                "fade_confirmed": bool(md.get("fade_confirmed") or False),
            }
        return out

    @staticmethod
    def _subject_day_stats(pool_rows: list[SubjectStockPoolDTO]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for row in pool_rows:
            sk = str(row.subject_key or "")
            if not sk:
                continue
            md = row.metadata if isinstance(row.metadata, dict) else {}
            s = stats.setdefault(sk, {"subject_limit_up_count": 0, "subject_strong_count": 0})
            if bool(md.get("limit_up") or False):
                s["subject_limit_up_count"] += 1
            rank = row.pool_rank if row.pool_rank is not None else 999
            pct = Decimal(str(md.get("pct_chg") or "0"))
            if bool(md.get("limit_up") or False) or bool(md.get("is_leader") or False) or rank <= 3 or pct >= Decimal("7"):
                s["subject_strong_count"] += 1
        return stats

    def _build_shadow_summary(
        self,
        *,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        identities_by_subject: dict[str, Any] | None = None,
        cycles_by_subject: dict[str, Any] | None = None,
    ) -> StrongWatchShadowSummary:
        identities, cycles = self._require_layer_ab_inputs(
            pool_rows=pool_rows,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        universe = self._universe_builder.build_universe(
            pool_rows=pool_rows,
            identities_by_subject=identities,
            cycles_by_subject=cycles,
        )
        universe_kept_rows = [*universe.formal_rows, *universe.observe_rows]
        enriched_kept_rows = self._enrich_rows_with_universe_diag(
            universe_rows=universe_kept_rows,
            diagnostics=universe.diagnostics,
        )

        if not universe_kept_rows:
            return StrongWatchShadowSummary(
                universe_formal_count=universe.formal_count,
                universe_observe_count=universe.observe_count,
                universe_blocked_count=universe.blocked_count,
                admission_formal_count=0,
                admission_observe_count=0,
                admission_reject_count=0,
                admission_pass_4of3_fail_count=0,
                admission_hard_reject_count=0,
            )

        seeded = self._seed_service.seed(enriched_kept_rows)
        refreshed = self._refresh_service.refresh(
            seeded_rows=seeded,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )

        subject_stats = self._subject_day_stats(pool_rows)
        bars_by_stock = {b.stock_id: b for b in bars}

        # Use AdmissionPolicy V2 (same as main chain) for shadow audit.
        admission_formal = 0
        admission_observe = 0
        admission_reject = 0
        admission_pass_4of3_fail = 0
        admission_hard_reject = 0

        for row in refreshed:
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
            if decision.admission_status == "formal":
                admission_formal += 1
            elif decision.admission_status == "observe_only":
                admission_observe += 1
            else:
                admission_reject += 1
            if decision.pass_count_4of3 < 3:
                admission_pass_4of3_fail += 1
            if decision.reject_no_limitup_gene or decision.reject_isolated_theme or decision.reject_break_support_with_heavy_drop:
                admission_hard_reject += 1

        return StrongWatchShadowSummary(
            universe_formal_count=universe.formal_count,
            universe_observe_count=universe.observe_count,
            universe_blocked_count=universe.blocked_count,
            admission_formal_count=admission_formal,
            admission_observe_count=admission_observe,
            admission_reject_count=admission_reject,
            admission_pass_4of3_fail_count=admission_pass_4of3_fail,
            admission_hard_reject_count=admission_hard_reject,
        )

    def build_promoted_pool_with_history_and_shadow(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        prior_active_rows: list[StrongWatchRecord] | None = None,
        identities_by_subject: dict[str, Any] | None = None,
        cycles_by_subject: dict[str, Any] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord], list[StrongWatchHistoryRecord], StrongWatchShadowSummary]:
        promoted, kept, history_rows = self.build_promoted_pool_with_history(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
            prior_active_rows=prior_active_rows,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        shadow = self._build_shadow_summary(
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
            identities_by_subject=identities_by_subject,
            cycles_by_subject=cycles_by_subject,
        )
        return promoted, kept, history_rows, shadow

    @staticmethod
    def is_candidate_eligible(
        *,
        watch_status: str,
        pool_entry_type: str,
        candidate_source: str = "strong_watch_pool",
    ) -> bool:
        """
        Layer C -> D single outlet contract.
        Only rows explicitly in strong_watch_pool source and in the active/weakening
        lifecycle with formal/observe_only entry can flow into D1.
        """
        if str(candidate_source or "").strip().lower() != "strong_watch_pool":
            return False
        if str(watch_status or "").strip().lower() not in {"active", "weakening"}:
            return False
        if str(pool_entry_type or "").strip().lower() not in {"formal", "observe_only"}:
            return False
        return True
