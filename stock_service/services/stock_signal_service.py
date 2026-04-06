from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from stock_service.models import (
    StockAbnormalEvent,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboardEntry,
)


def _score_snapshot(row: SubjectStockDailySnapshot) -> float:
    pct = row.pct_chg or 0.0
    leader_bonus = 20.0 if row.is_leader else 0.0
    rank_bonus = max(0.0, 10.0 - float(max(row.rank_order, 1) - 1) * 2.0)
    limit_bonus = 15.0 if pct >= 9.8 else 0.0
    return pct + leader_bonus + rank_bonus + limit_bonus


class StockSignalService:
    """
    P3.phase1-T03 最小实现：
    - 从 subject_stock_daily_snapshot 派生可解释的股票异动事件
    - 构建题材内榜单对象，供 recap 和后续工作台直接复用
    """

    def derive_abnormal_events(
        self,
        rows: Iterable[SubjectStockDailySnapshot],
    ) -> list[StockAbnormalEvent]:
        events: list[StockAbnormalEvent] = []
        for row in rows:
            pct = row.pct_chg
            event_type = None
            if pct is not None and pct >= 9.8:
                event_type = "limit_up"
            elif pct is not None and pct <= -9.8:
                event_type = "limit_down"
            elif row.is_leader and pct is not None and pct >= 3.0:
                event_type = "leader_move"

            if not event_type:
                continue

            evidence_parts = [f"rank={row.rank_order}"]
            if pct is not None:
                evidence_parts.append(f"pct={pct:.2f}%")
            if row.is_leader:
                evidence_parts.append("leader")

            events.append(
                StockAbnormalEvent(
                    trade_date=row.trade_date,
                    stock_id=row.stock_id,
                    stock_name=row.stock_name,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    abnormal_type=event_type,
                    pct_chg=pct,
                    rank_order=row.rank_order,
                    is_leader=row.is_leader,
                    evidence=", ".join(evidence_parts),
                )
            )

        return sorted(
            events,
            key=lambda item: (
                0 if item.abnormal_type == "limit_up" else 1,
                -(item.pct_chg or 0.0),
                item.rank_order,
                item.stock_id,
            ),
        )

    def build_theme_stock_leaderboard(
        self,
        rows: Iterable[SubjectStockDailySnapshot],
    ) -> list[ThemeStockLeaderboardEntry]:
        grouped: dict[str, list[SubjectStockDailySnapshot]] = defaultdict(list)
        for row in rows:
            grouped[row.subject_key].append(row)

        leaderboard: list[ThemeStockLeaderboardEntry] = []
        for subject_key, subject_rows in grouped.items():
            sorted_rows = sorted(
                subject_rows,
                key=lambda row: (-_score_snapshot(row), row.rank_order, row.stock_id),
            )
            for row in sorted_rows:
                role = "member"
                if row.is_leader:
                    role = "leader"
                elif row.rank_order and row.rank_order <= 3:
                    role = "core"

                leaderboard.append(
                    ThemeStockLeaderboardEntry(
                        trade_date=row.trade_date,
                        subject_key=subject_key,
                        subject_name=row.subject_name,
                        stock_id=row.stock_id,
                        stock_name=row.stock_name,
                        rank_order=row.rank_order,
                        role=role,
                        pct_chg=row.pct_chg,
                        close_price=row.close_price,
                        limit_up=bool(row.pct_chg is not None and row.pct_chg >= 9.8),
                        score=_score_snapshot(row),
                    )
                )

        return sorted(
            leaderboard,
            key=lambda item: (item.subject_key, -item.score, item.rank_order, item.stock_id),
        )
