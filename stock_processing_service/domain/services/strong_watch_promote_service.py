from __future__ import annotations

from datetime import date

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPromoteService:
    def promote(self, trade_date: date, rows: list[StrongWatchRecord]) -> list[SubjectStockPoolDTO]:
        promoted: list[SubjectStockPoolDTO] = []
        for row in rows:
            if row.strong_grade not in {"S", "A", "B", "B_KEEP"}:
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
                    },
                )
            )
        return promoted
