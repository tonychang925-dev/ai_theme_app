from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import SubjectStockPoolDTO


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")


def _as_raw_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return dict(getattr(row, "__dict__", {}) or {})


@dataclass(frozen=True)
class LegacyLayerCOutputReport:
    trade_date: str
    source: dict[str, Any]
    raw: dict[str, Any]
    effective: dict[str, Any]
    distributions: dict[str, Any]
    target: dict[str, Any]
    consistency: dict[str, Any]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegacyLayerCOutputReportBuilder:
    """Report old-chain Layer C raw/effective output without running new Layer C."""

    def build(
        self,
        *,
        trade_date: str,
        raw_rows: list[Any],
        effective_rows: list[SubjectStockPoolDTO],
        target_stock_id: str,
        recap_doc: dict[str, Any] | None = None,
    ) -> LegacyLayerCOutputReport:
        raw = [_as_raw_dict(row) for row in raw_rows]
        target_stock = target_stock_id.strip().upper()
        raw_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw:
            stock_id = str(row.get("stock_id") or "").strip().upper()
            if stock_id:
                raw_by_stock[stock_id].append(row)

        effective_sorted = sorted(effective_rows, key=self._effective_sort_key, reverse=True)
        effective_by_stock = {row.stock_id.strip().upper(): row for row in effective_sorted}
        effective_rank = {row.stock_id.strip().upper(): idx for idx, row in enumerate(effective_sorted, start=1)}

        source_used = str(raw[0].get("_legacy_source_used") or "") if raw else ""
        latest_pool_trade_date = raw[0].get("_legacy_latest_pool_trade_date") if raw else None
        source_reason = ""
        if source_used == "strong_stock_watch_history":
            source_reason = "trade_date_before_latest_pool_trade_date"
        elif source_used == "strong_stock_watch_pool":
            source_reason = "trade_date_at_or_after_latest_pool_trade_date"

        target_raw = raw_by_stock.get(target_stock, [])
        target_effective = effective_by_stock.get(target_stock)
        target_md = target_effective.metadata if target_effective and isinstance(target_effective.metadata, dict) else {}

        consistency = self._consistency(
            recap_doc=recap_doc or {},
            effective_stock_count=len(effective_rows),
        )

        notes: list[str] = []
        if len(raw) > len(effective_rows):
            notes.append("raw_rows_contain_duplicate_stock_across_subjects")
        if not effective_rows:
            notes.append("effective_legacy_layer_c_output_empty")
        if target_raw and not target_effective:
            notes.append("target_raw_exists_but_missing_after_effective_dedupe")

        return LegacyLayerCOutputReport(
            trade_date=trade_date,
            source={
                "source_used": source_used,
                "reason": source_reason,
                "latest_pool_trade_date": latest_pool_trade_date,
            },
            raw={
                "raw_row_count": len(raw),
                "stock_distinct_count": len(raw_by_stock),
                "subject_distinct_count": len({str(r.get("subject_key") or "") for r in raw if r.get("subject_key")}),
                "duplicate_stock_count": sum(1 for rows in raw_by_stock.values() if len(rows) > 1),
                "max_rows_per_stock": max((len(rows) for rows in raw_by_stock.values()), default=0),
            },
            effective={
                "effective_stock_count": len(effective_rows),
                "effective_subject_count": len({row.subject_key for row in effective_rows if row.subject_key}),
                "top_preview": [self._row_preview(row, idx) for idx, row in enumerate(effective_sorted[:30], start=1)],
            },
            distributions={
                "watch_status_counts": dict(Counter(str(r.get("watch_status") or "") for r in raw)),
                "pool_entry_type_counts": dict(Counter(str(r.get("watch_pool_entry_type") or r.get("pool_entry_type") or "") for r in raw)),
                "watch_source_tag_counts": dict(Counter(str(r.get("watch_source_tag") or "") for r in raw)),
                "watch_score": self._quantiles([_d(r.get("watch_score")) for r in raw]),
                "watch_priority": self._quantiles([_d(r.get("watch_priority")) for r in raw]),
            },
            target={
                "stock_id": target_stock,
                "raw_rows": len(target_raw),
                "effective_selected": target_effective is not None,
                "selected_subject_key": target_effective.subject_key if target_effective else "",
                "selected_theme_name": target_effective.subject_name if target_effective else "",
                "watch_status": str(target_md.get("watch_status") or ""),
                "pool_entry_type": str(target_md.get("watch_pool_entry_type") or target_md.get("pool_entry_type") or ""),
                "watch_score": str(target_md.get("watch_score") or ""),
                "watch_priority": str(target_md.get("watch_priority") or ""),
                "prior7_limitup_days": int(target_md.get("prior7_limitup_days") or 0),
                "prior7_strong_days": int(target_md.get("prior7_strong_days") or 0),
                "recent_limit_up_count": int(target_md.get("recent_limit_up_count") or 0),
                "support_type": str(target_md.get("support_type") or ""),
                "support_score": str(target_md.get("support_score") or ""),
                "rank_in_effective_c_pool": effective_rank.get(target_stock),
                "legacy_raw_row_count": int(target_md.get("legacy_raw_row_count") or 0),
                "duplicate_subjects": [
                    {
                        "subject_key": str(row.get("subject_key") or ""),
                        "theme_name": str(row.get("theme_name") or ""),
                        "watch_status": str(row.get("watch_status") or ""),
                        "pool_entry_type": str(row.get("watch_pool_entry_type") or row.get("pool_entry_type") or ""),
                        "watch_score": str(row.get("watch_score") or ""),
                        "watch_priority": str(row.get("watch_priority") or ""),
                        "prior7_limitup_days": int(row.get("prior7_limitup_days") or 0),
                        "prior7_strong_days": int(row.get("prior7_strong_days") or 0),
                    }
                    for row in target_raw
                ],
            },
            consistency=consistency,
            notes=notes,
        )

    @staticmethod
    def _effective_sort_key(row: SubjectStockPoolDTO) -> tuple[Any, ...]:
        md = row.metadata if isinstance(row.metadata, dict) else {}
        rank = row.pool_rank if row.pool_rank is not None else 999
        return (
            1 if str(md.get("pool_entry_type") or "") == "formal" else 0,
            _d(md.get("watch_priority")),
            _d(md.get("watch_score")),
            int(md.get("prior7_limitup_days") or 0),
            int(md.get("prior7_strong_days") or 0),
            _d(md.get("support_score")),
            -int(rank or 999),
        )

    @staticmethod
    def _row_preview(row: SubjectStockPoolDTO, rank: int) -> dict[str, Any]:
        md = row.metadata if isinstance(row.metadata, dict) else {}
        return {
            "rank": rank,
            "stock_id": row.stock_id,
            "stock_name": row.stock_name,
            "subject_key": row.subject_key,
            "theme_name": row.subject_name,
            "watch_status": str(md.get("watch_status") or ""),
            "pool_entry_type": str(md.get("pool_entry_type") or ""),
            "watch_score": str(md.get("watch_score") or ""),
            "watch_priority": str(md.get("watch_priority") or ""),
            "prior7_limitup_days": int(md.get("prior7_limitup_days") or 0),
            "prior7_strong_days": int(md.get("prior7_strong_days") or 0),
            "support_type": str(md.get("support_type") or ""),
            "support_score": str(md.get("support_score") or ""),
        }

    @staticmethod
    def _quantiles(values: list[Decimal]) -> dict[str, str]:
        if not values:
            return {"p50": "0", "p75": "0", "p90": "0", "max": "0"}
        ordered = sorted(values)

        def pick(percent: Decimal) -> Decimal:
            idx = int((Decimal(len(ordered) - 1) * percent).to_integral_value())
            return ordered[max(0, min(idx, len(ordered) - 1))]

        return {
            "p50": str(pick(Decimal("0.50"))),
            "p75": str(pick(Decimal("0.75"))),
            "p90": str(pick(Decimal("0.90"))),
            "max": str(ordered[-1]),
        }

    @staticmethod
    def _consistency(*, recap_doc: dict[str, Any], effective_stock_count: int) -> dict[str, Any]:
        if not recap_doc:
            return {
                "recap_available": False,
                "effective_equals_legacy_watch_input_count": None,
                "effective_equals_strong_watch_input_7d_count": None,
            }
        legacy_count = int(recap_doc.get("legacy_watch_input_count") or 0)
        input_count = int(recap_doc.get("strong_watch_input_7d_count") or 0)
        return {
            "recap_available": True,
            "recap_layer_c_input_mode": recap_doc.get("layer_c_input_mode"),
            "recap_legacy_watch_input_count": legacy_count,
            "recap_strong_watch_input_7d_count": input_count,
            "recap_candidate_count_all": int(recap_doc.get("candidate_count_all") or 0),
            "recap_candidate_count_observe": int(recap_doc.get("candidate_count_observe") or 0),
            "recap_observe_candidates_count": int(recap_doc.get("observe_candidates_count") or 0),
            "effective_equals_legacy_watch_input_count": effective_stock_count == legacy_count,
            "effective_equals_strong_watch_input_7d_count": effective_stock_count == input_count,
        }
