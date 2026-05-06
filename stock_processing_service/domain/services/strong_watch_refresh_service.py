from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer


@dataclass(frozen=True)
class StrongWatchRecord:
    stock_id: str
    stock_name: str
    subject_key: str
    subject_name: str
    pool_rank: int | None
    watch_score: Decimal
    strong_grade: str
    support_type: str
    support_level: Decimal
    support_score: Decimal
    support_refs: list[str] = field(default_factory=list)
    support_count: int = 0
    support_combined_strength: Decimal = Decimal("0")
    gap_hit: bool = False
    gap_hit_mode: str = "miss"
    gap_source: str = ""
    gap_level: Decimal = Decimal("0")
    gap_distance_pct: Decimal = Decimal("999")
    role_tags: dict[str, Any] = field(default_factory=dict)
    watch_status: str = "active"
    watch_age_days: int = 1
    weak_days: int = 0
    prune_reason_code: str | None = None
    prune_mode: str | None = None
    removed_reason: str | None = None
    source: str = "strong_watch_pool"
    mainline_context_score: Decimal = Decimal("0")
    strong_gene_score: Decimal = Decimal("0")
    weakness_tolerance_score: Decimal = Decimal("0")
    prior7_limitup_days: int = 0
    prior7_strong_days: int = 0
    prior7_best_watch_score: Decimal = Decimal("0")
    prior7_peak_rank: int = 99
    kept_because: str | None = None
    admission_status: str = "formal"


