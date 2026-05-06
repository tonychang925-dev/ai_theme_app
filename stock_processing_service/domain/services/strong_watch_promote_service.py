from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPromoteService:
    """Layer C promote: AdmissionPolicy-driven output, no independent business gates.

    V2 (LAYER_C_PROMOTE_V2=1, default):
      - Consumes admission_status from AdmissionPolicy.
      - formal     → promote_bucket="formal"
      - observe_only → promote_bucket="observe"
      - reject / removed → dropped from promote output.
      - strong_grade / watch_score are sorting factors only, NOT hard reject gates.

    Legacy (LAYER_C_PROMOTE_V2=0):
      - Original S/A grade + watch_score >= 78 hard gates.
    """

    def promote(
        self,
        trade_date: date,
        rows: list[StrongWatchRecord],
        top_n: int = 20,
    ) -> list[SubjectStockPoolDTO]:
        if os.environ.get("LAYER_C_PROMOTE_V2", "1") != "1":
            return self._legacy_promote(trade_date, rows)

        # Build (record, bucket, reason) triples — no dataclass mutation needed.
        eligible: list[tuple[StrongWatchRecord, str, str]] = []
        for row in rows:
            if row.watch_status == "removed":
                continue
            admission = str(getattr(row, "admission_status", "") or "").strip().lower()
            if admission == "formal":
                eligible.append((row, "formal", "admission_formal"))
            elif admission == "observe_only":
                eligible.append((row, "observe", "admission_observe_only"))
            # reject or unknown → dropped

        ranked = sorted(
            eligible,
            key=lambda item: (
                1 if item[1] == "formal" else 0,
                self._support_priority(item[0].support_type or ""),
                item[0].support_score or Decimal("0"),
                item[0].prior7_limitup_days or 0,
                item[0].watch_score or Decimal("0"),
            ),
            reverse=True,
        )

        promoted: list[SubjectStockPoolDTO] = []
        for row, bucket, reason in ranked[:top_n]:
            promoted.append(self._to_dto(trade_date, row, bucket, reason))
        return promoted

    @staticmethod
    def _to_dto(
        trade_date: date,
        row: StrongWatchRecord,
        promote_bucket: str,
        promote_reason: str,
    ) -> SubjectStockPoolDTO:
        return SubjectStockPoolDTO(
            trade_date=trade_date,
            subject_key=row.subject_key,
            subject_name=row.subject_name,
            stock_id=row.stock_id,
            stock_name=row.stock_name,
            pool_rank=row.pool_rank,
            metadata={
                "candidate_source": row.source,
                "watch_score": str(row.watch_score),
                "strong_grade": row.strong_grade,
                "support_type": row.support_type,
                "support_level": str(row.support_level),
                "support_score": str(row.support_score),
                "support_refs": row.support_refs,
                "support_count": row.support_count,
                "support_combined_strength": str(row.support_combined_strength),
                "gap_hit": row.gap_hit,
                "gap_hit_mode": row.gap_hit_mode,
                "gap_source": row.gap_source,
                "gap_level": str(row.gap_level),
                "gap_distance_pct": str(row.gap_distance_pct),
                "role_tags": row.role_tags,
                "mainline_context_score": str(row.mainline_context_score),
                "strong_gene_score": str(row.strong_gene_score),
                "weakness_tolerance_score": str(row.weakness_tolerance_score),
                "prior7_limitup_days": row.prior7_limitup_days,
                "prior7_strong_days": row.prior7_strong_days,
                "prior7_best_watch_score": str(row.prior7_best_watch_score),
                "prior7_peak_rank": row.prior7_peak_rank,
                "watch_status": row.watch_status,
                "kept_because": row.kept_because,
                "admission_status": row.admission_status,
                "promote_bucket": promote_bucket,
                "promote_reason": promote_reason,
            },
        )

    # ── Legacy path (LAYER_C_PROMOTE_V2=0) ──

    @staticmethod
    def _legacy_promote(
        trade_date: date,
        rows: list[StrongWatchRecord],
    ) -> list[SubjectStockPoolDTO]:
        promoted: list[SubjectStockPoolDTO] = []
        for row in rows:
            if str(getattr(row, "admission_status", "formal") or "formal") != "formal":
                continue
            if row.strong_grade not in {"S", "A"}:
                continue
            if row.watch_score < 78:
                continue
            promoted.append(
                SubjectStockPoolDTO(
                    trade_date=trade_date,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    stock_id=row.stock_id,
                    stock_name=row.stock_name,
                    pool_rank=row.pool_rank,
                    metadata={
                        "candidate_source": row.source,
                        "watch_score": str(row.watch_score),
                        "strong_grade": row.strong_grade,
                        "support_type": row.support_type,
                        "support_level": str(row.support_level),
                        "support_score": str(row.support_score),
                        "support_refs": row.support_refs,
                        "support_count": row.support_count,
                        "support_combined_strength": str(row.support_combined_strength),
                        "gap_hit": row.gap_hit,
                        "gap_hit_mode": row.gap_hit_mode,
                        "gap_source": row.gap_source,
                        "gap_level": str(row.gap_level),
                        "gap_distance_pct": str(row.gap_distance_pct),
                        "role_tags": row.role_tags,
                        "mainline_context_score": str(row.mainline_context_score),
                        "strong_gene_score": str(row.strong_gene_score),
                        "weakness_tolerance_score": str(row.weakness_tolerance_score),
                        "prior7_limitup_days": row.prior7_limitup_days,
                        "prior7_strong_days": row.prior7_strong_days,
                        "prior7_best_watch_score": str(row.prior7_best_watch_score),
                        "prior7_peak_rank": row.prior7_peak_rank,
                        "watch_status": row.watch_status,
                        "kept_because": row.kept_because,
                        "admission_status": row.admission_status,
                    },
                )
            )
        return promoted

    @staticmethod
    def _support_priority(support_type: str) -> int:
        st = (support_type or "").strip().lower()
        if st == "gap_support":
            return 5
        if st in {"previous_low", "prev_low_support"}:
            return 4
        if st == "platform_support":
            return 3
        if st == "ma_support":
            return 2
        return 0
