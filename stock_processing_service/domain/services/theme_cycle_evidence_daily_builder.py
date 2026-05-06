from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO, SubjectEventStatsDTO, SubjectStockPoolDTO
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

        # ── Event layer ──
        event_recency_source = "unknown"
        if event_stats is not None:
            # Real event stats from theme_history_event (preferred).
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
            # distinct_event_days is a proxy for recency, not exact last-event days.
            event_recency = event_stats.distinct_event_days if event_stats.distinct_event_days > 0 else None
            event_recency_source = "distinct_event_days_proxy"
        else:
            # Fallback: pool metadata (weaker, use only when event_stats unavailable).
            event_scores: list[Decimal] = []
            for r in rows:
                md = r.metadata if isinstance(r.metadata, dict) else {}
                es = self._d(md.get("event_score") or md.get("event_strength_score"))
                event_scores.append(es)
            event_strength = sum(event_scores, start=Decimal("0")) / Decimal(str(len(event_scores))) if event_scores else Decimal("0")
            hot_days_5d = sum(1 for r in rows if int((r.metadata or {}).get("hot_days_5d") or 0) >= 1)
            event_continuity = min(Decimal("100"), Decimal(str(hot_days_5d * 15 + len(rows) * 3)))
            strong_count = sum(1 for s in event_scores if s >= Decimal("70"))
            event_count_3d = sum(1 for r in rows if int((r.metadata or {}).get("event_count_3d") or 0) > 0)
            event_count_7d = sum(1 for r in rows if int((r.metadata or {}).get("event_count_7d") or 0) > 0)
            event_recency_raw = [r.metadata.get("event_recency_days") for r in rows if isinstance(r.metadata, dict) and r.metadata.get("event_recency_days") is not None]
            event_recency = int(min(event_recency_raw)) if event_recency_raw else None
            event_recency_source = "pool_metadata"

        # ── Leader layer ──
        leader_scores: list[Decimal] = []
        for r in rows:
            md = r.metadata if isinstance(r.metadata, dict) else {}
            ls = self._d(md.get("leader_score") or md.get("leader_alive_score"))
            leader_scores.append(ls)
        leader_alive = max(leader_scores) if leader_scores else Decimal("0")

        # Leader breakdown: no leader with score >= 50 and no front-row stock above 0%
        leader_breakdown = all(s < Decimal("50") for s in leader_scores) if leader_scores else True

        # Relay: average of non-leader scores in top 5
        sorted_scores = sorted(leader_scores, reverse=True)
        relay_pool = sorted_scores[1:6] if len(sorted_scores) > 1 else []
        relay_strength = sum(relay_pool, start=Decimal("0")) / Decimal(str(max(len(relay_pool), 1)))

        # Front row survival: positive pct_stocks / total
        positive_bars = sum(1 for b in stock_bars if b.pct_chg > Decimal("0"))
        front_row_survival = Decimal(str(positive_bars)) / Decimal(str(m))

        # ── Board structure layer ──
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

        # ── K-line layer ──
        if kline is not None:
            theme_support = kline.theme_support_score
            break_start_pivot = kline.break_start_pivot
            above_ma10 = kline.above_ma10
            above_ma20 = kline.above_ma20
            kline_source = "theme_kline_evidence_builder"
        else:
            # Fallback: pool metadata (weaker).
            support_scores: list[Decimal] = []
            for r in rows:
                md = r.metadata if isinstance(r.metadata, dict) else {}
                ss = self._d(md.get("support_score") or md.get("theme_support_score"))
                support_scores.append(ss)
            theme_support = sum(support_scores, start=Decimal("0")) / Decimal(str(len(support_scores))) if support_scores else Decimal("0")
            break_start_pivot = theme_support < Decimal("35") and red_ratio < Decimal("0.45")
            above_ma10 = any(bool((r.metadata or {}).get("above_ma10")) for r in rows if isinstance(r.metadata, dict))
            above_ma20 = any(bool((r.metadata or {}).get("above_ma20")) for r in rows if isinstance(r.metadata, dict))
            kline_source = "pool_metadata"

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
            above_ma10=above_ma10,
            above_ma20=above_ma20,
            previous_cycle_state=previous_state,
            evidence_json=evidence_json,
        )
