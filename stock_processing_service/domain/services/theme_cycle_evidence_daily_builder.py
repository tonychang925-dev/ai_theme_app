from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO, SubjectEventStatsDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.leader_evidence_builder import LeaderEvidenceBuilder
from stock_processing_service.domain.services.theme_kline_evidence_builder import (
    ThemeKlineEvidence,
    ThemeKlineEvidenceBuilder,
)


@dataclass(frozen=True)
class ThemeCycleEvidenceDailyRow:
    subject_key: str
    theme_name: str
    trade_date: date

    # Event layer
    event_strength_score: Decimal
    event_continuity_score: Decimal
    strong_event_count_7d: int
    event_recency_days: int | None
    event_count_3d: int
    event_count_7d: int

    # Leader layer
    leader_alive_score: Decimal
    leader_breakdown_flag: bool
    relay_strength_score: Decimal
    front_row_survival_ratio: Decimal

    # Board structure layer
    limit_up_count: int
    limit_down_count: int
    red_ratio: Decimal
    big_drop_ratio: Decimal
    front_row_strength_score: Decimal

    # K-line layer
    theme_support_score: Decimal
    break_start_pivot: bool
    above_ma5: bool = False
    above_ma10: bool = False
    above_ma20: bool = False

    # Meta
    previous_cycle_state: str = "unknown"
    evidence_json: dict | None = None


