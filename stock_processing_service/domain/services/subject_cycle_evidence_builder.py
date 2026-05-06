from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.subject_board_structure_aggregator import (
    SubjectBoardStructureAggregator,
)


@dataclass(frozen=True)
class SubjectCycleEvidence:
    subject_key: str
    subject_name: str
    previous_cycle_state: str
    event_strength_score: Decimal
    event_continuity_score: Decimal
    strong_event_count_7d: int
    event_recency_days: int | None
    leader_alive_score: Decimal
    leader_breakdown_flag: bool
    relay_strength_score: Decimal
    front_row_survival_ratio: Decimal
    limit_up_count: int
    limit_down_count: int
    red_ratio: Decimal
    big_drop_ratio: Decimal
    front_row_strength_score: Decimal
    theme_support_score: Decimal
    break_start_pivot: bool = False
    kline_support_hold: bool = False


class SubjectCycleEvidenceBuilder:
    """Build SubjectCycleEvidence exclusively from theme_cycle_evidence_daily DB truth source.

    No heuristic fallback — build_from_db() is the only path.
    """

    def __init__(self, board_aggregator: SubjectBoardStructureAggregator | None = None) -> None:
        self._board = board_aggregator or SubjectBoardStructureAggregator()

    def build_from_db(
        self,
        db_rows: list[dict],
        kline_support_map: dict[str, bool] | None = None,
    ) -> list[SubjectCycleEvidence]:
        """从 theme_cycle_evidence_daily 预计算数据直接构建 SubjectCycleEvidence。

        旧链 ThemeCycleEvidenceBuilder + ThemeBoardStructureAggregator 每日写入该表，
        包含四层证据的全部字段。新链直接消费，这是唯一路径。
        """
        out: list[SubjectCycleEvidence] = []
        for r in db_rows:
            _ev_raw = r.get("evidence_json") or {}
            if isinstance(_ev_raw, str):
                try:
                    _ev_raw = json.loads(_ev_raw)
                except (json.JSONDecodeError, TypeError):
                    _ev_raw = {}
            evidence_json = _ev_raw if isinstance(_ev_raw, dict) else {}
            prev_state = str(evidence_json.get("previous_cycle_state") or "unknown")
            _kline_hold = (kline_support_map or {}).get(r["subject_key"], False)

            out.append(
                SubjectCycleEvidence(
                    subject_key=str(r["subject_key"]),
                    subject_name=str(r.get("theme_name") or r["subject_key"]),
                    previous_cycle_state=prev_state,
                    event_strength_score=Decimal(str(r.get("event_strength_score") or 0)),
                    event_continuity_score=Decimal(str(r.get("event_continuity_score") or 0)),
                    strong_event_count_7d=int(r.get("strong_event_count_7d") or 0),
                    event_recency_days=r.get("event_recency_days"),
                    leader_alive_score=Decimal(str(r.get("leader_alive_score") or 0)),
                    leader_breakdown_flag=bool(r.get("leader_breakdown_flag")),
                    relay_strength_score=Decimal(str(r.get("relay_strength_score") or 0)),
                    front_row_survival_ratio=Decimal(str(r.get("front_row_survival_ratio") or 0)),
                    limit_up_count=int(r.get("limit_up_count") or 0),
                    limit_down_count=int(r.get("limit_down_count") or 0),
                    red_ratio=Decimal(str(r.get("red_ratio") or 0)),
                    big_drop_ratio=Decimal(str(r.get("big_drop_ratio") or 0)),
                    front_row_strength_score=Decimal(str(r.get("front_row_strength_score") or 0)),
                    theme_support_score=Decimal(str(r.get("theme_support_score") or 0)),
                    break_start_pivot=bool(r.get("break_start_pivot")),
                    kline_support_hold=_kline_hold,
                )
            )
        return out
