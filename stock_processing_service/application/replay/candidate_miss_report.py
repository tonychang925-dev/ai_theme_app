from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateMissReport:
    stock_id: str
    trade_date: str
    presence: dict[str, bool]
    ranking: dict[str, int | None]
    scores: dict[str, Any]
    selection: dict[str, Any]
    c_layer_trace: dict[str, Any]
    d_layer_trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_id": self.stock_id,
            "trade_date": self.trade_date,
            "presence": self.presence,
            "ranking": self.ranking,
            "scores": self.scores,
            "selection": self.selection,
            "c_layer_trace": self.c_layer_trace,
            "d_layer_trace": self.d_layer_trace,
        }


class CandidateMissReportBuilder:
    def build(
        self,
        *,
        trade_date: str,
        stock_id: str,
        recap_doc: dict[str, Any],
        top_candidates: list[dict[str, Any]],
        observe_candidates: list[dict[str, Any]],
        promoted_pool: list[dict[str, Any]],
        strong_watch_input: list[dict[str, Any]],
        best_row: dict[str, Any] | None,
    ) -> CandidateMissReport:
        top_rank = self._rank(stock_id, top_candidates)
        observe_rank = self._rank(stock_id, observe_candidates)
        promoted_rank = self._rank(stock_id, promoted_pool)
        input_rank = self._rank(stock_id, strong_watch_input)
        in_top = top_rank is not None
        in_observe = observe_rank is not None
        in_promoted = promoted_rank is not None
        in_input = input_rank is not None
        top_row = self._target(stock_id, top_candidates) or {}
        observe_row = self._target(stock_id, observe_candidates) or {}
        promoted_row = self._target(stock_id, promoted_pool) or {}
        input_row = self._target(stock_id, strong_watch_input) or {}
        row = best_row or top_row or observe_row or promoted_row or input_row or {}
        observe_total = int(recap_doc.get("observe_candidates_count") or len(observe_candidates) or 0)
        top_total = int(recap_doc.get("candidate_count") or len(top_candidates) or 0)
        observe_top_n = len(observe_candidates)
        formal_top_n = len(top_candidates)
        candidate_level = str(row.get("candidate_level") or "")
        reject_reason = str(row.get("reject_reason") or row.get("hard_reject_reason") or "")

        candidate_row_created = in_top or in_observe
        reason = "selected"
        if not in_input and not in_promoted and not in_top and not in_observe:
            reason = "not_in_input_pool"
        elif in_input and not (in_promoted or in_top or in_observe):
            reason = "in_input_but_not_promoted"
        elif in_promoted and not candidate_row_created:
            reason = "in_promoted_but_not_candidate"
        elif reject_reason:
            reason = "d_layer_reject"
        elif candidate_level == "observe_only" and not in_observe:
            if observe_total > observe_top_n:
                reason = "observe_rank_gt_observe_top_n"
            else:
                reason = "candidate_rank_outside_output"
        elif candidate_level in {"formal", "s", "a", "b"} and not in_top:
            reason = "formal_rank_gt_formal_top_n"
        elif not candidate_level and in_input:
            reason = "in_input_but_not_promoted"

        c_layer_trace = {
            "seed_gate_pass": row.get("seed_gate_pass"),
            "seed_gate_reason": row.get("seed_gate_reason"),
            "strong_gene_seed": row.get("strong_gene_seed"),
            "strong_gene_seed_reason": row.get("strong_gene_seed_reason"),
            "input_rank": input_rank,
            "refresh_status": input_row.get("watch_status"),
            "kept": in_promoted or in_top or in_observe,
            "pruned": str(input_row.get("watch_status") or "").lower() == "removed",
            "admission_status": self._first_value(row, "admission_status", "pool_entry_type", "candidate_level"),
            "admission_reasons": self._list_value(row.get("admission_reasons") or row.get("evidence_rules")),
            "hard_reject_any": bool(reject_reason),
            "pass_count_4of3": row.get("pass_count_4of3"),
            "promote_bucket": self._first_value(promoted_row, "promote_bucket", "pool_entry_type"),
            "promoted_rank": promoted_rank,
        }
        d_layer_trace = {
            "candidate_row_created": candidate_row_created,
            "candidate_level": row.get("candidate_level"),
            "hard_reject": reject_reason or None,
            "not_selected_reason": reason,
        }

        return CandidateMissReport(
            stock_id=stock_id,
            trade_date=trade_date,
            presence={
                "in_pool": in_input or in_promoted or in_top or in_observe,
                "in_refreshed": in_input,
                "in_kept": in_promoted or in_top or in_observe,
                "in_promoted_pool": in_promoted or in_top or in_observe,
                "in_top_candidates": in_top,
                "in_observe_candidates": in_observe,
            },
            ranking={
                "top_rank": top_rank,
                "top_total": top_total,
                "observe_rank": observe_rank,
                "observe_total": observe_total,
                "promoted_rank": promoted_rank,
                "input_rank": input_rank,
            },
            scores={
                "candidate_score": row.get("candidate_score"),
                "support_score": row.get("support_score"),
                "support_type": row.get("support_type"),
                "weakness_valid_score": row.get("weakness_valid_score"),
                "strong_gene_score": row.get("strong_gene_score"),
                "repair_or_takeover_score": row.get("repair_or_takeover_score"),
                "candidate_level": row.get("candidate_level"),
                "gap_hit": row.get("gap_hit"),
            },
            selection={
                "selected": in_top or in_observe,
                "not_selected_reason": reason,
                "observe_top_n": observe_top_n,
                "formal_top_n": formal_top_n,
                "reject_reason": reject_reason,
            },
            c_layer_trace=c_layer_trace,
            d_layer_trace=d_layer_trace,
        )

    @classmethod
    def _rank(cls, stock_id: str, rows: list[dict[str, Any]]) -> int | None:
        target = str(stock_id).strip().upper()
        for idx, row in enumerate(rows, start=1):
            if str(row.get("stock_id") or "").strip().upper() == target:
                return idx
        return None

    @classmethod
    def _target(cls, stock_id: str, *groups: list[dict[str, Any]]) -> dict[str, Any] | None:
        target = str(stock_id).strip().upper()
        for rows in groups:
            for row in rows:
                if str(row.get("stock_id") or "").strip().upper() == target:
                    return row
        return None

    @staticmethod
    def _first_value(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _list_value(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