class ThemeCycleEvidenceDailyBuilder:
    """Build theme_cycle_evidence_daily rows from pool + bar data.

    Replicates the old chain ThemeCycleEvidenceBuilder's four-layer evidence
    (event/leader/board/K-line) using new-chain domain services and DTOs.
    No direct DB access — all data comes through StockReadPort.
    """

    def build_many(
        self,
        *,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        heat_scores: dict[str, Decimal],
        previous_states: dict[str, str],
        event_stats_by_subject: dict[str, SubjectEventStatsDTO] | None = None,
        kline_evidence_by_subject: dict[str, ThemeKlineEvidence] | None = None,
    ) -> list[ThemeCycleEvidenceDailyRow]:
        bars_by_stock = {b.stock_id: b for b in bars}
        subject_pools: dict[str, list[SubjectStockPoolDTO]] = {}
        for r in pool_rows:
            subject_pools.setdefault(r.subject_key, []).append(r)

        _event_stats = event_stats_by_subject or {}
        _kline = kline_evidence_by_subject or {}

        out: list[ThemeCycleEvidenceDailyRow] = []
        for subject_key, rows in subject_pools.items():
            row = self._build_one(
                trade_date=trade_date,
                subject_key=subject_key,
                subject_name=rows[0].subject_name or subject_key,
                rows=rows,
                bars_by_stock=bars_by_stock,
                heat_score=heat_scores.get(subject_key, Decimal("0")),
                previous_state=previous_states.get(subject_key, "unknown"),
                event_stats=_event_stats.get(subject_key),
                kline=_kline.get(subject_key),
            )
            out.append(row)
        return out

    @staticmethod
    def _d(val: object) -> Decimal:
        if val is None:
            return Decimal("0")
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    def _build_one(
        self,
        *,
        trade_date: date,
        subject_key: str,
        subject_name: str,
        rows: list[SubjectStockPoolDTO],
        bars_by_stock: dict[str, StockBarDTO],
        heat_score: Decimal,
        previous_state: str,
        event_stats: SubjectEventStatsDTO | None = None,
        kline: ThemeKlineEvidence | None = None,
    ) -> ThemeCycleEvidenceDailyRow:
        n = max(len(rows), 1)
        stock_bars = [bars_by_stock[r.stock_id] for r in rows if r.stock_id in bars_by_stock]
        m = max(len(stock_bars), 1)

        # ── Event layer (mandatory: event_stats from theme_history_event) ──
        if event_stats is None:
            raise ValueError(
                f"Evidence builder: event_stats is None for subject={subject_key}. "
                f"Real event data from theme_history_event is mandatory."
            )
        event_strength = min(
            Decimal("100"),
            Decimal(str(event_stats.today_event_count * 14 + event_stats.key_event_count * 8 + event_stats.distinct_event_days * 6)),
        )
        event_continuity = min(
            Decimal("100"),
            Decimal(str(event_stats.distinct_event_days * 15 + event_stats.recent_event_count * 3)),
        )
        strong_count = event_stats.key_event_count
        event_count_3d = event_stats.today_event_count
        event_count_7d = event_stats.recent_event_count
        event_recency = event_stats.distinct_event_days if event_stats.distinct_event_days > 0 else None
        event_recency_source = "distinct_event_days_proxy"

        # ── Leader layer ──
        leader_evidence = LeaderEvidenceBuilder().build(rows=rows, bars_by_stock=bars_by_stock)
        leader_alive = leader_evidence.leader_alive_score
        leader_breakdown = leader_evidence.leader_breakdown_flag
        relay_strength = leader_evidence.relay_strength_score
        front_row_survival = leader_evidence.front_row_survival_ratio

        # ── Board structure layer ──
        positive_bars = sum(1 for b in stock_bars if b.pct_chg > Decimal("0"))
        limit_up_count = sum(1 for b in stock_bars if b.close_price >= b.limit_up_price or b.pct_chg >= Decimal("9.5"))
        limit_down_count = sum(1 for b in stock_bars if b.close_price <= b.limit_down_price or b.pct_chg <= Decimal("-9.5"))
        red_ratio = Decimal(str(positive_bars)) / Decimal(str(m))
        big_drop_count = sum(1 for b in stock_bars if b.pct_chg <= Decimal("-5"))
        big_drop_ratio = Decimal(str(big_drop_count)) / Decimal(str(m))

        # Front row strength: average of top-3 watch_scores
        watch_scores = []
        for r in rows:
            md = r.metadata if isinstance(r.metadata, dict) else {}
            ws = self._d(md.get("watch_score"))
            watch_scores.append(ws)
        top3 = sorted(watch_scores, reverse=True)[:3]
        front_row_strength = sum(top3, start=Decimal("0")) / Decimal(str(max(len(top3), 1))) if top3 else Decimal("0")

        # ── K-line layer (mandatory: ThemeKlineEvidence from ThemeKlineEvidenceBuilder) ──
        if kline is None:
            raise ValueError(
                f"Evidence builder: kline evidence is None for subject={subject_key}. "
                f"ThemeKlineEvidenceBuilder output is mandatory."
            )
        theme_support = kline.theme_support_score
        break_start_pivot = kline.break_start_pivot
        above_ma5 = kline.above_ma5
        above_ma10 = kline.above_ma10
        above_ma20 = kline.above_ma20
        kline_source = "theme_kline_evidence_builder"

        # ── Evidence JSON (for audit/replay) ──
        evidence_json = {
            "previous_cycle_state": previous_state,
            "source": "stock_processing_service.v1",
            "trade_date": trade_date.isoformat(),
            "event_layer": {
                "event_strength_score": str(event_strength),
                "event_continuity_score": str(event_continuity),
                "strong_event_count_7d": strong_count,
                "event_recency_days": event_recency,
                "event_recency_source": event_recency_source,
            },
            "leader_layer": {
                "leader_alive_score": str(leader_alive),
                "leader_breakdown_flag": leader_breakdown,
                "relay_strength_score": str(relay_strength),
                "front_row_survival_ratio": str(front_row_survival),
                "leader_score_source": leader_evidence.leader_score_source,
                "leader_stock_id": leader_evidence.leader_stock_id,
                "leader_stock_name": leader_evidence.leader_stock_name,
                "leader_pct_chg": str(leader_evidence.leader_pct_chg) if leader_evidence.leader_pct_chg is not None else None,
                "leader_limit_up": leader_evidence.leader_limit_up,
                "leader_breakdown_reason": leader_evidence.leader_breakdown_reason,
                "front_row_alive_count": leader_evidence.front_row_alive_count,
                "front_row_limit_up_count": leader_evidence.front_row_limit_up_count,
                "front_row_big_drop_count": leader_evidence.front_row_big_drop_count,
                "successor_vacuum": leader_evidence.successor_vacuum,
            },
            "board_layer": {
                "pool_size": len(rows),
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "red_ratio": str(red_ratio),
                "big_drop_ratio": str(big_drop_ratio),
                "front_row_strength_score": str(front_row_strength),
            },
            "kline_layer": {
                "source": kline_source,
                "kline_quality": kline.kline_quality if kline else "none",
                "history_days": kline.history_days if kline else 0,
                "theme_support_score": str(theme_support),
                "break_start_pivot": break_start_pivot,
                "above_ma10": above_ma10,
                "above_ma20": above_ma20,
                "above_ma5": kline.above_ma5 if kline else False,
                "theme_ret_3d": str(kline.theme_ret_3d) if kline else "0",
                "theme_ret_5d": str(kline.theme_ret_5d) if kline else "0",
                "theme_ret_10d": str(kline.theme_ret_10d) if kline else "0",
                "volume_breakdown_flag": kline.volume_breakdown_flag if kline else False,
                "composite_last": str(kline.composite_last) if kline else "0",
                "ma5": str(kline.ma5) if kline else "0",
                "ma10": str(kline.ma10) if kline else "0",
                "ma20": str(kline.ma20) if kline else "0",
                "avg_volume_ratio": str(kline.avg_volume_ratio) if kline else "0",
            },
        }

        return ThemeCycleEvidenceDailyRow(
            subject_key=subject_key,
            theme_name=subject_name,
            trade_date=trade_date,
            event_strength_score=event_strength,
            event_continuity_score=event_continuity,
            strong_event_count_7d=strong_count,
            event_recency_days=event_recency,
            event_count_3d=event_count_3d,
            event_count_7d=event_count_7d,
            leader_alive_score=leader_alive,
            leader_breakdown_flag=leader_breakdown,
            relay_strength_score=relay_strength,
            front_row_survival_ratio=front_row_survival,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            red_ratio=red_ratio,
            big_drop_ratio=big_drop_ratio,
            front_row_strength_score=front_row_strength,
            theme_support_score=theme_support,
            break_start_pivot=break_start_pivot,
            above_ma5=above_ma5,
            above_ma10=above_ma10,
            above_ma20=above_ma20,
            previous_cycle_state=previous_state,
            evidence_json=evidence_json,
        )