class StrongWatchRefreshService:
    ACTIVE_MIN_SCORE = Decimal("72")
    WEAKENING_MIN_SCORE = Decimal("62")

    def __init__(self, support_scorer: KlineSupportScorer | None = None) -> None:
        self._support_scorer = support_scorer or KlineSupportScorer()

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _in_range(value: Decimal, low: str, high: str) -> bool:
        return Decimal(low) <= value <= Decimal(high)

    def _weakness_tolerance_score(self, pct_chg: Decimal) -> Decimal:
        # Weak-to-strong upstream should tolerate pullback and neutral days,
        # while avoiding overheating and extreme breakdown.
        if self._in_range(pct_chg, "-5", "-1"):
            return Decimal("92")
        if self._in_range(pct_chg, "-1", "2"):
            return Decimal("76")
        if self._in_range(pct_chg, "2", "4"):
            return Decimal("56")
        if pct_chg > Decimal("4"):
            return Decimal("36")
        if self._in_range(pct_chg, "-8", "-5"):
            return Decimal("52")
        return Decimal("24")

    def _mainline_context_score(self, rank: int, metadata: dict[str, Any]) -> Decimal:
        rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
        role_tags = metadata.get("role_tags") if isinstance(metadata.get("role_tags"), dict) else {}
        leader_bonus = Decimal("14") if bool(role_tags.get("is_leader")) else Decimal("0")
        front_row_bonus = Decimal("8") if bool(role_tags.get("is_front_row_core")) else Decimal("0")
        return min(Decimal("100"), rank_score * Decimal("0.72") + leader_bonus + front_row_bonus)

    def _prior7_features(
        self,
        *,
        stock_id: str,
        metadata: dict[str, Any],
        prior_rows_by_stock: dict[str, list[PriorSnapshotDTO]],
    ) -> tuple[int, int, Decimal, int]:
        m_limit = metadata.get("prior7_limitup_days")
        m_strong = metadata.get("prior7_strong_days")
        m_best_watch = metadata.get("prior7_best_watch_score")
        m_peak_rank = metadata.get("prior7_peak_rank")
        if m_limit is not None or m_strong is not None or m_best_watch is not None or m_peak_rank is not None:
            return (
                int(m_limit or 0),
                int(m_strong or 0),
                self._d(m_best_watch),
                int(m_peak_rank or 99),
            )

        rows = prior_rows_by_stock.get(stock_id, [])
        limitup_days = 0
        strong_days = 0
        best_watch_score = Decimal("0")
        peak_rank = 99
        for r in rows:
            payload = r.payload or {}
            pct = self._d(payload.get("pct_chg"))
            if pct >= Decimal("9.5"):
                limitup_days += 1
            if pct >= Decimal("5"):
                strong_days += 1
            best_watch_score = max(best_watch_score, self._d(payload.get("watch_score")))
            rank = int(payload.get("pool_rank") or 99)
            peak_rank = min(peak_rank, rank)
        return limitup_days, strong_days, best_watch_score, peak_rank

    def _recent_limit_up_features(
        self,
        *,
        stock_id: str,
        current_bar: StockBarDTO,
        metadata: dict[str, Any],
        history_bars_by_stock: dict[str, list[StockBarDTO]],
        prior_rows_by_stock: dict[str, list[PriorSnapshotDTO]],
    ) -> tuple[int, int]:
        raw_recent = metadata.get("recent_limit_up_count")
        raw_consecutive = metadata.get("max_consecutive_limit_up_days")
        if raw_recent is not None or raw_consecutive is not None:
            return int(raw_recent or 0), int(raw_consecutive or 0)

        def _is_limit_up_pct(pct: Decimal) -> bool:
            return pct >= Decimal("9.5")

        history_days: list[tuple[Any, Decimal]] = []
        for prior in prior_rows_by_stock.get(stock_id, []):
            payload = prior.payload or {}
            history_days.append((prior.trade_date, self._d(payload.get("pct_chg"))))
        for hist in history_bars_by_stock.get(stock_id, []):
            history_days.append((hist.trade_date, hist.pct_chg))
        history_days.append((current_bar.trade_date, current_bar.pct_chg))

        unique_days: dict[Any, Decimal] = {}
        for trade_day, pct in history_days:
            if trade_day is None:
                continue
            unique_days[trade_day] = pct
        ordered = sorted(unique_days.items(), key=lambda item: item[0])
        if not ordered:
            return 0, 0

        recent_window = ordered[-7:]
        recent_limit_up_count = sum(1 for _, pct in recent_window if _is_limit_up_pct(pct))

        consecutive = 0
        for _, pct in reversed(ordered):
            if _is_limit_up_pct(pct):
                consecutive += 1
                continue
            break
        return recent_limit_up_count, consecutive

    def _strong_gene_score(
        self,
        *,
        prior7_limitup_days: int,
        prior7_strong_days: int,
        prior7_best_watch_score: Decimal,
        prior7_peak_rank: int,
    ) -> Decimal:
        history_score = min(
            Decimal("100"),
            Decimal(str(prior7_limitup_days * 25 + prior7_strong_days * 10)),
        )
        best_watch_bonus = min(Decimal("20"), prior7_best_watch_score * Decimal("0.2"))
        peak_rank_bonus = Decimal("10") if prior7_peak_rank <= 3 else Decimal("0")
        return min(
            Decimal("100"),
            history_score + best_watch_bonus + peak_rank_bonus,
        )

    def refresh(
        self,
        seeded_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
    ) -> list[StrongWatchRecord]:
        bars_by_stock = {bar.stock_id: bar for bar in bars}
        history_bars_by_stock: dict[str, list[StockBarDTO]] = {}
        for hist in history_bars or []:
            history_bars_by_stock.setdefault(hist.stock_id, []).append(hist)
        prior_rows_by_stock: dict[str, list[PriorSnapshotDTO]] = {}
        for prior in prior_rows or []:
            prior_rows_by_stock.setdefault(prior.stock_id, []).append(prior)
        rows: list[StrongWatchRecord] = []
        for row in seeded_rows:
            bar = bars_by_stock.get(row.stock_id)
            if bar is None:
                continue
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            rank = row.pool_rank if row.pool_rank is not None else 20
            mainline_context_score = self._mainline_context_score(rank, metadata)
            weakness_tolerance_score = self._weakness_tolerance_score(bar.pct_chg)
            prior7_limitup_days, prior7_strong_days, prior7_best_watch_score, prior7_peak_rank = self._prior7_features(
                stock_id=row.stock_id,
                metadata=metadata,
                prior_rows_by_stock=prior_rows_by_stock,
            )
            strong_gene_score = self._strong_gene_score(
                prior7_limitup_days=prior7_limitup_days,
                prior7_strong_days=prior7_strong_days,
                prior7_best_watch_score=prior7_best_watch_score,
                prior7_peak_rank=prior7_peak_rank,
            )

            support_result = self._support_scorer.score(
                stock_id=row.stock_id,
                current_bar=bar,
                prior_rows=prior_rows_by_stock.get(row.stock_id, []),
                history_bars=history_bars_by_stock.get(row.stock_id, []),
            )
            support_type = support_result.support_type
            support_level = support_result.support_level
            support_score = support_result.support_score
            support_refs = list(support_result.support_refs)
            support_count = support_result.support_count
            support_combined_strength = support_result.combined_strength
            gap_hit = support_result.gap_hit
            gap_hit_mode = support_result.gap_hit_mode
            gap_source = support_result.gap_source
            gap_level = support_result.gap_level
            gap_distance_pct = support_result.gap_distance_pct
            if support_type == "none" and self._d(metadata.get("support_score")) > Decimal("0"):
                support_type = str(metadata.get("support_type") or "none")
                support_level = self._d(metadata.get("support_level"))
                support_score = self._d(metadata.get("support_score"))
                support_refs = list(metadata.get("support_refs") or ["prior_support_snapshot"])
                support_count = int(metadata.get("support_count") or 1)
                support_combined_strength = self._d(metadata.get("support_combined_strength"))
                gap_hit = bool(metadata.get("gap_hit") or False)
                gap_hit_mode = str(metadata.get("gap_hit_mode") or "miss")
                gap_source = str(metadata.get("gap_source") or "")
                gap_level = self._d(metadata.get("gap_level"))
                gap_distance_pct = self._d(metadata.get("gap_distance_pct"), default="999")
            watch_score = (
                mainline_context_score * Decimal("0.20")
                + strong_gene_score * Decimal("0.35")
                + support_score * Decimal("0.25")
                + weakness_tolerance_score * Decimal("0.20")
            )

            if watch_score >= Decimal("80"):
                grade = "S"
            elif watch_score >= Decimal("65"):
                grade = "A"
            elif watch_score >= Decimal("50"):
                grade = "B"
            else:
                grade = "REJECT"

            recent_limit_up_count, max_consecutive_limit_up_days = self._recent_limit_up_features(
                stock_id=row.stock_id,
                current_bar=bar,
                metadata=metadata,
                history_bars_by_stock=history_bars_by_stock,
                prior_rows_by_stock=prior_rows_by_stock,
            )
            final_mainline_alive = bool(metadata.get("final_mainline_alive") or False)
            final_cycle_state = str(metadata.get("final_cycle_state") or "")
            transition_type = str(metadata.get("transition_type") or "")
            transition_confidence = self._d(metadata.get("transition_confidence"), default="0")
            trigger_flags = list(metadata.get("trigger_flags") or [])
            board_effect_confirmed = bool(
                metadata.get("board_effect_confirmed")
                or int(metadata.get("subject_limit_up_count") or 0) >= 2
                or int(metadata.get("subject_strong_count") or 0) >= 3
            )
            two_board_entry = (
                max_consecutive_limit_up_days >= 2
                or recent_limit_up_count >= 2
                or prior7_limitup_days >= 2
            )
            # Structure-driven status: removed only on hard structural breaks.
            # Low watch_score alone does not trigger removal.
            support_valid = support_score >= 50
            has_gene = prior7_limitup_days >= 1 or recent_limit_up_count >= 1 or two_board_entry

            kept_because = None
            if final_cycle_state == "fade_confirmed":
                watch_status = "removed"
            elif not support_valid and not has_gene:
                watch_status = "removed"
            elif watch_score >= self.ACTIVE_MIN_SCORE:
                watch_status = "active"
            elif has_gene or support_valid:
                # Low score but valid structure or gene → keep observing.
                watch_status = "weakening"
                if has_gene and support_valid:
                    kept_because = "gene_and_support_keep"
                elif has_gene:
                    kept_because = "gene_keep"
                else:
                    kept_because = "support_valid_keep"
            elif watch_score >= self.WEAKENING_MIN_SCORE:
                watch_status = "weakening"
            else:
                watch_status = "removed"

            # Read lifecycle from metadata first (SubjectStockPoolDTO), then attribute (StrongWatchRecord).
            _md = row.metadata if isinstance(getattr(row, "metadata", None), dict) else {}
            watch_age_days = int(
                getattr(row, "watch_age_days", None)
                or _md.get("watch_age_days")
                or 1
            )
            weak_days = int(
                getattr(row, "weak_days", None)
                or _md.get("weak_days")
                or 0
            )

            # ── Strong-watch renewal: any fresh strong signal resets the observation window ──
            # Renewal is NOT exclusive to two_board_entry — it covers all strong-stock
            # signals that confirm the stock is still worth observing.
            current_limit_up = bar.pct_chg >= Decimal("9.5")
            strong_rebound = (
                bar.pct_chg >= Decimal("5")
                and support_score >= Decimal("50")
            )
            watch_score_reactivation = (
                watch_score >= self.ACTIVE_MIN_SCORE
            )
            renewal_signal = bool(
                two_board_entry
                or current_limit_up
                or recent_limit_up_count >= 2
                or prior7_limitup_days >= 2
                or strong_rebound
                or watch_score_reactivation
            )
            renewal_reason = ""
            watch_age_reset = False
            if renewal_signal and watch_status in {"active", "weakening"}:
                watch_age_days = 1
                weak_days = 0
                watch_age_reset = True
                if two_board_entry:
                    renewal_reason = "two_board_renewal"
                elif current_limit_up:
                    renewal_reason = "limit_up_renewal"
                elif recent_limit_up_count >= 2:
                    renewal_reason = "recent_multi_limitup_renewal"
                elif prior7_limitup_days >= 2:
                    renewal_reason = "prior7_multi_limitup_renewal"
                elif strong_rebound:
                    renewal_reason = "strong_rebound_renewal"
                elif watch_score_reactivation:
                    renewal_reason = "watch_score_reactivation"

            rows.append(
                StrongWatchRecord(
                    stock_id=row.stock_id,
                    stock_name=row.stock_name or bar.stock_name,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    pool_rank=row.pool_rank,
                    watch_score=watch_score,
                    strong_grade=grade,
                    support_type=support_type,
                    support_level=support_level,
                    support_score=support_score,
                    support_refs=support_refs,
                    support_count=support_count,
                    support_combined_strength=support_combined_strength,
                    gap_hit=gap_hit,
                    gap_hit_mode=gap_hit_mode,
                    gap_source=gap_source,
                    gap_level=gap_level,
                    gap_distance_pct=gap_distance_pct,
                    role_tags={
                        "watch_tier": grade,
                        "is_leader": bool((row.pool_rank or 999) <= 1),
                        "is_front_row_core": bool((row.pool_rank or 999) <= 3),
                        "momentum_positive": bool(bar.pct_chg > Decimal("0")),
                        "final_mainline_alive": final_mainline_alive,
                        "final_cycle_state": final_cycle_state,
                        "transition_type": transition_type,
                        "transition_confidence": str(transition_confidence),
                        "trigger_flags": trigger_flags,
                        "board_effect_confirmed": board_effect_confirmed,
                        "recent_limit_up_count": recent_limit_up_count,
                        "max_consecutive_limit_up_days": max_consecutive_limit_up_days,
                        "two_board_entry": two_board_entry,
                        "prior7_limitup_days": prior7_limitup_days,
                        "prior7_strong_days": prior7_strong_days,
                        "prior7_best_watch_score": str(prior7_best_watch_score),
                        "prior7_peak_rank": prior7_peak_rank,
                        "renewal_signal": renewal_signal,
                        "renewal_reason": renewal_reason,
                        "watch_age_reset": watch_age_reset,
                    },
                    watch_status=watch_status,
                    watch_age_days=watch_age_days,
                    weak_days=weak_days,
                    mainline_context_score=mainline_context_score,
                    strong_gene_score=strong_gene_score,
                    weakness_tolerance_score=weakness_tolerance_score,
                    prior7_limitup_days=prior7_limitup_days,
                    prior7_strong_days=prior7_strong_days,
                    prior7_best_watch_score=prior7_best_watch_score,
                    prior7_peak_rank=prior7_peak_rank,
                    kept_because=kept_because,
                )
            )
        return rows
