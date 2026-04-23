from __future__ import annotations

from datetime import date

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPromoteService:
    def promote(self, trade_date: date, rows: list[StrongWatchRecord]) -> list[SubjectStockPoolDTO]:
        promoted: list[SubjectStockPoolDTO] = []
        for row in rows:
            if row.strong_grade not in {"S", "A", "B"}:
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
                        "role_tags": row.role_tags,
                    },
                )
            )
        return promoted
