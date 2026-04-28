from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence
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
    kline_support_hold: bool = False  # 从 ThemeKlineAnalyzer 传入，用于调整 support_score


class SubjectCycleEvidenceBuilder:
    def __init__(self, board_aggregator: SubjectBoardStructureAggregator | None = None) -> None:
        self._board = board_aggregator or SubjectBoardStructureAggregator()

    def build_from_db(
        self,
        db_rows: list[dict],
        kline_support_map: dict[str, bool] | None = None,
    ) -> list[SubjectCycleEvidence]:
        """从 theme_cycle_evidence_daily 预计算数据直接构建 SubjectCycleEvidence。

        旧链 ThemeCycleEvidenceBuilder + ThemeBoardStructureAggregator 每日写入该表，
        包含四层证据的全部字段。新链直接消费，避免重复计算。
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

    def build_many(
        self,
        stock_evidences: list[CycleEvidence],
        kline_support_map: dict[str, bool] | None = None,
    ) -> list[SubjectCycleEvidence]:
        by_subject: dict[str, list[CycleEvidence]] = defaultdict(list)
        for e in stock_evidences:
            by_subject[e.subject_key].append(e)

        out: list[SubjectCycleEvidence] = []
        for subject_key, rows in by_subject.items():
            rows_sorted = sorted(rows, key=lambda x: x.leader_score, reverse=True)
            n = max(len(rows_sorted), 1)
            prev_state = rows_sorted[0].previous_state if rows_sorted else "unknown"
            # Estimate event_recency from per-stock event_score（修复硬编码 1）
            _max_event = max((r.event_score for r in rows_sorted), default=Decimal("0"))
            if _max_event >= Decimal("70"):
                event_recency_days = 0
            elif _max_event >= Decimal("50"):
                event_recency_days = 1
            elif _max_event >= Decimal("30"):
                event_recency_days = 3
            else:
                event_recency_days = 7 if rows_sorted else None

            # 板块结构指标（委托给独立聚合器，对齐生产 ThemeBoardStructureAggregator）
            _board = self._board.aggregate(subject_key, rows_sorted)
            limit_up_count = _board.limit_up_count
            limit_down_count = _board.limit_down_count
            red_ratio = _board.red_ratio
            big_drop_ratio = _board.big_drop_ratio
            front_row_survival_ratio = _board.front_row_survival_ratio
            front_row_strength_score = _board.front_row_strength_score

            # K线支撑调整：支撑有效 +15，支撑失效且低于50 -10
            _kline_hold = (kline_support_map or {}).get(subject_key, False)
            _raw_support = sum((r.support_score for r in rows_sorted), start=Decimal("0")) / Decimal(str(n))
            if _kline_hold:
                _theme_support = min(_raw_support + Decimal("15"), Decimal("100"))
            elif _raw_support < Decimal("50"):
                _theme_support = max(_raw_support - Decimal("10"), Decimal("0"))
            else:
                _theme_support = _raw_support

            out.append(
                SubjectCycleEvidence(
                    subject_key=subject_key,
                    subject_name=rows_sorted[0].subject_name if rows_sorted else subject_key,
                    previous_cycle_state=prev_state,
                    event_strength_score=max((r.event_score for r in rows_sorted), default=Decimal("0")),
                    event_continuity_score=sum((r.continuity_score for r in rows_sorted), start=Decimal("0"))
                    / Decimal(str(n)),
                    strong_event_count_7d=sum(1 for r in rows_sorted if r.event_score >= Decimal("70")),
                    event_recency_days=event_recency_days,
                    leader_alive_score=max((r.leader_score for r in rows_sorted), default=Decimal("0")),
                    leader_breakdown_flag=_board.leader_breakdown_flag,
                    relay_strength_score=sum((r.relay_score for r in rows_sorted), start=Decimal("0")) / Decimal(
                        str(n)
                    ),
                    front_row_survival_ratio=front_row_survival_ratio,
                    limit_up_count=limit_up_count,
                    limit_down_count=limit_down_count,
                    red_ratio=red_ratio,
                    big_drop_ratio=big_drop_ratio,
                    front_row_strength_score=front_row_strength_score,
                    theme_support_score=_theme_support,
                    break_start_pivot=False,
                    kline_support_hold=_kline_hold,
                )
            )
        return out

